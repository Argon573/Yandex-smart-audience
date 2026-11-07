import { RotateCcw, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { Slider } from '@/components/ui/slider'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import {
  useFaults,
  useInjectFault,
  useRemoveFault,
  useResetSimulator,
  useSetOccupancy,
} from '@/hooks/use-operator'
import { useRoomPlan } from '@/hooks/use-room'
import type { FaultKind } from '@/types/api'

const KIND_LABEL: Record<FaultKind, string> = {
  unavailable: 'offline',
  latency: 'latency',
  error: 'error',
}

export function OperatorPanel() {
  const room = useRoomPlan()
  const faults = useFaults()
  const inject = useInjectFault()
  const remove = useRemoveFault()
  const occupancy = useSetOccupancy()
  const reset = useResetSimulator()

  const devices = useMemo(
    () => room.data?.zones.flatMap((z) => z.devices) ?? [],
    [room.data],
  )

  const occupancyDevice = devices.find((d) => d.id === 'D11')
  const motionDetected = String(occupancyDevice?.state?.motion ?? '') === 'detected'

  const [latencyByDevice, setLatencyByDevice] = useState<Record<string, number>>({})
  const [presenceMinutes, setPresenceMinutes] = useState(0)

  const activeFaults = faults.data?.items.filter((f) => f.active) ?? []

  const setDeviceKind = (deviceId: string, kind: FaultKind | 'online') => {
    if (kind === 'online') {
      const existing = activeFaults.filter((f) => f.device_id === deviceId)
      existing.forEach((f) => remove.mutate(f.id))
      return
    }

    inject.mutate({
      device_id: deviceId,
      kind,
      value_ms: kind === 'latency' ? latencyByDevice[deviceId] ?? 1500 : null,
      error_code: kind === 'error' ? 'invalid_value' : null,
      comment: `UI injection: ${kind}`,
      ttl_seconds: 600,
    })
  }

  return (
    <div className="space-y-5">
      <Card className="rounded-3xl p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-alice-lilac/80">S7 · Operator</p>
            <h2 className="mt-1 text-2xl font-semibold">Панель симулятора</h2>
            <CardDescription className="mt-1">
              Инъекция отказов, latency и ручная генерация движения D11
            </CardDescription>
          </div>
          <Button
            variant="secondary"
            onClick={() => reset.mutate()}
            disabled={reset.isPending}
          >
            {reset.isPending ? <Spinner /> : <RotateCcw className="h-4 w-4" />}
            Reset seed
          </Button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone="info">broken: {faults.data?.broken_devices.length ?? 0}</Badge>
          <Badge>faults: {activeFaults.length}</Badge>
        </div>
      </Card>

      <Card className="rounded-3xl p-5">
        <CardTitle className="mb-1">Датчик занятости (D11)</CardTitle>
        <CardDescription className="mb-4">
          Тумблер ручной генерации движения для предусловий режимов
        </CardDescription>
        <div className="flex flex-wrap items-center gap-6">
          <Switch
            id="occupancy-toggle"
            checked={motionDetected}
            disabled={occupancy.isPending}
            label={motionDetected ? 'движение detected' : 'тихо not_detected'}
            onCheckedChange={(detected) =>
              occupancy.mutate({ detected, presence_minutes: presenceMinutes })
            }
          />
          <div className="min-w-56 flex-1">
            <div className="mb-1 flex justify-between text-xs text-alice-muted">
              <span>presence_minutes</span>
              <span>{presenceMinutes} мин</span>
            </div>
            <Slider
              value={presenceMinutes}
              min={0}
              max={30}
              onValueChange={(value) => {
                setPresenceMinutes(value)
                occupancy.mutate({ detected: motionDetected, presence_minutes: value })
              }}
            />
          </div>
        </div>
      </Card>

      <Card className="rounded-3xl p-5">
        <CardTitle className="mb-1">Инъекция сбоев устройств</CardTitle>
        <CardDescription className="mb-4">
          online / offline / error + ползунок latency (мс)
        </CardDescription>

        <div className="space-y-3">
          {devices.map((device) => {
            const deviceFaults = activeFaults.filter((f) => f.device_id === device.id)
            const currentKind: FaultKind | 'online' =
              deviceFaults.find((f) => f.kind === 'unavailable')
                ? 'unavailable'
                : deviceFaults.find((f) => f.kind === 'error')
                  ? 'error'
                  : deviceFaults.find((f) => f.kind === 'latency')
                    ? 'latency'
                    : 'online'
            const latency = latencyByDevice[device.id] ?? deviceFaults.find((f) => f.kind === 'latency')?.value_ms ?? 1000

            return (
              <div
                key={device.id}
                className="rounded-2xl border border-white/10 bg-alice-surface/40 p-4"
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium">
                      {device.name}{' '}
                      <span className="text-xs text-alice-muted">{device.id}</span>
                    </p>
                    <p className="text-xs text-alice-muted">status UI: {device.status}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(['online', 'unavailable', 'error'] as const).map((kind) => (
                      <Button
                        key={kind}
                        size="sm"
                        variant={currentKind === kind ? 'primary' : 'secondary'}
                        disabled={inject.isPending || remove.isPending}
                        onClick={() => setDeviceKind(device.id, kind)}
                      >
                        {kind === 'unavailable' ? 'offline' : kind}
                      </Button>
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap items-end gap-3">
                  <div className="min-w-56 flex-1">
                    <div className="mb-1 flex justify-between text-xs text-alice-muted">
                      <span>latency injection</span>
                      <span>{latency} мс</span>
                    </div>
                    <Slider
                      value={latency}
                      min={0}
                      max={5000}
                      step={100}
                      onValueChange={(value) =>
                        setLatencyByDevice((prev) => ({ ...prev, [device.id]: value }))
                      }
                    />
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={inject.isPending}
                    onClick={() =>
                      inject.mutate({
                        device_id: device.id,
                        kind: 'latency',
                        value_ms: latency,
                        comment: 'UI latency slider',
                        ttl_seconds: 600,
                      })
                    }
                  >
                    Применить latency
                  </Button>
                </div>

                {deviceFaults.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {deviceFaults.map((fault) => (
                      <Badge key={fault.id} tone="warning" className="gap-2">
                        {KIND_LABEL[fault.kind]}
                        {fault.value_ms ? ` ${fault.value_ms}ms` : ''}
                        <button
                          type="button"
                          aria-label="Удалить fault"
                          onClick={() => remove.mutate(fault.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}
