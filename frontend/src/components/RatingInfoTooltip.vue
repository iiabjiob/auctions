<script setup lang="ts">
import { computed } from 'vue'
import AppTooltip from './AppTooltip.vue'

type RatingDimensionBreakdown = {
  key?: string
  label?: string
  score?: number
  reasons?: string[]
}

type RatingCapBreakdown = {
  key?: string
  label?: string
  max_score?: number
  reason?: string
}

const props = defineProps<{
  reasons: string[]
  dimensions?: Record<string, RatingDimensionBreakdown> | null
  caps?: RatingCapBreakdown[] | null
}>()

const dimensionItems = computed(() =>
  Object.values(props.dimensions ?? {}).filter((dimension) => (dimension.score ?? 0) !== 0 || Boolean(dimension.reasons?.length)),
)
const capItems = computed(() => props.caps ?? [])

function formatScore(value: number | undefined) {
  const score = Number.isFinite(value) ? Number(value) : 0
  return score > 0 ? `+${score}` : String(score)
}
</script>

<template>
  <AppTooltip
    id="lot-rating-tooltip"
    placement="left"
    :gutter="8"
    trigger-tag="button"
    trigger-class="rating-info-button"
    :trigger-attrs="{
      type: 'button',
      'aria-label': 'Показать факторы рейтинга',
    }"
    surface-class="rating-info-tooltip"
  >
    <template #trigger>i</template>

    <section v-if="reasons.length">
      <strong>Сработавшие факторы</strong>
      <ul>
        <li v-for="reason in reasons" :key="reason">{{ reason }}</li>
      </ul>
    </section>
    <section v-if="dimensionItems.length">
      <strong>Измерения</strong>
      <dl>
        <template v-for="dimension in dimensionItems" :key="dimension.key || dimension.label">
          <dt>{{ dimension.label || dimension.key }}</dt>
          <dd>
            {{ formatScore(dimension.score) }}
            <ul v-if="dimension.reasons?.length">
              <li v-for="reason in dimension.reasons" :key="reason">{{ reason }}</li>
            </ul>
          </dd>
        </template>
      </dl>
    </section>
    <section v-if="capItems.length">
      <strong>Ограничения</strong>
      <ul>
        <li v-for="cap in capItems" :key="cap.key || cap.reason">
          {{ cap.reason || cap.label }}<template v-if="cap.max_score !== undefined">: максимум {{ cap.max_score }}</template>
        </li>
      </ul>
    </section>
  </AppTooltip>
</template>
