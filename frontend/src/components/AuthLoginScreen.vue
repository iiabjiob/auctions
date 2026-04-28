<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const { errorMessage, isRestoring, isSubmitting, publicConfig } = storeToRefs(authStore)

const email = ref('')
const password = ref('')

const helperText = computed(() => {
  if (!publicConfig.value?.default_user_enabled) {
    return ''
  }
  return 'Демо-пользователь может быть создан на бэке. Email подставлен, пароль задается через env и вводится вручную.'
})

watch(
  publicConfig,
  (config) => {
    if (!config?.default_user_enabled) return
    email.value = config.default_user_email ?? ''
  },
  { immediate: true },
)

async function submit() {
  try {
    await authStore.login({
      email: email.value.trim(),
      password: password.value,
    })
  } catch {
    // store already holds message
  }
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-panel" aria-label="Вход в систему">
      <div class="auth-panel__copy">
        <span class="eyebrow">Auctions Workspace</span>
        <h1>Вход в каталог лотов</h1>
        <p>Базовая авторизация для рабочего доступа к таблице, карточкам лотов и фоновой синхронизации.</p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>Email</span>
          <input v-model="email" type="email" autocomplete="username" placeholder="you@example.com" />
        </label>

        <label>
          <span>Пароль</span>
          <input v-model="password" type="password" autocomplete="current-password" placeholder="Введите пароль" />
        </label>

        <p v-if="helperText" class="auth-form__hint">{{ helperText }}</p>
        <p v-if="errorMessage" class="auth-form__error">{{ errorMessage }}</p>

        <button class="primary-button auth-form__submit" type="submit" :disabled="isRestoring || isSubmitting">
          {{ isRestoring ? 'Проверяю сессию' : isSubmitting ? 'Вхожу' : 'Войти' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.auth-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(31, 143, 82, 0.14), transparent 28%),
    radial-gradient(circle at bottom right, rgba(190, 90, 73, 0.12), transparent 26%),
    linear-gradient(180deg, #f4f7fb 0%, #eef3f8 100%);
}

.auth-panel {
  width: min(100%, 920px);
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 380px);
  gap: 28px;
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 24px 60px rgba(30, 41, 59, 0.1);
  backdrop-filter: blur(10px);
}

.auth-panel__copy {
  display: grid;
  align-content: center;
  gap: 12px;
}

.auth-panel__copy p {
  margin: 0;
  max-width: 42ch;
  color: var(--color-text-muted);
  font-size: 15px;
  line-height: 1.6;
}

.auth-form {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(250, 251, 253, 0.96) 0%, #ffffff 100%);
}

.auth-form label {
  display: grid;
  gap: 6px;
}

.auth-form label span {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.auth-form__hint,
.auth-form__error {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}

.auth-form__hint {
  color: var(--color-text-muted);
}

.auth-form__error {
  color: var(--color-risk);
}

.auth-form__submit {
  width: 100%;
  margin-top: 4px;
}

@media (max-width: 860px) {
  .auth-panel {
    grid-template-columns: minmax(0, 1fr);
    padding: 20px;
  }
}
</style>
