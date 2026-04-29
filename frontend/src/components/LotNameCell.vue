<script setup lang="ts">
import AppTooltip from './AppTooltip.vue'

type LotNameCellRow = {
  id: string
  lotName: string
  isNew: boolean
}

defineProps<{
  row: LotNameCellRow
  label: string
}>()

const emit = defineEmits<{
  open: [row: unknown]
}>()
</script>

<template>
  <AppTooltip
    :id="`lot-name-tooltip-${row.id}`"
    :open-delay="1000"
    :gutter="8"
    trigger-class="grid-lot-placeholder"
    :trigger-attrs="{
      class: { 'grid-lot-placeholder--new': row.isNew },
      onClick: (event: MouseEvent) => {
        event.stopPropagation()
        emit('open', row)
      },
    }"
    surface-class="lot-name-tooltip"
  >
    <template #trigger>
      {{ label || 'Без названия' }}
    </template>

    {{ label || 'Без названия' }}
  </AppTooltip>
</template>
