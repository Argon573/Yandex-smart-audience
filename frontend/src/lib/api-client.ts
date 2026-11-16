import { API_BASE_URL } from '@/lib/constants'
import { ApiError, type ApiErrorBody } from '@/types/api'

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  idempotencyKey?: string
}

export type AuthTokens = {
  access_token: string
  refresh_token: string
  expires_in: number
}

const ACCESS_KEY = 'smart-classroom-access'
const REFRESH_KEY = 'smart-classroom-refresh'
const EXPIRES_KEY = 'smart-classroom-expires-at'
let refreshInFlight: Promise<string | null> | null = null

export function storeAuthTokens(tokens: AuthTokens): void {
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token)
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  sessionStorage.setItem(EXPIRES_KEY, String(Date.now() + tokens.expires_in * 1000))
  window.dispatchEvent(new Event('smart-classroom-auth-changed'))
}

export function clearAuthTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(EXPIRES_KEY)
  window.dispatchEvent(new Event('smart-classroom-auth-changed'))
}

export function hasAuthSession(): boolean {
  return Boolean(sessionStorage.getItem(ACCESS_KEY))
}

function isInternalApi(path: string): boolean {
  return path.startsWith('/api/v1/') && !path.startsWith('/api/v1/auth/login') &&
    !path.startsWith('/api/v1/auth/refresh')
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight
  const refreshToken = sessionStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return null

  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!response.ok) {
        clearAuthTokens()
        return null
      }
      const tokens = (await response.json()) as AuthTokens
      storeAuthTokens(tokens)
      return tokens.access_token
    } catch {
      clearAuthTokens()
      return null
    } finally {
      refreshInFlight = null
    }
  })()
  return refreshInFlight
}

export async function authenticatedFetch(
  url: string,
  init: RequestInit = {},
  internal = false,
): Promise<Response> {
  const headers = new Headers(init.headers)
  let token = internal ? sessionStorage.getItem(ACCESS_KEY) : null
  const expiresAt = Number(sessionStorage.getItem(EXPIRES_KEY) || 0)
  if (internal && token && expiresAt && expiresAt <= Date.now() + 20_000) {
    token = await refreshAccessToken()
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response = await fetch(url, { ...init, headers })
  if (internal && response.status === 401 && sessionStorage.getItem(REFRESH_KEY)) {
    token = await refreshAccessToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
      response = await fetch(url, { ...init, headers })
    }
  }
  if (internal && response.status === 401) clearAuthTokens()
  return response
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

  const response = await authenticatedFetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  }, isInternalApi(path))

  if (!response.ok) {
    throw await parseError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
