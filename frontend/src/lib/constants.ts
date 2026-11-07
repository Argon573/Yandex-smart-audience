export const CLASSROOM_ID =
  import.meta.env.VITE_CLASSROOM_ID ?? '9f1b6a2e-0000-4000-8000-000000000001'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export const TELEMETRY_STALE_SECONDS = 10
export const ROOM_POLL_INTERVAL_MS = 3000
export const RUN_POLL_INTERVAL_MS = 1000

export const MODE_META: Record<
  string,
  { accent: string; hint: string; icon: 'sunrise' | 'book' | 'presentation' | 'coffee' | 'power' }
> = {
  arrival: {
    accent: 'from-cyan-400/30 to-violet-500/20',
    hint: 'Мягкий свет и климат при входе',
    icon: 'sunrise',
  },
  lecture: {
    accent: 'from-violet-400/35 to-blue-500/20',
    hint: 'Рабочий свет и проекция',
    icon: 'book',
  },
  hybrid: {
    accent: 'from-fuchsia-400/30 to-cyan-400/20',
    hint: 'Приглушённый свет + экран и звук',
    icon: 'presentation',
  },
  break: {
    accent: 'from-amber-300/25 to-violet-400/20',
    hint: 'Пауза: комфорт без проекции',
    icon: 'coffee',
  },
  finish: {
    accent: 'from-slate-300/20 to-violet-500/25',
    hint: 'Завершение и энергосбережение',
    icon: 'power',
  },
}

/** Устройства с длительными операциями — для спиннеров на S5. */
export const LONG_RUNNING_DEVICES: Record<string, { label: string; expectedSec: [number, number] }> = {
  D02: { label: 'Прогрев проектора', expectedSec: [20, 30] },
  D03: { label: 'Спуск/подъём экрана', expectedSec: [10, 15] },
}
