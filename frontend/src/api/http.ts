import { getStoredAccessToken } from '@/auth/tokenStorage'

type ApiRequestInit = RequestInit & {
  auth?: boolean
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

export async function apiRequest<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const { auth = false, headers, ...requestInit } = init ?? {}
  const nextHeaders = new Headers(headers ?? {})
  if (!nextHeaders.has('Content-Type') && requestInit.body) {
    nextHeaders.set('Content-Type', 'application/json')
  }

  if (auth) {
    const token = getStoredAccessToken()
    if (!token) {
      throw new Error('Сессия не найдена.')
    }
    nextHeaders.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`/api/v1${path}`, {
    ...requestInit,
    headers: nextHeaders,
  })

  if (!response.ok) {
    let detail = `API вернул ${response.status}`
    let body: unknown = null
    try {
      const payload = (await response.json()) as { detail?: string }
      body = payload
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        detail = payload.detail
      }
    } catch {
      // keep default detail
    }
    throw new ApiRequestError(detail, response.status, body)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
