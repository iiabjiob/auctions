import { getStoredAccessToken } from '@/auth/tokenStorage'
import { buildAppPath } from '@/api/base'

type ApiRequestInit = RequestInit & {
  auth?: boolean
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

  const response = await fetch(buildAppPath(`/api/v1${path}`), {
    ...requestInit,
    headers: nextHeaders,
  })

  if (!response.ok) {
    let detail = `API вернул ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        detail = payload.detail
      }
    } catch {
      // keep default detail
    }
    throw new Error(detail)
  }

  return (await response.json()) as T
}
