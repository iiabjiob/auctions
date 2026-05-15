<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  bindings: any
}>()

const router = useRouter()

onMounted(() => {
  props.bindings.resetInterestProfileDraft()
  void props.bindings.loadPresets()
  void props.bindings.loadUserInterestProfiles()
})

function closeRoute() {
  void router.push('/auctions')
}
</script>

<template>
  <section class="app-dialog-layer app-route-layer">
    <div class="app-dialog app-dialog--wide app-route-panel" role="dialog" aria-modal="true" aria-labelledby="interest-profiles-route-title" tabindex="-1">
      <header class="app-dialog__header">
        <div>
          <span class="eyebrow">Персональные сигналы</span>
          <h1 id="interest-profiles-route-title">Профили интересов</h1>
        </div>
        <button class="icon-button" type="button" aria-label="Закрыть страницу" @click="closeRoute">×</button>
      </header>

      <div class="app-dialog__body app-dialog__body--scroll">
        <p class="app-dialog__text">
          Профиль интересов управляет тем, какие рейтинговые лоты попадут в персональные Telegram-уведомления.
          Срез таблицы остается только UI-фильтром.
        </p>

        <div v-if="bindings.interestProfilesError" class="error-banner">{{ bindings.interestProfilesError }}</div>

        <section class="interest-profile-panel interest-profile-panel--telegram" aria-label="Подключить Telegram-бота">
          <div class="interest-profile-panel__header">
            <div>
              <h3>Подключить Telegram-бота</h3>
              <p>
                Нажмите «Открыть бота» и запустите его по одноразовой ссылке. Бот сам отправит команду
                подключения, а приложение сохранит Chat ID автоматически.
              </p>
              <p v-if="bindings.telegramConnectUrl" class="interest-profile-connect-note">
                Ссылка создана до {{ bindings.formatDateTime(bindings.telegramConnectExpiresAt) }}.
              </p>
            </div>
            <button class="primary-button" type="button" :disabled="bindings.telegramConnectLoading" @click="void bindings.connectTelegramBot()">
              {{ bindings.telegramConnectLoading ? 'Создаем...' : 'Открыть бота' }}
            </button>
          </div>
        </section>

        <section class="interest-profile-panel" aria-label="Создать профиль из текущих фильтров">
          <div class="interest-profile-panel__header">
            <div>
              <h3>Создать из текущих фильтров</h3>
              <p>{{ bindings.interestProfileSummary }}</p>
            </div>
            <button class="secondary-button" type="button" :disabled="bindings.interestProfilesSaving" @click="bindings.resetInterestProfileDraft">
              Обновить черновик
            </button>
          </div>

          <div class="app-dialog__grid">
            <label class="app-dialog__field">
              <span>Название</span>
              <input
                :ref="bindings.setInterestProfilesDialogInitialRef"
                v-model="bindings.interestProfileDraft.name"
                type="text"
                maxlength="160"
                placeholder="Например, BMW от 2 млн"
              />
            </label>
            <label class="app-dialog__field">
              <span>Минимальный рейтинг</span>
              <input v-model.number="bindings.interestProfileDraft.minRating" type="number" min="0" max="100" />
            </label>
            <label class="app-dialog__check">
              <input v-model="bindings.interestProfileDraft.telegramEnabled" type="checkbox" />
              <span>Telegram включен</span>
            </label>
            <label class="app-dialog__check">
              <input v-model="bindings.interestProfileDraft.isActive" type="checkbox" />
              <span>Профиль активен</span>
            </label>
          </div>

          <button class="primary-button" type="button" :disabled="bindings.interestProfilesSaving" @click="void bindings.createInterestProfileFromCurrentFilters()">
            Создать профиль
          </button>
        </section>

        <section class="interest-profile-panel" aria-label="Подключить сохраненный срез к Telegram">
          <div class="interest-profile-panel__header">
            <div>
              <h3>Подключить срез к Telegram</h3>
              <p>Выберите сохраненный срез. Backend превратит его фильтры в профиль интересов.</p>
            </div>
            <button class="secondary-button" type="button" :disabled="bindings.presetsLoading" @click="void bindings.loadPresets()">
              Обновить срезы
            </button>
          </div>

          <div class="interest-profile-preset-row">
            <label class="app-dialog__field">
              <span>Срез для Telegram</span>
              <select v-model="bindings.telegramPresetIdDraft" :disabled="!bindings.presets.length || bindings.interestProfilesSaving">
                <option value="">Выберите срез</option>
                <option v-for="preset in bindings.presets" :key="preset.id" :value="preset.id">
                  {{ preset.name }}
                </option>
              </select>
            </label>
            <button class="primary-button" type="button" :disabled="!bindings.telegramPresetIdDraft || bindings.interestProfilesSaving" @click="void bindings.createInterestProfileFromSelectedPreset()">
              Подключить
            </button>
          </div>
        </section>

        <section class="interest-profile-list" aria-label="Список профилей интересов">
          <div v-if="bindings.interestProfilesLoading" class="app-dialog__text">Загружаем профили...</div>
          <article v-else-if="!bindings.userInterestProfiles.length" class="interest-profile-card interest-profile-card--empty">
            <h3>Профилей пока нет</h3>
            <p>Создайте первый профиль из текущих фильтров каталога.</p>
          </article>
          <template v-else>
            <article v-for="profile in bindings.userInterestProfiles" :key="profile.id" class="interest-profile-card">
              <div>
                <h3>{{ profile.name }}</h3>
                <p>{{ bindings.interestProfileNote(profile) }}</p>
              </div>
              <div class="interest-profile-card__actions">
                <button class="secondary-button" type="button" @click="void bindings.toggleInterestProfileActive(profile)">
                  {{ profile.is_active ? 'Отключить' : 'Включить' }}
                </button>
                <button class="secondary-button" type="button" @click="void bindings.toggleInterestProfileTelegram(profile)">
                  {{ profile.telegram_enabled ? 'Telegram вкл.' : 'Telegram выкл.' }}
                </button>
                <button class="secondary-button" type="button" :disabled="!profile.source_filter_preset_id" @click="void bindings.refreshInterestProfileFromPreset(profile)">
                  Обновить из среза
                </button>
                <button class="secondary-button secondary-button--danger" type="button" @click="void bindings.removeInterestProfile(profile)">
                  Удалить
                </button>
              </div>
            </article>
          </template>
        </section>
      </div>

      <footer class="app-dialog__footer">
        <button class="secondary-button" type="button" @click="closeRoute">Закрыть</button>
      </footer>
    </div>
  </section>
</template>
