import { Activity, Radar } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { DevicePayload } from '@/types/api'

interface OccupancyIndicatorProps {
  device?: DevicePayload
}

export function OccupancyIndicator({ device }: OccupancyIndicatorProps) {
  const motion = String(device?.state?.motion ?? 'not_detected')
  const detected = motion === 'detected'
  const online = device?.status !== 'unavailable'

  return (
    <div
      className={cn(
        'glass flex items-center gap-3 rounded-2xl px-4 py-3',
        detected && 'alice-glow',
      )}
    >
      <div
        className={cn(
          'flex h-10 w-10 items-center justify-center rounded-xl',
          detected ? 'bg-alice-cyan/20 text-alice-cyan' : 'bg-white/5 text-alice-muted',
        )}
      >
        {detected ? <Radar className="h-5 w-5 animate-pulse" /> : <Activity className="h-5 w-5" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">Датчик присутствия</p>
        <p className="truncate text-xs text-alice-muted">
          {device?.name ?? 'D11'} · {online ? 'online' : 'offline'}
        </p>
      </div>
      <Badge tone={detected ? 'info' : 'default'}>
        {detected ? 'движение' : 'тихо'}
      </Badge>
    </div>
  )
}
