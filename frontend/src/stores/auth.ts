import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { clearStoredAccessToken, getStoredAccessToken, setStoredAccessToken } from '@/auth/tokenStorage'
import { fetchAuthPublicConfig, fetchCurrentUser, loginUser } from '@/api/auth'
import type { AuthPublicConfig, AuthSession, AuthUser, LoginInput } from '@/types/auth'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(getStoredAccessToken())
  const currentUser = ref<AuthUser | null>(null)
  const publicConfig = ref<AuthPublicConfig | null>(null)
  const isRestoring = ref(false)
  const isSubmitting = ref(false)
  const errorMessage = ref<string | null>(null)

  const isAuthenticated = computed(() => Boolean(accessToken.value && currentUser.value))

  function applySession(session: AuthSession) {
    accessToken.value = session.access_token
    currentUser.value = session.user
    errorMessage.value = null
    setStoredAccessToken(session.access_token)
  }

  function logout() {
    accessToken.value = null
    currentUser.value = null
    errorMessage.value = null
    clearStoredAccessToken()
  }

  async function restoreSession() {
    isRestoring.value = true
    errorMessage.value = null

    try {
      publicConfig.value = await fetchAuthPublicConfig()

      if (!accessToken.value) {
        currentUser.value = null
        return
      }

      currentUser.value = await fetchCurrentUser()
    } catch (error) {
      logout()
      if (error instanceof Error && error.message !== 'Сессия не найдена.') {
        errorMessage.value = error.message
      }
    } finally {
      isRestoring.value = false
    }
  }

  async function login(payload: LoginInput) {
    isSubmitting.value = true
    errorMessage.value = null

    try {
      applySession(await loginUser(payload))
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Не удалось войти.'
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    accessToken,
    currentUser,
    errorMessage,
    isAuthenticated,
    isRestoring,
    isSubmitting,
    login,
    logout,
    publicConfig,
    restoreSession,
  }
})
