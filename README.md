# Умная аудитория (Smart Classroom)

Монорепозиторий проекта "Умная аудитория".

- `backend/` — FastAPI + Pydantic v2 + SQLAlchemy async (SQLite/aiosqlite для MVP)
- `frontend/` — React (Vite), разрабатывается отдельной командой

Документация: `Техническая документация бэкенда 1–3` (Архитектура, API-контракты, Device Adapter).

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
    ├── api/                       # транспорт: control_plane, runs, auth,
    │                              # operator, assistant, admin, oauth, provider_api
    ├── classroom_core/            # сущности + порты (ModeRepository, StateSnapshotPort)
    ├── mode_engine/               # Mode/Run/PreviewResult, catalog, ClassroomEngine
    ├── device_adapter/            # контракт C-03: contract, dto, in_memory
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

## Ключевые эндпоинты (заглушки)

| Метод | Путь | Контракт |
|-------|------|----------|
| GET | `/healthz`, `/readyz`, `/metrics` | C-08 |
| GET | `/api/v1/classrooms` · `/classrooms/{id}` · `/state` | C-01 |
| GET | `/api/v1/classrooms/{id}/modes` | C-01 |
| POST | `/api/v1/classrooms/{id}/modes/{modeId}/preview` | C-01 |
| POST | `/api/v1/classrooms/{id}/runs` (Idempotency-Key) | C-01 |
| GET | `/api/v1/runs/{runId}` — опрос каждые 2 с | C-02 |
| GET/POST | `/api/v1/auth/*` | C-07 |
| * | `/api/v1/operator/*` | C-06 |
| * | `/api/v1/assistant/*` | — |
| * | `/api/v1/admin/users` | — |
| GET/POST | `/oauth/authorize` · `/oauth/token` · `/oauth/revoke` | C-05 |
| HEAD/GET/POST | `/v1.0/` · `/user/devices` · `query` · `action` · `unlink` | C-04 |

## Моки и ошибки для фронта

### Данные: `GET /api/v1/room`
Полный план аудитории из seed: 3 зоны (Z1–Z3), 12 приборов (D01–D12), у каждого — `state`, `status` (`on|off|unavailable`), `managability`, `updated_at`, `source`. Карточка прибора: `GET /api/v1/classrooms/{id}/devices/{deviceId}` (там же `specs.capabilities`).

### Preview и apply (экраны S4/S5)
```
POST /api/v1/classrooms/{id}/modes/{modeId}/preview
  → 200: preview_hash="a91f3c8e", 7 шагов (will_change/already_in_state),
         warnings=[presence_absent], summary, expires_at (+15 мин)

POST /api/v1/classrooms/{id}/runs        (тело: mode_id, preview_hash, ack_warnings)
  → 201: status=running, step_total=7, poll_url
  → 409 preview_stale,     если preview_hash != "a91f3c8e"
  → 422 warnings_unacked,  если ack_warnings не содержит "presence_absent"

GET  /api/v1/runs/{runId}   → мок итога: status=failed, counters,
                              outcome_message «Применено частично...», шаги с ошибкой
```

### Принудительная ошибка (для верстки алертов)
Любой эндпоинт с заголовком `X-Simulate-Error: <code>` вернёт конверт ошибки:
```
X-Simulate-Error: preview_stale | run_in_progress | invalid_value |
                  adapter_unreachable | device_timeout | not_found | ...
```

### Формат ошибки (Часть 2 §1.1) — один на весь API
```json
{ "error": { "code": "preview_stale", "message": "Состояние аудитории...",
             "details": {...}, "request_id": "...", "retryable": false } }
```
Ошибки валидации тела — 400 `validation_error`, неизвестный путь — 404 `not_found`.
`request_id` дублируется в заголовке `X-Request-Id`.

## Frontend

См. `frontend/README.md` (React + Vite, `http://localhost:5173`, CORS уже разрешён).
