# Умная аудитория (Smart Classroom)

Монорепозиторий проекта "Умная аудитория".

- `backend/` — FastAPI + Pydantic v2 + SQLAlchemy async (SQLite/aiosqlite для MVP)
- `frontend/` — React (Vite), разрабатывается отдельной командой

Документация: `Техническая документация бэкенда 1–3` (Арxитектура, API-контракты, Device Adapter).

## Структура backend (по Части 1 §3)

```
backend/
├── config/yandex_allowlist.yaml   # allowlist C-09, версия 2026-10-27
├── requirements.txt
├── Dockerfile
├── .env.example
└── app/
    ├── main.py                    # FastAPI, CORS, request-id, все роутеры
    ├── config.py                  # Settings (pydantic-settings) по §10.3
    ├── deps.py                    # composition root: engine + in_memory_adapter
    ├── api/                       # транспорт: control_plane, runs, auth,
    │                              # operator, assistant, admin, oauth, provider_api, errors
    ├── classroom_core/            # сущности + порты (ModeRepository, StateSnapshotPort)
    ├── mode_engine/               # models, catalog (§11), engine (preview/run), exceptions
    ├── device_adapter/            # контракт C-03: contract, dto, in_memory (+faults)
    ├── provider/                  # маппинг на формат Яндекса, allowlist
    ├── storage/                   # async engine/session (aiosqlite)
    └── observability/             # /healthz /readyz /metrics, X-Request-Id middleware
```

Правило зависимостей: `app/api → module → domain/ports → storage`. Домен не знает о FastAPI, БД и Яндексе.

## Запуск

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload   # http://localhost:8000
pytest
```

## Документация API (Swagger)

| URL | Что это |
|-----|---------|
| `http://localhost:8000/docs` | Swagger UI — запросы к бэку можно отправлять прямо из браузера («Try it out») |
| `http://localhost:8000/redoc` | ReDoc — read-only справка по контрактам |
| `http://localhost:8000/openapi.json` | сама схема OpenAPI 3 |

В схеме для каждой операции описано:

- **структура успешного ответа** (`RoomPlan`, `PreviewResult`, `RunPayload`, `Fault`, …) с живым примером;
- **конверт ошибок** (Часть 2 §1.1) для релевантных статусов — 400/404/409/422/502/504 с примером и кодом;
- **заголовки** `X-Simulate-Error` и `Idempotency-Key` — заполняются прямо в форме Swagger;
- **SSE** `/api/v1/runs/{runId}/events` — в Swagger поток не показывается, проверять через `curl -N`.

Пример флоу в Swagger: `GET /api/v1/room` → `POST .../modes/hybrid/preview`
(запомнить `preview_hash`) → `POST .../runs` (вставить hash + `Idempotency-Key`)
→ `GET /api/v1/runs/{runId}`.

## Ключевые эндпоинты

| Метод | Путь | Контракт |
|-------|------|----------|
| GET | `/healthz`, `/readyz`, `/metrics` | C-08 |
| GET | `/api/v1/room` · `/classrooms` · `/classrooms/{id}` · `/state` | C-01 |
| GET | `/api/v1/classrooms/{id}/modes` · `/modes/{modeId}` | C-01 |
| POST | `/api/v1/classrooms/{id}/modes/{modeId}/preview` | C-01 |
| POST | `/api/v1/classrooms/{id}/runs` (Idempotency-Key) | C-01 |
| GET | `/api/v1/runs` · `/runs/{runId}` · `/runs/{runId}/steps` | C-02 |
| POST | `/api/v1/classrooms/{id}/devices/{deviceId}/commands` | C-01 §2.5 |
| GET/POST | `/api/v1/auth/*` | C-07 |
| * | `/api/v1/operator/*` (faults, occupancy, reset, health, summary) | C-06 |
| * | `/api/v1/assistant/*` | — |
| * | `/api/v1/admin/users` | — |
| GET/POST | `/oauth/authorize` · `/oauth/token` · `/oauth/revoke` | C-05 |
| HEAD/GET/POST | `/v1.0/` · `/user/devices` · `query` · `action` · `unlink` | C-04 |

## Реальный движок (без моков preview/runs)

`app/deps.py` — composition root: один `InMemoryAdapter` + `ClassroomEngine`.

- **Каталог режимов** — матрицы Части 3 §11: arrival/lecture/hybrid/break/finish, 8 шагов, `critical` по `critical_device_ids`.
- **Preview** — читает живое состояние, считает diff `before→target`, `preview_hash = sha256(version:mode)[:16]`, TTL 15 мин. Предусловия:
  - lecture `presence_warning` (D11) → warning `presence_absent`;
  - hybrid `read_check` [D02, D04] → при недоступности `blocking_reasons=["read_check_failed"]`, `can_apply=false`;
  - finish `motion_quiet_5min` (D11 + `presence_minutes ≥ 5`) → warning `motion_not_quiet`.
- **Apply (`POST /runs`)** — пересчитывает preview, сверяет hash (409 `preview_stale`), ack warnings (422 `warnings_unacked`), `can_apply` (422 `precondition_failed`); шаги идут последовательно, `continue_on_error`, итог `applied|failed` + counters + `outcome_message`. Повтор `Idempotency-Key` → 200 + тот же run; другой body → 409 `idempotency_mismatch`.
- **Команды приборов** — реальный `adapter.execute` (валидация, readonly → 409, неверное значение → 422).

### Примеры для фронта
```
POST .../modes/hybrid/preview
  → 200: preview_hash (16 hex), 8 шагов, summary, expires_at
  → 200 can_apply=false + blocking_reasons  (например после fault D02)

POST .../runs  {mode_id, preview_hash, ack_warnings}  + Idempotency-Key
  → 201 status=applied|failed, counters, steps, poll_url
  → 409 preview_stale | idempotency_mismatch | run_in_progress
  → 422 warnings_unacked | precondition_failed

GET  /api/v1/runs/{runId} → журнал: status, counters, outcome_message, steps с error_text/manual_hint
```

### Инъекция сбоев (Operator API, S7)
```
POST /api/v1/operator/classrooms/{id}/simulator/faults
  {device_id, kind: unavailable|latency|error, value_ms?, error_code?, ttl_seconds?}
  → 201 {id, active, expires_at, created_by}
  unavailable → read: reachable=false; команда → 502 adapter_unreachable
  latency value_ms > 3000 → 504 device_timeout
  error error_code → код из реестра (например 422 invalid_value)

GET  .../simulator/faults          → {items, broken_devices}
DELETE /api/v1/operator/simulator/faults/{faultId} → {active: false}

POST .../simulator/occupancy  {detected, presence_minutes} → D11 motion (+ presence_minutes)
POST .../simulator/reset      → seed + faults_cleared + runs_cleared («чистый старт»)
GET  .../adapter/health       → ok|degraded + devices с last_error
GET  /api/v1/operator/summary?window=1h → runs/adapter/errors
```

## Моки и ошибки для фронта

### Данные: `GET /api/v1/room`
Полный план аудитории из seed: 3 зоны (Z1–Z3), 12 приборов (D01–D12), у каждого — `state`, `status` (`on|off|unavailable`), `managability`, `updated_at`, `source`. `state_version` = сумма версий приборов; `adapter_health` учитывает активные faults.

### Принудительная ошибка (для верстки алертов)
Эндпоинты с зависимостью `simulate_error` — `preview`, `POST/GET runs`,
`devices/{id}/commands`, `simulator/faults`, `simulator/occupancy` — с заголовком
`X-Simulate-Error: <code>` вернут конверт ошибки:
```
X-Simulate-Error: preview_stale | run_in_progress | invalid_value |
                  adapter_unreachable | device_timeout | not_found | ...
```
Заголовок виден в Swagger (`/docs`) как поле формы — можно тыкать без curl.

### Формат ошибки (Часть 2 §1.1) — один на весь API
```json
{ "error": { "code": "preview_stale", "message": "Состояние аудитории...",
             "details": {...}, "request_id": "...", "retryable": false } }
```
Ошибки валидации тела — 400 `validation_error`, неизвестный путь — 404 `not_found`.
`request_id` дублируется в заголовке `X-Request-Id`.

## Frontend

См. `frontend/README.md` (React + Vite, `http://localhost:5173`, CORS уже разрешён).
