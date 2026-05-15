<script setup lang="ts">
import { nextTick, ref, watch, type PropType } from 'vue'
import {
  DataGrid,
  type DataGridExposed,
} from '@affino/datagrid-vue-app'

const props = defineProps({
  loading: { type: Boolean, required: true },
  allRowsLength: { type: Number, required: true },
  catalogGridHasLoadedOnce: { type: Boolean, required: true },
  loadingSkeletonTemplate: { type: String, required: true },
  loadingSkeletonColumns: {
    type: Array as PropType<ReadonlyArray<{ key: string; label: string; placeholderWidth: string }>>,
    required: true,
  },
  loadingSkeletonRows: {
    type: Array as PropType<ReadonlyArray<number>>,
    required: true,
  },
  rowModel: { type: Object as PropType<any>, required: true },
  columns: { type: Array as PropType<ReadonlyArray<any>>, required: true },
  gridColumnWidths: { type: Object as PropType<any>, required: true },
  workspaceDataGridTheme: { type: Object as PropType<any>, required: true },
  isGridCellEditable: { type: Function as PropType<any>, required: true },
  editableGridCellStyle: { type: Function as PropType<any>, required: true },
  catalogVirtualizationOptions: { type: Object as PropType<any>, required: true },
  advancedFilterOptions: { type: Object as PropType<any>, required: true },
  quickFilter: { type: Object as PropType<any>, required: true },
  gridStatePersistence: { type: Object as PropType<any>, required: true },
  columnMenuOptions: { type: Object as PropType<any>, required: true },
  columnLayoutOptions: { type: Object as PropType<any>, required: true },
  auctionGridHistoryOptions: { type: Object as PropType<any>, required: true },
})

const emit = defineEmits<{
  'update:column-widths': [widths: Readonly<Record<string, number | null>> | null]
}>()

const gridRef = ref<DataGridExposed<unknown> | null>(null)
const initialFocusApplied = ref(false)

type GridSelectionSnapshot = NonNullable<
  ReturnType<NonNullable<ReturnType<DataGridExposed<unknown>['getApi']>>['selection']['getSnapshot']>
>

function createFirstCellSelectionSnapshot() {
  const api = gridRef.value?.getApi()
  const runtime = gridRef.value?.getRuntime()
  if (!api?.selection.hasSupport() || !runtime) return null

  const firstRow = runtime.getBodyRowAtIndex(0)
  const firstColumn = runtime.columnSnapshot.value.visibleColumns[0]
  if (!firstRow || !firstColumn) return null

  const point = {
    rowIndex: 0,
    colIndex: 0,
    rowId: firstRow.rowId,
  }

  return {
    ranges: [
      {
        startRow: 0,
        endRow: 0,
        startCol: 0,
        endCol: 0,
        startRowId: firstRow.rowId,
        endRowId: firstRow.rowId,
        anchor: point,
        focus: point,
      },
    ],
    activeRangeIndex: 0,
    activeCell: point,
  } satisfies GridSelectionSnapshot
}

async function focusFirstCell() {
  const api = gridRef.value?.getApi()
  const runtime = gridRef.value?.getRuntime()
  if (!api?.selection.hasSupport() || !runtime) return false

  const snapshot = createFirstCellSelectionSnapshot()
  if (!snapshot) return false

  api.selection.setSnapshot(snapshot)
  await nextTick()

  const anchor = gridRef.value?.captureFocusAnchor({
    includeSelection: true,
    includeRowSelection: true,
  })
  if (!anchor) return false

  return gridRef.value?.restoreFocusAnchor(anchor, {
    scrollIntoView: true,
    preventScroll: true,
    retries: 3,
  }) ?? false
}

watch(
  () => props.rowModel && (props.catalogGridHasLoadedOnce || !props.loading || props.allRowsLength > 0),
  async (ready) => {
    if (!ready || initialFocusApplied.value) return
    if (await focusFirstCell()) {
      initialFocusApplied.value = true
    }
  },
  { immediate: true, flush: 'post' },
)

defineExpose({
  getApi: () => gridRef.value?.getApi(),
  getRuntime: () => gridRef.value?.getRuntime(),
  getSavedView: () => gridRef.value?.getSavedView(),
  applySavedView: (...args: Parameters<NonNullable<DataGridExposed<unknown>['applySavedView']>>) =>
    gridRef.value?.applySavedView(...args),
  restoreFocusAnchor: (...args: Parameters<NonNullable<DataGridExposed<unknown>['restoreFocusAnchor']>>) =>
    gridRef.value?.restoreFocusAnchor(...args),
  captureFocusAnchor: (...args: Parameters<NonNullable<DataGridExposed<unknown>['captureFocusAnchor']>>) =>
    gridRef.value?.captureFocusAnchor(...args),
})
</script>

<template>
  <div>
    <div
      v-if="loading && allRowsLength === 0 && !catalogGridHasLoadedOnce"
      class="loading-state"
      role="status"
      aria-live="polite"
    >
      <div class="table-skeleton" :style="{ '--skeleton-columns': loadingSkeletonTemplate }">
        <div class="table-skeleton__toolbar">
          <span class="table-skeleton__status">Загружаю лоты</span>
          <span class="table-skeleton__pill"></span>
          <span class="table-skeleton__pill table-skeleton__pill--short"></span>
        </div>
        <div class="table-skeleton__viewport">
          <div class="table-skeleton__head" :style="{ gridTemplateColumns: loadingSkeletonTemplate }">
            <span v-for="column in loadingSkeletonColumns" :key="column.key">
              {{ column.label }}
            </span>
          </div>
          <div class="table-skeleton__body">
            <div
              v-for="rowIndex in loadingSkeletonRows"
              :key="rowIndex"
              class="table-skeleton__row"
              :style="{ gridTemplateColumns: loadingSkeletonTemplate, '--row-delay': `${rowIndex * 38}ms` }"
            >
              <span v-for="column in loadingSkeletonColumns" :key="column.key" class="table-skeleton__cell">
                <i :style="{ width: column.placeholderWidth }"></i>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <DataGrid
      v-else-if="rowModel"
      v-show="catalogGridHasLoadedOnce || !loading || allRowsLength > 0"
      ref="gridRef"
      :row-model="rowModel"
      :columns="columns"
      :column-widths="gridColumnWidths"
      :base-row-height="26"
      :theme="workspaceDataGridTheme"
      :is-cell-editable="isGridCellEditable"
      :cell-style="editableGridCellStyle"
      :virtualization="catalogVirtualizationOptions"
      :advanced-filter="advancedFilterOptions"
      :quick-filter="quickFilter"
      :state-persistence="gridStatePersistence"
      :column-menu="columnMenuOptions"
      :column-layout="columnLayoutOptions"
      fill-handle
      range-move
      layout-mode="fill"
      :row-selection="false"
      :cell-menu="true"
      :chrome="{ toolbarPlacement: 'integrated', density: 'compact', toolbarGap: 0, workspaceGap: 8 }"
      :history="auctionGridHistoryOptions"
      @update:column-widths="emit('update:column-widths', $event)"
    />
  </div>
</template>
