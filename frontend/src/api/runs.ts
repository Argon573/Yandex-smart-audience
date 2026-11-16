import { CLASSROOM_ID } from '@/lib/constants'
import { apiRequest, authenticatedFetch } from '@/lib/api-client'
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
  const controller = new AbortController()
  void (async () => {
    try {
      const response = await authenticatedFetch(
        `/api/v1/runs/${runId}/events`,
        { signal: controller.signal, headers: { Accept: 'text/event-stream' } },
        true,
      )
      if (!response.ok || !response.body) throw new Error(`SSE HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let boundary = buffer.search(/\r?\n\r?\n/)
        while (boundary >= 0) {
          const block = buffer.slice(0, boundary)
          const delimiter = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] ?? '\n\n'
          buffer = buffer.slice(boundary + delimiter.length)
          const lines = block.split(/\r?\n/)
          const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
          const data = lines.filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart()).join('\n')
          if (eventName && data) {
            try {
              handlers.onEvent(eventName, JSON.parse(data) as unknown)
            } catch {
              handlers.onEvent(eventName, data)
            }
          }
          boundary = buffer.search(/\r?\n\r?\n/)
        }
      }
    } catch {
      if (!controller.signal.aborted) handlers.onError?.(new Event('error'))
    }
  })()

  return () => controller.abort()
}
