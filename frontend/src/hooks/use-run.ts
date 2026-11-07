import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { fetchRun, subscribeRunEvents } from '@/api/runs'
import { RUN_POLL_INTERVAL_MS } from '@/lib/constants'
import type { RunPayload, RunStepPayload } from '@/types/api'

export function useRun(runId: string | null) {
  const [sseRun, setSseRun] = useState<Partial<RunPayload> | null>(null)

  const query = useQuery({
    queryKey: ['run', runId],
    queryFn: () => fetchRun(runId!),
    enabled: Boolean(runId),
    refetchInterval: (q) =>
      q.state.data?.status === 'running' ? RUN_POLL_INTERVAL_MS : false,
  })

  useEffect(() => {
    if (!runId) return
    setSseRun(null)

    return subscribeRunEvents(runId, {
      onEvent: (event, data) => {
        const payload = data as Partial<RunPayload> & { step?: RunStepPayload }

        if (event === 'run.current' || event === 'run.finished') {
          setSseRun({
            steps: payload.steps,
            status: payload.status,
            outcome_message: payload.outcome_message,
            counters: payload.counters,
          })
          return
        }

        if (event === 'step.updated' && payload.step) {
          setSseRun((prev) => {
            const baseSteps = prev?.steps ?? []
            const next = [...baseSteps]
            const idx = next.findIndex((s) => s.sequence === payload.step!.sequence)
            if (idx >= 0) next[idx] = payload.step!
            else next.push(payload.step!)
            return {
              ...prev,
              steps: next.sort((a, b) => a.sequence - b.sequence),
            }
          })
        }
      },
    })
  }, [runId])

  const run = query.data
    ? {
        ...query.data,
        steps: sseRun?.steps ?? query.data.steps,
        status: sseRun?.status ?? query.data.status,
        outcome_message: sseRun?.outcome_message ?? query.data.outcome_message,
        counters: sseRun?.counters ?? query.data.counters,
      }
    : undefined

  return { ...query, run }
}
