const AUTH_STORAGE_KEY = 'auctions.auth.token'

export function getStoredAccessToken(): string | null {
  if (typeof window === 'undefined') {
    return null
  }

  return window.localStorage.getItem(AUTH_STORAGE_KEY)
}

export function setStoredAccessToken(token: string) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(AUTH_STORAGE_KEY, token)
}

export function clearStoredAccessToken() {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.removeItem(AUTH_STORAGE_KEY)
}
