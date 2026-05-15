<script setup lang="ts">
import { onMounted } from 'vue'

const props = defineProps<{
  bindings: any
}>()

onMounted(() => {
  void props.bindings.loadPresets()
  void props.bindings.loadUserInterestProfiles()
})
</script>

<template>
  <section class="route-page route-page--interests" aria-labelledby="interest-profiles-route-title">
    <header class="route-page__header">
      <div>
        <span class="eyebrow">Персональные сигналы</span>
        <h1 id="interest-profiles-route-title">Профили интересов</h1>
        <p>
          Профиль интересов управляет тем, какие рейтинговые лоты попадут в персональные Telegram-уведомления.
          Срез таблицы остается только UI-фильтром.
        </p>
      </div>
    </header>

    <div v-if="bindings.interestProfilesError.value" class="error-banner">{{ bindings.interestProfilesError.value }}</div>

    <div class="interest-profiles-layout">
      <div class="interest-profiles-layout__sidebar">
        <section class="route-card interest-profile-panel interest-profile-panel--telegram" aria-label="Подключить Telegram-бота">
          <div class="interest-profile-panel__header">
            <div>
              <h3>Подключить Telegram-бота</h3>
              <p>
                Нажмите «Открыть бота» и запустите его по одноразовой ссылке. Бот сам отправит команду
                подключения, а приложение сохранит Chat ID автоматически.
              </p>
              <p v-if="bindings.telegramConnectUrl.value" class="interest-profile-connect-note">
                Ссылка создана до {{ bindings.formatDateTime(bindings.telegramConnectExpiresAt.value) }}.
              </p>
            </div>
            <button class="primary-button" type="button" :disabled="bindings.telegramConnectLoading.value" @click="void bindings.connectTelegramBot()">
              {{ bindings.telegramConnectLoading.value ? 'Создаем...' : 'Открыть бота' }}
            </button>
          </div>
        </section>

        <section class="route-card interest-profile-panel" aria-label="Подключить сохраненный срез к Telegram">
          <div class="interest-profile-panel__header">
            <div>
              <h3>Подключить срез к Telegram</h3>
              <p>Выберите сохраненный срез. Backend превратит его фильтры в профиль интересов.</p>
            </div>
            <button class="secondary-button" type="button" :disabled="bindings.presetsLoading.value" @click="void bindings.loadPresets()">
              Обновить срезы
            </button>
          </div>

          <div class="interest-profile-preset-row">
            <label class="app-dialog__field">
              <span>Срез для Telegram</span>
              <select v-model="bindings.telegramPresetIdDraft.value" :disabled="!bindings.presets.value.length || bindings.interestProfilesSaving.value">
                <option value="">Выберите срез</option>
                <option v-for="preset in bindings.presets.value" :key="preset.id" :value="preset.id">
                  {{ preset.name }}
                </option>
              </select>
            </label>
            <button class="primary-button" type="button" :disabled="!bindings.telegramPresetIdDraft.value || bindings.interestProfilesSaving.value" @click="void bindings.createInterestProfileFromSelectedPreset()">
              Подключить
            </button>
          </div>
        </section>
      </div>

      <section class="route-card interest-profile-list" aria-label="Список профилей интересов">
        <div v-if="bindings.interestProfilesLoading.value" class="route-page__state">Загружаем профили...</div>
        <article v-else-if="!bindings.userInterestProfiles.value.length" class="interest-profile-card interest-profile-card--empty">
          <h3>Профилей пока нет</h3>
          <p>Создайте первый профиль из текущих фильтров каталога.</p>
        </article>
        <template v-else>
          <article v-for="profile in bindings.userInterestProfiles.value" :key="profile.id" class="interest-profile-card">
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
  </section>
</template>
