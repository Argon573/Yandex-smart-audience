import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

import { fetchRoomPlan } from '@/api/room'
import { ROOM_POLL_INTERVAL_MS } from '@/lib/constants'
import { useTelemetryStore } from '@/stores/telemetry-store'

export function useRoomPlan() {
  const markFetched = useTelemetryStore((s) => s.markFetched)

  const query = useQuery({
    queryKey: ['room'],
    queryFn: fetchRoomPlan,
    refetchInterval: ROOM_POLL_INTERVAL_MS,
  })

  useEffect(() => {
    if (query.dataUpdatedAt) {
      markFetched(query.dataUpdatedAt)
    }
  }, [query.dataUpdatedAt, markFetched])

  return query
}
