import { useEffect } from 'react'

import { useTelemetryStore } from '@/stores/telemetry-store'

/** Тикает раз в секунду для индикатора «обновлено N с назад». */
export function useClockTick() {
  const tick = useTelemetryStore((s) => s.tick)

  useEffect(() => {
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [tick])
}
