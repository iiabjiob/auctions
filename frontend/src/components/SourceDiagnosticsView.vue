<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  fetchSourceDiagnostics,
  type SourceDiagnosticsRange,
  type SourceDiagnosticsResponse,
} from '@/api/sourceDiagnostics'

const rangeOptions: Array<{ label: string; value: SourceDiagnosticsRange }> = [
  { label: 'День', value: 'day' },
  { label: 'Неделя', value: 'week' },
  { label: 'Месяц', value: 'month' },
  { label: '3 месяца', value: '3months' },
  { label: 'Все время', value: 'all' },
]

const selectedRange = ref<SourceDiagnosticsRange>('day')
const diagnostics = ref<SourceDiagnosticsResponse | null>(null)
const isLoading = ref(false)
const errorMessage = ref<string | null>(null)

const maxTimelineRequests = computed(() => {
  return Math.max(1, ...((diagnostics.value?.timeline ?? []).map((bucket) => bucket.request_count)))
})

const prettyJson = computed(() => JSON.stringify(diagnostics.value, null, 2))

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
  }).format(new Date(value))
}

async function loadDiagnostics() {
  isLoading.value = true
  errorMessage.value = null
  try {
    diagnostics.value = await fetchSourceDiagnostics(selectedRange.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить диагностику.'
  } finally {
    isLoading.value = false
  }
}

onMounted(loadDiagnostics)
watch(selectedRange, loadDiagnostics)
</script>

<template>
  <section class="source-diagnostics" aria-label="Диагностика обмена с площадками">
    <div class="source-diagnostics__main">
      <header class="source-diagnostics__header">
        <div>
          <span class="eyebrow">Диагностика</span>
          <h1>Обмен с площадками</h1>
          <p>
            {{ formatDate(diagnostics?.from_at ?? null) }} — {{ formatDate(diagnostics?.to_at ?? null) }}
          </p>
        </div>

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
        <div
          v-for="bucket in diagnostics?.timeline ?? []"
          :key="bucket.bucket_start"
          class="source-diagnostics__bar"
          :style="{ height: `${Math.max(8, (bucket.request_count / maxTimelineRequests) * 160)}px` }"
          :title="`${formatBucket(bucket.bucket_start)}: ${bucket.request_count}`"
        >
          <span>{{ bucket.request_count }}</span>
        </div>
        <p v-if="!isLoading && !(diagnostics?.timeline.length)" class="source-diagnostics__empty">Данных за выбранный период пока нет.</p>
      </div>

      <section v-if="diagnostics" class="source-diagnostics__sources">
        <article v-for="source in diagnostics.sources" :key="source.code" class="source-diagnostics__source">
          <header>
            <div>
              <h2>{{ source.title }}</h2>
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
        </article>
      </section>
    </div>

    <section class="source-diagnostics__json" aria-label="JSON">
      <header>
        <h2>JSON</h2>
        <button type="button" @click="loadDiagnostics" :disabled="isLoading">
          {{ isLoading ? 'Обновление...' : 'Обновить' }}
        </button>
      </header>
      <pre>{{ prettyJson }}</pre>
    </section>
  </section>
</template>

<style scoped>
.source-diagnostics {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 42vw);
  min-height: 100%;
  height: 100%;
  padding: 24px;
  gap: 16px;
  color: #17211b;
  background: #f5f7f4;
  overflow: hidden;
}

.source-diagnostics__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  overflow: auto;
  padding-right: 2px;
}

.source-diagnostics__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.source-diagnostics__header h1 {
  margin: 4px 0;
  font-size: 28px;
}

.source-diagnostics__header p {
  margin: 0;
  color: #607067;
}

.source-diagnostics__ranges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.source-diagnostics__ranges button,
.source-diagnostics__json button {
  border: 1px solid #cbd6cf;
  border-radius: 6px;
  padding: 8px 10px;
  color: #26352c;
  background: #ffffff;
  cursor: pointer;
}

.source-diagnostics__range--active {
  border-color: #346f4b !important;
  color: #ffffff !important;
  background: #346f4b !important;
}

.source-diagnostics__summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(140px, 1fr));
  gap: 8px;
}

.source-diagnostics__summary article,
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

.source-diagnostics__chart {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  min-height: 190px;
  padding: 14px;
  border: 1px solid #d8e0dc;
  border-radius: 8px;
  background: #ffffff;
  overflow-x: auto;
}

.source-diagnostics__bar {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  min-width: 18px;
  border-radius: 4px 4px 0 0;
  background: #5b8f6d;
}

.source-diagnostics__bar span {
  margin-top: -18px;
  font-size: 10px;
  color: #334238;
}

.source-diagnostics__sources {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 12px;
}

.source-diagnostics__source {
  padding: 14px;
}

.source-diagnostics__source header,
.source-diagnostics__json header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.source-diagnostics__source h2,
.source-diagnostics__json h2 {
  margin: 0;
  font-size: 18px;
}

.source-diagnostics__source a {
  color: #346f4b;
  font-size: 13px;
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

.source-diagnostics__source table {
  width: 100%;
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

@media (max-width: 900px) {
  .source-diagnostics {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: 100%;
    overflow: visible;
    padding: 16px;
  }

  .source-diagnostics__main {
    overflow: visible;
  }

  .source-diagnostics__header {
    flex-direction: column;
  }

  .source-diagnostics__summary,
  .source-diagnostics__sources,
  .source-diagnostics__source dl {
    grid-template-columns: 1fr;
  }

  .source-diagnostics__json pre {
    min-height: 320px;
    max-height: 70vh;
  }
}
</style>
