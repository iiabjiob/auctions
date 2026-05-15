<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTabsController } from '@affino/tabs-vue'
import {
  fetchAnalysisConfig,
  updateAnalysisConfig,
  type AnalysisConfigSource,
} from '@/api/analysisConfig'
import type {
  AnalysisConfigResponse,
  OwnerScoringProfile,
  ScoringDimensionWeights,
} from '@/app/types'

const props = defineProps<{
  bindings?: unknown
}>()

type AnalysisConfigDraftRule = {
  id: number
  category: string
  keywordsText: string
}

type AnalysisConfigDraft = {
  categoryRules: AnalysisConfigDraftRule[]
  exclusionKeywordsText: string
  highRiskKeywordsText: string
  mediumRiskKeywordsText: string
  mediumRiskCategoriesText: string
}

type AnalysisTabState = {
  config: AnalysisConfigResponse | null
  draft: AnalysisConfigDraft
  loaded: boolean
  loading: boolean
  saving: boolean
  error: string
}

const sourceLabels: Record<AnalysisConfigSource, string> = {
  auction: 'Аукционы',
  procurement: 'Тендеры',
}

const sourceHints: Record<AnalysisConfigSource, string> = {
  auction: 'Категории, исключения и юридический риск для банкротных торгов.',
  procurement: 'Категории и стоп-слова для закупок.',
}

const sourceTabLabels: Record<AnalysisConfigSource, string> = {
  auction: 'Аукционы',
  procurement: 'Тендеры',
}

const route = useRoute()
const router = useRouter()
const initialSource = parseSource(route.query.source)
const tabs = useTabsController<AnalysisConfigSource>(initialSource)
const activeSource = computed(() => tabs.state.value.value ?? initialSource)
let ruleSeed = 0

const states = reactive<Record<AnalysisConfigSource, AnalysisTabState>>({
  auction: createState(),
  procurement: createState(),
})

const activeState = computed(() => states[activeSource.value])
const activeConfig = computed(() => activeState.value.config)
const isAuctionTab = computed(() => activeSource.value === 'auction')
const activeUpdatedAt = computed(() => activeState.value.config?.updated_at ?? null)
const activeLoading = computed(() => activeState.value.loading)
const activeSaving = computed(() => activeState.value.saving)
const activeError = computed(() => activeState.value.error)
const activeTitle = computed(() => `${sourceLabels[activeSource.value]} · правила категорий`)
const activeDescription = computed(() => sourceHints[activeSource.value])
const hasCategories = computed(() => activeState.value.draft.categoryRules.length > 0)

function createState(): AnalysisTabState {
  return {
    config: null,
    draft: createEmptyDraft(),
    loaded: false,
    loading: false,
    saving: false,
    error: '',
  }
}

function createEmptyDraft(): AnalysisConfigDraft {
  return {
    categoryRules: [],
    exclusionKeywordsText: '',
    highRiskKeywordsText: '',
    mediumRiskKeywordsText: '',
    mediumRiskCategoriesText: '',
  }
}

function createDraftRule(category = '', keywords: string[] = []): AnalysisConfigDraftRule {
  ruleSeed += 1
  return {
    id: ruleSeed,
    category,
    keywordsText: keywords.join('\n'),
  }
}

function resetDraft(source: AnalysisConfigSource) {
  const draft = states[source].draft
  draft.categoryRules = []
  draft.exclusionKeywordsText = ''
  draft.highRiskKeywordsText = ''
  draft.mediumRiskKeywordsText = ''
  draft.mediumRiskCategoriesText = ''
}

function applyConfigToDraft(source: AnalysisConfigSource, config: AnalysisConfigResponse) {
  const draft = states[source].draft
  draft.categoryRules = config.category_rules.map((rule) => createDraftRule(rule.category, rule.keywords))
  draft.exclusionKeywordsText = config.exclusion_keywords.join('\n')
  draft.highRiskKeywordsText = config.legal_risk_rules.high_keywords.join('\n')
  draft.mediumRiskKeywordsText = config.legal_risk_rules.medium_keywords.join('\n')
  draft.mediumRiskCategoriesText = config.legal_risk_rules.medium_categories.join('\n')
}

function splitLines(value: string) {
  const seen = new Set<string>()
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter((item) => {
      const normalized = item.toLowerCase()
      if (!normalized || seen.has(normalized)) return false
      seen.add(normalized)
      return true
    })
}

function buildPayload(source: AnalysisConfigSource) {
  const state = states[source]
  const config = state.config
  return {
    category_rules: state.draft.categoryRules
      .map((rule) => ({
        category: rule.category.trim(),
        keywords: splitLines(rule.keywordsText),
      }))
      .filter((rule) => rule.category),
    exclusion_keywords: splitLines(state.draft.exclusionKeywordsText),
    legal_risk_rules: {
      high_keywords: splitLines(state.draft.highRiskKeywordsText),
      medium_keywords: splitLines(state.draft.mediumRiskKeywordsText),
      medium_categories: splitLines(state.draft.mediumRiskCategoriesText),
    },
    owner_profile: config?.owner_profile ?? defaultOwnerProfile(),
    dimension_weights: config?.dimension_weights ?? defaultDimensionWeights(),
  }
}

function defaultOwnerProfile(): OwnerScoringProfile {
  return {
    target_regions: [],
    target_categories: [],
    min_budget: null,
    max_budget: null,
    minimum_roi: null,
    minimum_market_discount: null,
    excluded_terms: [],
    discouraged_terms: [],
    max_delivery_distance_km: null,
    allow_dismantling: true,
    legal_risk_tolerance: 'medium',
    require_documents: false,
    require_photos: false,
  }
}

function defaultDimensionWeights(): ScoringDimensionWeights {
  return {
    economics: 1,
    risk: 1,
    urgency: 1,
    data_quality: 1,
    operational_readiness: 1,
    owner_fit: 1,
    manual_intent: 1,
  }
}

function parseSource(value: unknown): AnalysisConfigSource {
  return value === 'procurement' ? 'procurement' : 'auction'
}

async function syncRoute(source: AnalysisConfigSource) {
  if (parseSource(route.query.source) === source) return
  await router.replace({ query: { ...route.query, source } })
}

async function loadSourceConfig(source: AnalysisConfigSource, force = false) {
  const state = states[source]
  if (state.loading || (state.loaded && !force)) return
  state.loading = true
  state.error = ''
  try {
    const config = await fetchAnalysisConfig(source)
    state.config = config
    applyConfigToDraft(source, config)
    state.loaded = true
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Не удалось загрузить конфиг анализа.'
  } finally {
    state.loading = false
  }
}

async function saveSourceConfig(source: AnalysisConfigSource) {
  const state = states[source]
  state.saving = true
  state.error = ''
  try {
    const config = await updateAnalysisConfig(source, buildPayload(source))
    state.config = config
    applyConfigToDraft(source, config)
    state.loaded = true
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Не удалось сохранить конфиг анализа.'
  } finally {
    state.saving = false
  }
}

function addCategoryRule(source: AnalysisConfigSource) {
  states[source].draft.categoryRules = [...states[source].draft.categoryRules, createDraftRule()]
}

function removeCategoryRule(source: AnalysisConfigSource, ruleId: number) {
  states[source].draft.categoryRules = states[source].draft.categoryRules.filter((rule) => rule.id !== ruleId)
}

watch(
  () => route.query.source,
  (value) => {
    const next = parseSource(value)
    if (tabs.state.value.value !== next) {
      tabs.select(next)
    }
  },
  { immediate: true },
)

watch(
  activeSource,
  (source) => {
    void syncRoute(source)
    void loadSourceConfig(source)
  },
  { immediate: true },
)

function switchTab(source: AnalysisConfigSource) {
  tabs.select(source)
}
</script>

<template>
  <section class="route-page route-page--analysis" aria-labelledby="analysis-config-route-title">
    <header class="route-page__header">
      <div>
        <span class="eyebrow">Анализ</span>
        <h1 id="analysis-config-route-title">{{ activeTitle }}</h1>
        <p>{{ activeDescription }}</p>
      </div>
      <div class="route-page__actions">
        <button
          class="primary-button"
          type="button"
          :disabled="activeLoading || activeSaving"
          @click="void saveSourceConfig(activeSource)"
        >
          {{ activeSaving ? 'Сохраняю' : 'Сохранить конфиг' }}
        </button>
      </div>
    </header>

    <div class="analysis-config-tabs" role="tablist" aria-label="Вид анализа">
      <button
        v-for="option in (['auction', 'procurement'] as const)"
        :key="option"
        type="button"
        class="analysis-config-tabs__tab"
        :class="{ 'analysis-config-tabs__tab--active': tabs.isSelected(option) }"
        role="tab"
        :aria-selected="tabs.isSelected(option)"
        @click="switchTab(option)"
      >
        {{ sourceTabLabels[option] }}
      </button>
    </div>

    <p v-if="activeUpdatedAt" class="route-page__meta">
      Последнее обновление: {{ activeUpdatedAt }}
    </p>
    <p v-if="activeError" class="error-banner error-banner--inline">{{ activeError }}</p>

    <div v-if="activeLoading" class="route-page__state">Загружаю актуальный конфиг анализа</div>
    <template v-else>
      <div class="analysis-config-layout" :class="{ 'analysis-config-layout--compact': !isAuctionTab }">
        <section class="analysis-config-section route-card analysis-config-section--categories">
          <div class="analysis-config-section__header">
            <div>
              <span class="eyebrow">Категории</span>
              <p class="analysis-config-section__hint">Порядок важен: категория назначается по первому совпавшему правилу.</p>
            </div>
            <button class="secondary-button" type="button" @click="addCategoryRule(activeSource)">Добавить категорию</button>
          </div>

          <div v-if="hasCategories" class="analysis-config-editor">
            <article
              v-for="(rule, index) in activeState.draft.categoryRules"
              :key="rule.id"
              class="analysis-config-rule"
            >
              <div class="analysis-config-rule__row">
                <label class="app-dialog__field">
                  <span>Категория</span>
                  <input
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
                  @click="removeCategoryRule(activeSource, rule.id)"
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
            <span>{{ isAuctionTab ? 'Исключения' : 'Стоп-слова' }}</span>
            <textarea
              v-model="activeState.draft.exclusionKeywordsText"
              rows="7"
              :placeholder="isAuctionTab ? 'Слова или фразы, по которым лот исключается из анализа' : 'Слова и фразы для исключения из тендерного анализа'"
            ></textarea>
          </label>

          <template v-if="isAuctionTab">
            <label class="app-dialog__field">
              <span>Высокий юридический риск</span>
              <textarea
                v-model="activeState.draft.highRiskKeywordsText"
                rows="7"
                placeholder="Маркер высокого риска, одно значение на строку"
              ></textarea>
            </label>
            <label class="app-dialog__field">
              <span>Средний юридический риск</span>
              <textarea
                v-model="activeState.draft.mediumRiskKeywordsText"
                rows="7"
                placeholder="Маркер среднего риска, одно значение на строку"
              ></textarea>
            </label>
            <label class="app-dialog__field">
              <span>Категории среднего риска</span>
              <textarea
                v-model="activeState.draft.mediumRiskCategoriesText"
                rows="7"
                placeholder="Например, Земля и базы"
              ></textarea>
            </label>
          </template>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.analysis-config-tabs {
  display: flex;
  gap: 8px;
  padding: 4px;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface-muted);
}

.analysis-config-tabs__tab {
  border: 0;
  border-radius: 12px;
  padding: 10px 14px;
  color: var(--color-text-muted);
  background: transparent;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease, box-shadow 120ms ease;
}

.analysis-config-tabs__tab--active {
  color: var(--color-text-strong);
  background: var(--color-surface);
  box-shadow: 0 6px 14px rgba(37, 52, 71, 0.08);
}

.analysis-config-layout--compact {
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.9fr);
}

@media (max-width: 900px) {
  .analysis-config-tabs {
    flex-wrap: wrap;
  }
}
</style>
