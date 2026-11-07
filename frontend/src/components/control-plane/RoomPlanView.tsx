import { OccupancyIndicator } from '@/components/control-plane/OccupancyIndicator'
import { TelemetryFreshness } from '@/components/control-plane/TelemetryFreshness'
import { ZoneCard } from '@/components/control-plane/ZoneCard'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import type { RoomPlan } from '@/types/api'

interface RoomPlanViewProps {
  room?: RoomPlan
  isLoading: boolean
  errorMessage?: string
}

export function RoomPlanView({ room, isLoading, errorMessage }: RoomPlanViewProps) {
  if (isLoading && !room) {
    return (
      <div className="glass flex min-h-64 items-center justify-center rounded-3xl">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  if (errorMessage) {
    return (
      <div className="glass rounded-3xl border border-alice-danger/30 p-6 text-alice-danger">
        Не удалось загрузить план аудитории: {errorMessage}
      </div>
    )
  }

  if (!room) return null

  const occupancy = room.zones.flatMap((z) => z.devices).find((d) => d.id === 'D11')
  const healthTone =
    room.adapter_health === 'ok'
      ? 'success'
      : room.adapter_health === 'degraded'
        ? 'warning'
        : 'danger'

  return (
    <div className="space-y-5">
      <div className="glass flex flex-wrap items-center justify-between gap-3 rounded-3xl px-5 py-4">
        <div>
          <h2 className="text-xl font-semibold">{room.name}</h2>
          <p className="text-sm text-alice-muted">
            {room.device_count} устройств · state v{room.state_version}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={healthTone}>adapter: {room.adapter_health}</Badge>
          <TelemetryFreshness />
        </div>
      </div>

      <OccupancyIndicator device={occupancy} />

      <div className="space-y-8">
        {room.zones.map((zone) => (
          <ZoneCard key={zone.id} zone={zone} />
        ))}
      </div>
    </div>
  )
}
