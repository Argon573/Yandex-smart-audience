import { API_BASE_URL } from '@/lib/constants'
import { ApiError, type ApiErrorBody } from '@/types/api'

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  idempotencyKey?: string
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const data = (await response.json()) as ApiErrorBody
    if (data?.error?.code) {
      return new ApiError(response.status, data.error)
    }
  } catch {
    // fallthrough
  }
  return new ApiError(response.status, {
    code: 'http_error',
    message: `HTTP ${response.status}: ${response.statusText || 'ошибка запроса'}`,
  })
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (options.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (options.idempotencyKey) {
    headers.set('Idempotency-Key', options.idempotencyKey)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })

  if (!response.ok) {
    throw await parseError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
