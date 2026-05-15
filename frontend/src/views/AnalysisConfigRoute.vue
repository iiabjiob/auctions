<script setup lang="ts">
import { onMounted } from 'vue'

const props = defineProps<{
  bindings: any
}>()

onMounted(() => {
  void props.bindings.loadAnalysisConfig()
})
</script>

<template>
  <section class="route-page route-page--analysis" aria-labelledby="analysis-config-route-title">
    <header class="route-page__header">
      <div>
        <span class="eyebrow">Анализ</span>
        <h1 id="analysis-config-route-title">Правила категорий и риска</h1>
        <p>
          Здесь редактируются категории, исключения и правила юридического риска без изменения backend-кода.
        </p>
      </div>
      <div class="route-page__actions">
        <button class="primary-button" type="button" :disabled="bindings.analysisConfigLoading.value || bindings.analysisConfigSaving.value" @click="void bindings.submitAnalysisConfigDialog()">
          {{ bindings.analysisConfigSaving.value ? 'Сохраняю' : 'Сохранить конфиг' }}
        </button>
      </div>
    </header>

    <p v-if="bindings.analysisConfigUpdatedAt.value" class="route-page__meta">
      Последнее обновление: {{ bindings.analysisConfigUpdatedAt.value }}
    </p>
    <p v-if="bindings.analysisConfigError.value" class="error-banner error-banner--inline">{{ bindings.analysisConfigError.value }}</p>

    <div v-if="bindings.analysisConfigLoading.value" class="route-page__state">Загружаю актуальный конфиг анализа</div>
    <template v-else>
      <div class="analysis-config-layout">
        <section class="analysis-config-section route-card analysis-config-section--categories">
          <div class="analysis-config-section__header">
            <div>
              <span class="eyebrow">Категории</span>
              <p class="analysis-config-section__hint">Порядок важен: категория назначается по первому совпавшему правилу.</p>
            </div>
            <button class="secondary-button" type="button" @click="bindings.addAnalysisConfigCategoryRule">Добавить категорию</button>
          </div>

          <div v-if="bindings.analysisConfigDraft.categoryRules.length" class="analysis-config-editor">
            <article
              v-for="(rule, index) in bindings.analysisConfigDraft.categoryRules"
              :key="rule.id"
              class="analysis-config-rule"
            >
              <div class="analysis-config-rule__row">
                <label class="app-dialog__field">
                  <span>Категория</span>
                  <input
                    :ref="index === 0 ? bindings.setAnalysisConfigInitialRef : undefined"
                    v-model="rule.category"
                    type="text"
                    maxlength="160"
                    placeholder="Например, Спецтехника"
                  />
                </label>
                <button
                  class="icon-button analysis-config-rule__remove"
                  type="button"
                  aria-label="Удалить категорию"
                  @click="bindings.removeAnalysisConfigCategoryRule(rule.id)"
                >
                  ×
                </button>
              </div>
              <label class="app-dialog__field">
                <span>Ключевые слова</span>
                <textarea
                  v-model="rule.keywordsText"
                  rows="5"
                  placeholder="Одно ключевое слово или фраза на строку"
                ></textarea>
              </label>
            </article>
          </div>
          <div v-else class="detail-muted">Категории пока не заданы. Добавь хотя бы одно правило.</div>
        </section>

        <section class="analysis-config-section analysis-config-section--grid route-card">
          <label class="app-dialog__field">
            <span>Исключения</span>
            <textarea
              :ref="bindings.analysisConfigDraft.categoryRules.length === 0 ? bindings.setAnalysisConfigInitialRef : undefined"
              v-model="bindings.analysisConfigDraft.exclusionKeywordsText"
              rows="7"
              placeholder="Слова или фразы, по которым лот исключается из анализа"
            ></textarea>
          </label>
          <label class="app-dialog__field">
            <span>Высокий юридический риск</span>
            <textarea
              v-model="bindings.analysisConfigDraft.highRiskKeywordsText"
              rows="7"
              placeholder="Маркер высокого риска, одно значение на строку"
            ></textarea>
          </label>
          <label class="app-dialog__field">
            <span>Средний юридический риск</span>
            <textarea
              v-model="bindings.analysisConfigDraft.mediumRiskKeywordsText"
              rows="7"
              placeholder="Маркер среднего риска, одно значение на строку"
            ></textarea>
          </label>
          <label class="app-dialog__field">
            <span>Категории среднего риска</span>
            <textarea
              v-model="bindings.analysisConfigDraft.mediumRiskCategoriesText"
              rows="7"
              placeholder="Например, Земля и базы"
            ></textarea>
          </label>
        </section>
      </div>
    </template>
  </section>
</template>
