import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatRelativeSeconds(updatedAt: string | null | undefined, nowMs: number): {
  seconds: number
  stale: boolean
  label: string
} {
  if (!updatedAt) {
    return { seconds: Number.POSITIVE_INFINITY, stale: true, label: 'данные устарели' }
  }

  const then = Date.parse(updatedAt)
  if (Number.isNaN(then)) {
    return { seconds: Number.POSITIVE_INFINITY, stale: true, label: 'данные устарели' }
  }

  const seconds = Math.max(0, Math.floor((nowMs - then) / 1000))
  if (seconds > 10) {
    return { seconds, stale: true, label: 'данные устарели' }
  }
  return { seconds, stale: false, label: `обновлено ${seconds} с назад` }
}

export function createIdempotencyKey(prefix = 'run'): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function humanizeBlockingReason(reason: string): string {
  const map: Record<string, string> = {
    read_check_failed: 'Критичные устройства недоступны для чтения (проектор/аудио)',
    presence_absent: 'Датчик присутствия не фиксирует людей в аудитории',
    motion_not_quiet: 'В аудитории недавно было движение — энергосбережение рискованно',
    projector_offline: 'Проектор оффлайн',
  }
  return map[reason] ?? reason
}

export function deviceIconKind(yaType: string, name: string): string {
  if (yaType.includes('light')) return 'light'
  if (yaType.includes('curtain') || name.toLowerCase().includes('экран')) return 'curtain'
  if (yaType.includes('thermostat') || yaType.includes('climate')) return 'climate'
  if (yaType.includes('motion')) return 'motion'
  if (yaType.includes('illumination')) return 'illumination'
  if (name.toLowerCase().includes('проектор')) return 'projector'
  if (name.toLowerCase().includes('аудио')) return 'audio'
  if (name.toLowerCase().includes('двери') || name.toLowerCase().includes('дверь')) return 'door'
  return 'device'
}
