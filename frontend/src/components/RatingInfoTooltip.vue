<script setup lang="ts">
import AppTooltip from './AppTooltip.vue'

defineProps<{
  reasons: string[]
}>()

const weights = [
  ['Прием заявок', '+20'],
  ['Публичное предложение', '+12'],
  ['Срочность до 48 часов', '+10'],
  ['Цена распознана', '+8'],
  ['Документы есть / нет', '+6 / -10'],
  ['Фото или фотоархив есть / нет', '+6 / -5'],
  ['Порядок осмотра', '+4'],
  ['Подробное описание', '+3'],
  ['Дисконт к рынку', '+10 / +18 / +25'],
  ['ROI', '+6 / +12 / +20'],
  ['Потенциальная прибыль', '+5'],
  ['Решение команды', '+4 / +8 / -60'],
  ['Отмена лота', '-50'],
]
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
    <section>
      <strong>Веса</strong>
      <dl>
        <template v-for="[label, weight] in weights" :key="label">
          <dt>{{ label }}</dt>
          <dd>{{ weight }}</dd>
        </template>
      </dl>
    </section>
  </AppTooltip>
</template>
