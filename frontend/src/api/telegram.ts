import { apiRequest } from '@/api/http'

export type TelegramConnectTokenResponse = {
  connect_url: string
  expires_at: string
}

export async function createTelegramConnectToken(): Promise<TelegramConnectTokenResponse> {
  return apiRequest<TelegramConnectTokenResponse>('/telegram/connect-token', {
    method: 'POST',
    auth: true,
  })
}
