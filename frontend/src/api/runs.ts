import { CLASSROOM_ID } from '@/lib/constants'
import { apiRequest } from '@/lib/api-client'
import type { RunCreateBody, RunPayload } from '@/types/api'

export function applyMode(
  body: RunCreateBody,
  idempotencyKey: string,
  classroomId = CLASSROOM_ID,
): Promise<RunPayload> {
  return apiRequest<RunPayload>(`/api/v1/classrooms/${classroomId}/runs`, {
    method: 'POST',
    body,
    idempotencyKey,
  })
}

export function fetchRun(runId: string): Promise<RunPayload> {
  return apiRequest<RunPayload>(`/api/v1/runs/${runId}`)
}

/**
 * SSE прогресса запуска (S5).
 * События: run.current | step.updated | run.finished
 */
export function subscribeRunEvents(
  runId: string,
  handlers: {
    onEvent: (event: string, data: unknown) => void
    onError?: (error: Event) => void
  },
): () => void {
  const source = new EventSource(`/api/v1/runs/${runId}/events`)

  const forward = (eventName: string) => (event: MessageEvent) => {
    try {
      handlers.onEvent(eventName, JSON.parse(event.data as string))
    } catch {
      handlers.onEvent(eventName, event.data)
    }
  }

  source.addEventListener('run.current', forward('run.current'))
  source.addEventListener('step.updated', forward('step.updated'))
  source.addEventListener('run.finished', forward('run.finished'))
  source.onerror = (error) => handlers.onError?.(error)

  return () => source.close()
}
