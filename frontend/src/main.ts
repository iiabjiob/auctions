import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { useAuthStore } from './stores/auth'
import router from './router'

async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)
  app.use(router)

  const authStore = useAuthStore(pinia)
  await authStore.restoreSession()

  app.mount('#app')
}

void bootstrap()
