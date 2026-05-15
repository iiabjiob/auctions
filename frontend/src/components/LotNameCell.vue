<script setup lang="ts">
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
  <button
    type="button"
    class="grid-lot-placeholder"
    :class="{ 'grid-lot-placeholder--new': row.isNew }"
    @click.stop="emit('open', row)"
  >
    {{ label || 'Без названия' }}
  </button>
</template>
