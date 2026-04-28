<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import { ensureOverlayHost } from '@affino/overlay-host'
import { useFloatingTooltip, useTooltipController } from '@affino/tooltip-vue'

defineProps<{
  reasons: string[]
}>()

const tooltip = useTooltipController({ id: 'lot-rating-tooltip', openDelay: 150 })
const overlayHost = ensureOverlayHost() ?? 'body'
const floating = useFloatingTooltip(tooltip, {
  placement: 'left',
  align: 'start',
  gutter: 8,
  viewportPadding: 12,
  teleportTo: overlayHost,
})

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

function setTriggerRef(element: Element | ComponentPublicInstance | null) {
  floating.triggerRef.value = element instanceof HTMLElement ? element : null
}

function setTooltipRef(element: Element | ComponentPublicInstance | null) {
  floating.tooltipRef.value = element instanceof HTMLElement ? element : null
}

function toggleTooltip(event: MouseEvent) {
  event.stopPropagation()
  tooltip.toggle()
}
</script>

<template>
  <button
    :ref="setTriggerRef"
    v-bind="tooltip.getTriggerProps()"
    type="button"
    class="rating-info-button"
    aria-label="Показать факторы рейтинга"
    @click="toggleTooltip"
  >
    i
  </button>

  <Teleport :to="floating.teleportTarget.value || 'body'">
    <div
      v-if="tooltip.state.value.open"
      :ref="setTooltipRef"
      class="rating-info-tooltip"
      v-bind="tooltip.getTooltipProps()"
      :style="floating.tooltipStyle.value"
    >
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
    </div>
  </Teleport>
</template>
