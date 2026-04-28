import { apiRequest } from '@/api/http'
import type { AuthPublicConfig, AuthSession, AuthUser, LoginInput } from '@/types/auth'

export async function loginUser(payload: LoginInput): Promise<AuthSession> {
  return apiRequest<AuthSession>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>('/auth/me', {
    auth: true,
  })
}

export async function fetchAuthPublicConfig(): Promise<AuthPublicConfig> {
  return apiRequest<AuthPublicConfig>('/auth/public-config')
}
