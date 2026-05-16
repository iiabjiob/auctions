<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppTooltip from './AppTooltip.vue'
import {
  fetchSourceDiagnostics,
  type SourceDiagnosticsKind,
  type SourceDiagnosticsRange,
  type SourceDiagnosticsResponse,
} from '@/api/sourceDiagnostics'

defineProps<{
  mobileRailOpen: boolean
}>()

const emit = defineEmits<{
  (event: 'toggle-mobile-rail'): void
}>()

const rangeOptions: Array<{ label: string; value: SourceDiagnosticsRange }> = [
  { label: 'День', value: 'day' },
  { label: 'Неделя', value: 'week' },
  { label: 'Месяц', value: 'month' },
  { label: '3 месяца', value: '3months' },
  { label: 'Все время', value: 'all' },
]

const kindOptions: Array<{ label: string; value: SourceDiagnosticsKind }> = [
  { label: 'Все', value: 'all' },
  { label: 'Аукционы', value: 'auction' },
  { label: 'Тендеры', value: 'procurement' },
]

const kindLabels: Record<SourceDiagnosticsKind, string> = {
  all: 'Все потоки',
  auction: 'Аукционы',
  procurement: 'Тендеры',
}

const route = useRoute()
const router = useRouter()

const selectedRange = ref<SourceDiagnosticsRange>('day')
const selectedKind = ref<SourceDiagnosticsKind>('all')
const selectedSource = ref('all')
const diagnostics = ref<SourceDiagnosticsResponse | null>(null)
const isLoading = ref(false)
const errorMessage = ref<string | null>(null)
const isHydrated = ref(false)
const copyState = ref<'idle' | 'copied' | 'error'>('idle')
let copyResetTimer: number | null = null

const chartBuckets = computed(() => diagnostics.value?.timeline ?? [])
const maxTimelineRequests = computed(() => Math.max(1, ...chartBuckets.value.map((bucket) => bucket.request_count)))
const prettyJson = computed(() => JSON.stringify(diagnostics.value, null, 2))

const sourceOptions = computed(() => {
  const sources = diagnostics.value?.sources ?? []
  const filteredSources = selectedKind.value === 'all' ? sources : sources.filter((source) => source.kind === selectedKind.value)

  return [
    { label: 'Все площадки', value: 'all' },
    ...filteredSources.map((source) => ({
      label: selectedKind.value === 'all' ? `${source.title} · ${kindLabels[source.kind]}` : source.title,
      value: source.code,
      source,
    })),
  ]
})

const selectedSourceLabel = computed(() => {
  if (selectedSource.value === 'all') return 'Все площадки'
  const source = (diagnostics.value?.sources ?? []).find((item) => item.code === selectedSource.value)
  if (!source) return selectedSource.value
  return `${source.title} · ${kindLabels[source.kind]}`
})

const sourceGroups = computed(() => {
  const sources = diagnostics.value?.sources ?? []
  const kinds = selectedKind.value === 'all' ? (['auction', 'procurement'] as const) : ([selectedKind.value] as const)

  return kinds
    .map((kind) => ({
      kind,
      label: kindLabels[kind],
      sources: sources.filter((source) => source.kind === kind),
    }))
    .filter((group) => group.sources.length > 0)
})

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB']
  let next = value / 1024
  for (const unit of units) {
    if (next < 1024) return `${next.toFixed(next >= 10 ? 1 : 2)} ${unit}`
    next /= 1024
  }
  return `${next.toFixed(1)} TB`
}

function formatDuration(value: number | null) {
  if (value === null) return '—'
  if (value < 1000) return `${Math.round(value)} ms`
  return `${(value / 1000).toFixed(2)} s`
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatBucket(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatRouteQuery() {
  return {
    range: selectedRange.value,
    kind: selectedKind.value,
    source: selectedSource.value === 'all' ? undefined : selectedSource.value,
  }
}

function syncStateFromRoute() {
  const range = route.query.range
  const kind = route.query.kind
  const source = route.query.source

  if (range === 'day' || range === 'week' || range === 'month' || range === '3months' || range === 'all') {
    selectedRange.value = range
  }

  if (kind === 'all' || kind === 'auction' || kind === 'procurement') {
    selectedKind.value = kind
  }

  if (typeof source === 'string' && source.trim()) {
    selectedSource.value = source
  }
}

async function syncRoute() {
  await router.replace({ query: formatRouteQuery() })
}

async function loadDiagnostics() {
  isLoading.value = true
  errorMessage.value = null
  try {
    diagnostics.value = await fetchSourceDiagnostics(selectedRange.value, {
      kind: selectedKind.value,
      source: selectedSource.value === 'all' ? null : selectedSource.value,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить диагностику.'
  } finally {
    isLoading.value = false
  }
}

async function copyJsonToClipboard() {
  if (!prettyJson.value || prettyJson.value === 'null') {
    copyState.value = 'error'
    return
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(prettyJson.value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = prettyJson.value
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.top = '-9999px'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      document.body.removeChild(textarea)
      if (!copied) throw new Error('copy_failed')
    }

    copyState.value = 'copied'
    if (copyResetTimer !== null) {
      window.clearTimeout(copyResetTimer)
    }
    copyResetTimer = window.setTimeout(() => {
      copyState.value = 'idle'
      copyResetTimer = null
    }, 1600)
  } catch {
    copyState.value = 'error'
  }
}

async function syncAndLoad() {
  await syncRoute()
  await loadDiagnostics()
}

function isTimelineBarActive(bucket: SourceDiagnosticsResponse['timeline'][number]) {
  return bucket.request_count > 0
}

onMounted(async () => {
  syncStateFromRoute()
  isHydrated.value = true
  await loadDiagnostics()
})

onUnmounted(() => {
  if (copyResetTimer !== null) {
    window.clearTimeout(copyResetTimer)
    copyResetTimer = null
  }
})

watch(selectedRange, () => {
  if (!isHydrated.value) return
  void syncAndLoad()
})

watch(selectedSource, () => {
  if (!isHydrated.value) return
  void syncAndLoad()
})

watch(selectedKind, () => {
  if (!isHydrated.value) return
  if (selectedSource.value !== 'all') {
    selectedSource.value = 'all'
    return
  }
  void syncAndLoad()
})
</script>

<template>
  <section class="source-diagnostics" aria-label="Диагностика обмена с площадками">
    <div class="source-diagnostics__main">
      <header class="source-diagnostics__header">
        <div class="source-diagnostics__header-title">
          <button
            class="app-mobile-menu-button"
            type="button"
            aria-label="Открыть меню"
            :aria-expanded="mobileRailOpen"
            @click="emit('toggle-mobile-rail')"
          >
            <span></span>
            <span></span>
            <span></span>
          </button>

          <span class="eyebrow">Диагностика · {{ kindLabels[selectedKind] }}</span>
          <h1>Обмен с площадками</h1>
          <p>
            {{ selectedSourceLabel }} · {{ formatDate(diagnostics?.from_at ?? null) }} — {{ formatDate(diagnostics?.to_at ?? null) }}
          </p>
        </div>

        <div class="source-diagnostics__filters">
          <div class="source-diagnostics__ranges" aria-label="Диапазон">
            <button
              v-for="option in rangeOptions"
              :key="option.value"
              type="button"
              :class="{ 'source-diagnostics__range--active': selectedRange === option.value }"
              @click="selectedRange = option.value"
            >
              {{ option.label }}
            </button>
          </div>

          <div class="source-diagnostics__kinds" aria-label="Разрез">
            <button
              v-for="option in kindOptions"
              :key="option.value"
              type="button"
              :class="{ 'source-diagnostics__kind--active': selectedKind === option.value }"
              @click="selectedKind = option.value"
            >
              {{ option.label }}
            </button>
          </div>

          <div class="source-diagnostics__sources-filter" aria-label="Площадка">
            <button
              v-for="option in sourceOptions"
              :key="option.value"
              type="button"
              :class="{ 'source-diagnostics__source-filter--active': selectedSource === option.value }"
              @click="selectedSource = option.value"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </header>

      <p v-if="errorMessage" class="source-diagnostics__error">{{ errorMessage }}</p>

      <div v-if="diagnostics" class="source-diagnostics__summary">
        <article>
          <span>Запросы</span>
          <strong>{{ diagnostics.totals.request_count }}</strong>
        </article>
        <article>
          <span>Входящий трафик</span>
          <strong>{{ formatBytes(diagnostics.totals.inbound_bytes) }}</strong>
        </article>
        <article>
          <span>Исходящий трафик</span>
          <strong>{{ formatBytes(diagnostics.totals.outbound_bytes) }}</strong>
        </article>
        <article>
          <span>Ошибки</span>
          <strong>{{ diagnostics.totals.error_count }}</strong>
        </article>
        <article>
          <span>Среднее время</span>
          <strong>{{ formatDuration(diagnostics.totals.average_duration_ms) }}</strong>
        </article>
      </div>

      <div class="source-diagnostics__chart" aria-label="График запросов">
        <AppTooltip
          v-for="bucket in chartBuckets"
          :key="bucket.bucket_start"
          :id="`source-diagnostics-bar-${bucket.bucket_start}`"
          trigger-tag="div"
          trigger-class="source-diagnostics__bar-cell"
          :trigger-attrs="{
            role: 'img',
            'aria-label': `${formatBucket(bucket.bucket_start)}: ${bucket.request_count} запросов`,
          }"
          surface-class="source-diagnostics-chart-tooltip"
          placement="top"
          align="center"
          :gutter="10"
          :open-delay="160"
        >
          <template #trigger>
            <span class="source-diagnostics__bar-track">
              <span
                class="source-diagnostics__bar"
                :class="{ 'source-diagnostics__bar--empty': !isTimelineBarActive(bucket) }"
                :style="{ height: `${Math.max(8, (bucket.request_count / maxTimelineRequests) * 160)}px` }"
              >
                <span>{{ bucket.request_count }}</span>
              </span>
            </span>
          </template>

          <strong>{{ formatBucket(bucket.bucket_start) }}</strong>
          <dl class="source-diagnostics__chart-tooltip-grid">
            <div>
              <dt>Запросы</dt>
              <dd>{{ bucket.request_count }}</dd>
            </div>
            <div>
              <dt>Ошибки</dt>
              <dd>{{ bucket.error_count }}</dd>
            </div>
            <div>
              <dt>Входящий</dt>
              <dd>{{ formatBytes(bucket.inbound_bytes) }}</dd>
            </div>
            <div>
              <dt>Исходящий</dt>
              <dd>{{ formatBytes(bucket.outbound_bytes) }}</dd>
            </div>
          </dl>
        </AppTooltip>
        <p v-if="!isLoading && !(diagnostics?.timeline.length)" class="source-diagnostics__empty">Данных за выбранный период пока нет.</p>
      </div>

      <section v-if="diagnostics" class="source-diagnostics__source-groups">
        <article v-for="group in sourceGroups" :key="group.kind" class="source-diagnostics__source-group">
          <header class="source-diagnostics__source-group-header">
            <div>
              <span class="eyebrow">{{ group.label }}</span>
              <h2>{{ group.label }}</h2>
            </div>
            <strong>{{ group.sources.length }} площадок</strong>
          </header>

          <div class="source-diagnostics__sources">
            <article v-for="source in group.sources" :key="source.kind + ':' + source.code" class="source-diagnostics__source">
              <header>
                <div>
                  <span class="source-diagnostics__source-kind">{{ kindLabels[source.kind] }}</span>
                  <h3>{{ source.title }}</h3>
                  <a :href="source.website" target="_blank" rel="noreferrer">{{ source.website }}</a>
                </div>
                <strong>{{ source.totals.request_count }} запросов</strong>
              </header>

              <dl>
                <div>
                  <dt>Входящий</dt>
                  <dd>{{ formatBytes(source.totals.inbound_bytes) }}</dd>
                </div>
                <div>
                  <dt>Исходящий</dt>
                  <dd>{{ formatBytes(source.totals.outbound_bytes) }}</dd>
                </div>
                <div>
                  <dt>Ошибки</dt>
                  <dd>{{ source.totals.error_count }}</dd>
                </div>
                <div>
                  <dt>Среднее</dt>
                  <dd>{{ formatDuration(source.totals.average_duration_ms) }}</dd>
                </div>
              </dl>

              <div class="source-diagnostics__table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Операция</th>
                      <th>Запросы</th>
                      <th>Входящий</th>
                      <th>Исходящий</th>
                      <th>Среднее</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="operation in source.operations" :key="operation.operation">
                      <td>{{ operation.operation }}</td>
                      <td>{{ operation.request_count }}</td>
                      <td>{{ formatBytes(operation.inbound_bytes) }}</td>
                      <td>{{ formatBytes(operation.outbound_bytes) }}</td>
                      <td>{{ formatDuration(operation.average_duration_ms) }}</td>
                    </tr>
                    <tr v-if="!source.operations.length">
                      <td colspan="5">Нет запросов за выбранный период</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </article>
          </div>
        </article>
      </section>

      <p v-if="diagnostics && !sourceGroups.length" class="source-diagnostics__empty source-diagnostics__empty--card">
        Нет данных для выбранного разреза.
      </p>
    </div>

    <section class="source-diagnostics__json" aria-label="JSON">
      <header>
        <div class="source-diagnostics__json-title">
          <h2>JSON</h2>
          <p>Полный ответ диагностики</p>
        </div>
        <div class="source-diagnostics__json-actions">
          <button type="button" @click="copyJsonToClipboard" :disabled="!diagnostics || isLoading">
            {{ copyState === 'copied' ? 'Скопировано' : copyState === 'error' ? 'Не скопировано' : 'Copy to clipboard' }}
          </button>
          <button type="button" @click="loadDiagnostics" :disabled="isLoading">
            {{ isLoading ? 'Обновление...' : 'Обновить' }}
          </button>
        </div>
      </header>
      <pre>{{ prettyJson }}</pre>
    </section>
  </section>
</template>

<style scoped>
.source-diagnostics {
  display: grid;
  grid-row: 1 / -1;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 42vw);
  min-height: 100%;
  height: 100%;
  padding: 24px;
  gap: 16px;
  color: #17211b;
  background:
    radial-gradient(circle at top left, rgba(75, 127, 94, 0.12), transparent 36%),
    linear-gradient(180deg, #f5f7f4 0%, #eef3ef 100%);
  overflow: hidden;
}

.source-diagnostics__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 8px;
  -webkit-overflow-scrolling: touch;
}

.source-diagnostics__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.source-diagnostics__header h1 {
  margin: 4px 0;
  font-size: 28px;
}

.source-diagnostics__header-title {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.source-diagnostics__header p {
  margin: 0;
  color: #607067;
}

.source-diagnostics__filters {
  display: grid;
  gap: 8px;
  justify-items: end;
  min-width: 0;
}

.source-diagnostics__ranges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.source-diagnostics__kinds,
.source-diagnostics__sources-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.source-diagnostics__ranges button,
.source-diagnostics__kinds button,
.source-diagnostics__sources-filter button,
.source-diagnostics__json button {
  border: 1px solid #cbd6cf;
  border-radius: 6px;
  padding: 8px 10px;
  color: #26352c;
  background: #ffffff;
  cursor: pointer;
  transition:
    transform 160ms ease,
    border-color 160ms ease,
    box-shadow 160ms ease,
    background-color 160ms ease,
    color 160ms ease;
  max-width: 100%;
}

.source-diagnostics__ranges button:hover,
.source-diagnostics__kinds button:hover,
.source-diagnostics__sources-filter button:hover,
.source-diagnostics__json button:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(37, 52, 71, 0.08);
}

.source-diagnostics__range--active {
  border-color: #346f4b !important;
  color: #ffffff !important;
  background: #346f4b !important;
}

.source-diagnostics__kind--active,
.source-diagnostics__source-filter--active {
  border-color: #4f7f62 !important;
  color: #14311f !important;
  background: #e6f4eb !important;
}

.source-diagnostics__summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(140px, 1fr));
  gap: 8px;
}

.source-diagnostics__summary article,
.source-diagnostics__source-group,
.source-diagnostics__source,
.source-diagnostics__json {
  border: 1px solid #d8e0dc;
  border-radius: 8px;
  background: #ffffff;
}

.source-diagnostics__summary article {
  padding: 12px;
}

.source-diagnostics__summary span,
.source-diagnostics__source dt {
  display: block;
  color: #66766d;
  font-size: 12px;
}

.source-diagnostics__summary strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
}

.source-diagnostics__chart,
.source-diagnostics__source-group {
  border: 1px solid #d8e0dc;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 12px 28px rgba(37, 52, 71, 0.05);
}

.source-diagnostics__chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  min-height: 220px;
  padding: 26px 16px 14px;
  overflow-x: auto;
  overflow-y: visible;
}

.source-diagnostics__bar-cell {
  position: relative;
  display: flex;
  align-items: flex-end;
  flex: 1 0 24px;
  min-width: 24px;
  height: 180px;
}

.source-diagnostics__bar-track {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.source-diagnostics__bar {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  width: 100%;
  min-width: 18px;
  border-radius: 9px 9px 4px 4px;
  background:
    linear-gradient(180deg, #6aa57e 0%, #4a7c5e 100%);
  box-shadow: 0 10px 22px rgba(74, 124, 94, 0.28);
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    filter 180ms ease;
}

.source-diagnostics__bar-cell:hover .source-diagnostics__bar,
.source-diagnostics__bar-cell:focus-visible .source-diagnostics__bar {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(74, 124, 94, 0.34);
  filter: brightness(1.04);
}

.source-diagnostics__bar--empty {
  opacity: 0.45;
}

.source-diagnostics__bar span {
  position: absolute;
  top: -22px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  font-weight: 700;
  color: #2d4036;
  white-space: nowrap;
}

.source-diagnostics__chart-tooltip-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 10px;
  margin: 0;
}

.source-diagnostics__chart-tooltip-grid div {
  display: grid;
  gap: 2px;
}

.source-diagnostics__chart-tooltip-grid dt {
  color: var(--color-tooltip-text-muted);
  font-size: 11px;
}

.source-diagnostics__chart-tooltip-grid dd {
  margin: 0;
  color: var(--color-tooltip-accent);
  font-weight: 700;
}

.source-diagnostics__source-groups {
  display: grid;
  gap: 12px;
}

.source-diagnostics__source-group {
  display: grid;
  gap: 12px;
  padding: 14px;
  min-width: 0;
}

.source-diagnostics__source-group-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.source-diagnostics__source-group-header h2 {
  margin: 4px 0 0;
  font-size: 18px;
}

.source-diagnostics__source-kind {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  color: #4a7c5e;
  background: #e8f4ec;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.source-diagnostics__sources {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(390px, 1fr));
  gap: 12px;
}

.source-diagnostics__source {
  padding: 14px;
  min-width: 0;
}

.source-diagnostics__source header,
.source-diagnostics__json header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.source-diagnostics__json-title {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.source-diagnostics__json-title p {
  margin: 0;
  color: #607067;
  font-size: 12px;
}

.source-diagnostics__json-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.source-diagnostics__source h2,
.source-diagnostics__source h3,
.source-diagnostics__json h2 {
  margin: 0;
  font-size: 18px;
}

.source-diagnostics__source a {
  color: #346f4b;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.source-diagnostics__source dl {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin: 14px 0;
}

.source-diagnostics__source dd {
  margin: 2px 0 0;
  font-weight: 700;
}

.source-diagnostics__table-scroll {
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
}

.source-diagnostics__source table {
  min-width: 560px;
  width: max-content;
  border-collapse: collapse;
  font-size: 13px;
}

.source-diagnostics__source th,
.source-diagnostics__source td {
  padding: 8px;
  border-top: 1px solid #e4ebe7;
  text-align: left;
}

.source-diagnostics__json {
  padding: 14px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.source-diagnostics__json pre {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 6px;
  color: #d7f5df;
  background: #162019;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.source-diagnostics__error {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #efb4ac;
  border-radius: 6px;
  color: #8b2f25;
  background: #fff1ef;
}

.source-diagnostics__empty {
  margin: auto;
  color: #607067;
}

.source-diagnostics__empty--card {
  padding: 14px 16px;
  border: 1px solid #d8e0dc;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 12px 28px rgba(37, 52, 71, 0.05);
}

@media (max-width: 900px) {
  .source-diagnostics {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 100%;
    overflow: auto;
    padding: 16px;
    -webkit-overflow-scrolling: touch;
  }

  .source-diagnostics__main {
    overflow: visible;
  }

  .source-diagnostics__header {
    flex-direction: column;
  }

  .source-diagnostics__header-title {
    width: 100%;
  }

  .source-diagnostics__header h1 {
    font-size: 24px;
  }

  .source-diagnostics__header .app-mobile-menu-button {
    margin-bottom: 6px;
  }

  .source-diagnostics__header p {
    overflow-wrap: anywhere;
  }

  .source-diagnostics__filters {
    justify-items: start;
  }

  .source-diagnostics__ranges,
  .source-diagnostics__kinds,
  .source-diagnostics__sources-filter {
    justify-content: flex-start;
  }

  .source-diagnostics__ranges,
  .source-diagnostics__kinds,
  .source-diagnostics__sources-filter {
    width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
    flex-wrap: nowrap;
    padding-bottom: 2px;
    -webkit-overflow-scrolling: touch;
    scrollbar-gutter: stable;
  }

  .source-diagnostics__ranges button,
  .source-diagnostics__kinds button,
  .source-diagnostics__sources-filter button {
    flex: 0 0 auto;
    white-space: nowrap;
  }

  .source-diagnostics__summary,
  .source-diagnostics__sources,
  .source-diagnostics__source dl {
    grid-template-columns: 1fr;
  }

  .source-diagnostics__chart {
    min-height: 200px;
    padding-top: 22px;
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
  }

  .source-diagnostics__bar-cell {
    flex: 0 0 28px;
    min-width: 28px;
  }

  .source-diagnostics__bar {
    min-width: 20px;
  }

  .source-diagnostics__source header,
  .source-diagnostics__json header,
  .source-diagnostics__source-group-header {
    align-items: flex-start;
  }

  .source-diagnostics__source header > div,
  .source-diagnostics__json header > div,
  .source-diagnostics__source-group-header > div {
    min-width: 0;
  }

  .source-diagnostics__source a {
    display: inline-block;
    max-width: 100%;
  }

  .source-diagnostics__source dl {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .source-diagnostics__json pre {
    min-height: 260px;
    max-height: 60vh;
    white-space: pre;
    word-break: normal;
    overflow-wrap: normal;
  }

  .source-diagnostics__json {
    display: none;
  }
}
</style>
