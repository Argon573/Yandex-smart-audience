import { DeviceWidget } from '@/components/control-plane/DeviceWidget'
import { Badge } from '@/components/ui/badge'
import type { ZonePayload } from '@/types/api'

interface ZoneCardProps {
  zone: ZonePayload
}

export function ZoneCard({ zone }: ZoneCardProps) {
  const online = zone.devices.filter((d) => d.status !== 'unavailable').length

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <h2 className="text-lg font-semibold">{zone.name}</h2>
            <Badge>{zone.code}</Badge>
          </div>
          <p className="text-sm text-alice-muted">{zone.purpose}</p>
        </div>
        <p className="text-xs text-alice-muted">
          online {online}/{zone.devices.length}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {zone.devices.map((device) => (
          <DeviceWidget key={device.id} device={device} zoneName={zone.name} />
        ))}
      </div>
    </section>
  )
}
