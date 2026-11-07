# Frontend — Умная аудитория

React 18+/19 + Vite + TypeScript. Пульт Control Plane (S1/S3/S4/S5) и панель оператора симулятора (S7).

## Стек

- Vite + React + TypeScript
- Tailwind CSS v4 + локальные UI-примитивы в стиле shadcn
- Zustand (UI-флоу режимов) + TanStack Query v5 (серверный стейт)
- Lucide Icons, React Router
- REST `/api/v1/*` + SSE `/api/v1/runs/{id}/events`

## Запуск

```bash
# из корня монорепо — бэкенд на :8000
cd backend && uvicorn app.main:app --reload

# фронт
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Dev-прокси Vite пробрасывает `/api` → `http://localhost:8000`. CORS бэкенда также разрешает origin `5173`.

## Экраны

| Маршрут | Экран |
|---------|--------|
| `/` | S1 Control Plane + S3 режимы + S4 Preview modal |
| `/executions/:runId` | S5 Execution Timeline (+ SSE) |
| `/operator` | S7 Fault injection / occupancy / reset |
