import { Badge } from '@/components/ui/badge'
import { formatRelativeSeconds } from '@/lib/utils'
import { useTelemetryStore } from '@/stores/telemetry-store'

export function TelemetryFreshness() {
  const lastFetchedAt = useTelemetryStore((s) => s.lastFetchedAt)
  const nowTick = useTelemetryStore((s) => s.nowTick)

  const iso = lastFetchedAt ? new Date(lastFetchedAt).toISOString() : null
  const { stale, label } = formatRelativeSeconds(iso, nowTick)

  return <Badge tone={stale ? 'warning' : 'success'}>{label}</Badge>
}
