<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import { ensureOverlayHost } from '@affino/overlay-host'
import { useFloatingTooltip, useTooltipController } from '@affino/tooltip-vue'

type LotNameCellRow = {
  id: string
  lotName: string
  isNew: boolean
}

const props = defineProps<{
  row: LotNameCellRow
  label: string
}>()

const emit = defineEmits<{
  open: [row: unknown]
}>()

const tooltip = useTooltipController({ id: `lot-name-tooltip-${props.row.id}`, openDelay: 1000 })
const overlayHost = ensureOverlayHost() ?? 'body'
const floating = useFloatingTooltip(tooltip, {
  placement: 'top',
  align: 'start',
  gutter: 8,
  viewportPadding: 12,
  teleportTo: overlayHost,
})

function setTriggerRef(element: Element | ComponentPublicInstance | null) {
  floating.triggerRef.value = element instanceof HTMLElement ? element : null
}

function setTooltipRef(element: Element | ComponentPublicInstance | null) {
  floating.tooltipRef.value = element instanceof HTMLElement ? element : null
}
</script>

<template>
  <span
    :ref="setTriggerRef"
    v-bind="tooltip.getTriggerProps()"
    class="grid-lot-placeholder"
    :class="{ 'grid-lot-placeholder--new': row.isNew }"
    @click.stop="emit('open', row)"
  >
    {{ label || 'Без названия' }}
  </span>

  <Teleport :to="floating.teleportTarget.value || 'body'">
    <div
      v-if="tooltip.state.value.open"
      :ref="setTooltipRef"
      class="lot-name-tooltip"
      v-bind="tooltip.getTooltipProps()"
      :style="floating.tooltipStyle.value"
    >
      {{ label || 'Без названия' }}
    </div>
  </Teleport>
</template>