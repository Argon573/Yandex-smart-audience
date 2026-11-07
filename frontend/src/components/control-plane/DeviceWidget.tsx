import {
  AirVent,
  Blinds,
  DoorOpen,
  Lightbulb,
  MonitorPlay,
  Projector,
  Scan,
  Speaker,
  SunMedium,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { deviceIconKind, formatRelativeSeconds } from '@/lib/utils'
import { useTelemetryStore } from '@/stores/telemetry-store'
import type { DevicePayload } from '@/types/api'

const ICONS: Record<string, LucideIcon> = {
  light: Lightbulb,
  curtain: Blinds,
  climate: AirVent,
  motion: Scan,
  illumination: SunMedium,
  projector: Projector,
  audio: Speaker,
  door: DoorOpen,
  device: MonitorPlay,
}

function summarizeState(device: DevicePayload): string {
  const { state, status } = device
  if (status === 'unavailable') return 'недоступно'
  if (typeof state.on === 'boolean') {
    const extras: string[] = []
    if (typeof state.brightness === 'number') extras.push(`${state.brightness}%`)
    if (typeof state.open === 'number') extras.push(`открыто ${state.open}%`)
    if (typeof state.volume === 'number') extras.push(`громк. ${state.volume}`)
    if (typeof state.temperature === 'number') extras.push(`${state.temperature}°C`)
    if (typeof state.motion === 'string') extras.push(String(state.motion))
    if (typeof state.illumination === 'number') extras.push(`${state.illumination} лк`)
    if (typeof state.humidity === 'number') extras.push(`${state.humidity}% влажн.`)
    return [state.on ? 'вкл' : 'выкл', ...extras].join(' · ')
  }
  if (typeof state.motion === 'string') return String(state.motion)
  if (typeof state.temperature === 'number') {
    return `${state.temperature}°C${typeof state.humidity === 'number' ? ` · ${state.humidity}%` : ''}`
  }
  if (typeof state.illumination === 'number') return `${state.illumination} лк`
  return status
}

interface DeviceWidgetProps {
  device: DevicePayload
  zoneName: string
}

export function DeviceWidget({ device, zoneName }: DeviceWidgetProps) {
  const nowTick = useTelemetryStore((s) => s.nowTick)
  const kind = deviceIconKind(device.ya_type, device.name)
  const Icon = ICONS[kind] ?? MonitorPlay
  const freshness = formatRelativeSeconds(device.updated_at, nowTick)
  const tone =
    device.status === 'unavailable'
      ? 'danger'
      : device.status === 'on'
        ? 'success'
        : 'default'

  return (
    <Card className="flex h-full flex-col p-3.5 transition hover:border-alice-lilac/35">
      <CardHeader className="mb-2">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-alice-violet/20 text-alice-lilac">
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <CardTitle className="truncate text-sm">{device.name}</CardTitle>
            <CardDescription className="truncate text-xs">
              {device.id} · {zoneName}
            </CardDescription>
          </div>
        </div>
        <Badge tone={tone}>{device.status}</Badge>
      </CardHeader>

      <p className="mb-3 text-sm text-alice-text/90">{summarizeState(device)}</p>

      <div className="mt-auto flex items-center justify-between gap-2 text-[11px] text-alice-muted">
        <span>{device.managability === 'readonly' ? 'только чтение' : 'управляемый'}</span>
        <span className={freshness.stale ? 'text-alice-warning' : undefined}>
          {freshness.label}
        </span>
      </div>
    </Card>
  )
}
