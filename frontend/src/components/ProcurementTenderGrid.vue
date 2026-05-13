<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, reactive, ref, shallowRef } from 'vue'
import {
  DataGrid,
  defineDataGridColumnMenu,
  defineDataGridColumns,
  type DataGridAppColumnFilterOptions,
  type DataGridCellStyleResolver,
  type DataGridExposed,
} from '@affino/datagrid-vue-app'
import {
  createDataSourceBackedRowModel,
  type DataGridDataSource,
  type DataGridFilterSnapshot,
  type DataSourceBackedRowModel,
} from '@affino/datagrid-vue'
import {
  buildProcurementGridCellEditsFromPatch,
  commitProcurementGridEdits,
  PROCUREMENT_GRID_EDITABLE_COLUMN_IDS,
  type ProcurementGridCellEdit,
} from '@/datagrid/procurementGridEdits'
import {
  createProcurementServerDatasource,
  type ProcurementServerDatasource,
  type ProcurementServerGridFilters,
  type ProcurementServerGridSummary,
} from '@/datagrid/procurementServerDatasource'
import { workspaceDataGridTheme } from '@/theme/dataGridTheme'

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

const props = defineProps<{
  postJson: PostJson
  mobileRailOpen?: boolean
}>()

const emit = defineEmits<{
  toggleMobileRail: []
}>()

type ProcurementApiRow = {
  id: string
  recordId: number | null
  source: string
  externalId: string
  registryNumber: string
  law: string | null
  title: string | null
  status: string | null
  customerName: string | null
  customerInn: string | null
  procedureType: string | null
  platformName: string | null
  region: string | null
  deliveryRegion: string | null
  deliveryAddress: string | null
  initialPrice: number | null
  initialPriceText: string | null
  publicationDate: string | null
  applicationDeadline: string | null
  noticeUrl: string | null
  documentsUrl: string | null
  specificationUrl: string | null
  certificateRequirements: string | null
  documentationPresent: boolean | null
  isNew: boolean
  category: string | null
  matchedKeywords: string[]
  excludedKeywords: string[]
  filterReason: string | null
  score: number
  scoreLevel: string
  scoreReasons: string[]
  scoringVersion: string | null
  scoredAt: string | null
  workflowStatus: string
  assignee: string | null
  comment: string | null
  finalDecision: string | null
  rejectionReason: string | null
  bidSecurityAmount: number | null
  contractSecurityAmount: number | null
  prepaymentPercent: number | null
  paymentTerms: string | null
  quantity: number | null
  unitNmck: number | null
  costRealistic: number | null
  costCautious: number | null
  netProfit: number | null
  profitability: number | null
  roi: number | null
  cashGapPeak: number | null
  calculatorInputs?: Record<string, unknown>
  calculatorScenarios?: Record<string, unknown>
  firstSeenAt: string | null
  lastSeenAt: string | null
}

type ProcurementGridRow = ProcurementApiRow & {
  rowRevision: number
  productType: string | null
  fabricType: string | null
  fabricPrice: number | null
  fabricConsumptionPerUnit: number | null
  accessoriesCost: number | null
  sewingCost: number | null
  extraOperationsCost: number | null
  logisticsCost: number | null
  packagingCost: number | null
  defectReservePercent: number | null
  adminFotCost: number | null
  vatMode: string | null
}

type ProcurementCommitEditsRequest = {
  edits: readonly {
    rowId: string | number
    data: Partial<ProcurementGridRow>
  }[]
  signal?: AbortSignal
}

type ProcurementCommitEditsResult = {
  committed?: Array<{ rowId: string | number; revision?: string | number | null }>
  rejected?: Array<{ rowId: string | number; reason?: string }>
}

type ProcurementDataSource = DataGridDataSource<ProcurementGridRow> & {
  commitEdits?(request: ProcurementCommitEditsRequest): Promise<ProcurementCommitEditsResult>
}
type ProcurementRowModel = DataSourceBackedRowModel<ProcurementGridRow> & {
  patchRows?: (updates: readonly { rowId: string | number; data: Partial<ProcurementGridRow> }[]) => void | Promise<void>
  dataSource: ProcurementDataSource
}
type ProcurementServerGridDataSource = ProcurementServerDatasource<ProcurementApiRow, ProcurementGridRow>

const GRID_COLUMN_WIDTHS_STORAGE_KEY = 'procurement-grid-column-widths-v1'
const SERVER_ROW_MODEL_INITIAL_FETCH_SIZE = 160
const ROW_CACHE_LIMIT = 8_000

const gridRef = ref<DataGridExposed<ProcurementGridRow> | null>(null)
const rowModel = shallowRef<ProcurementRowModel | null>(null)
const rowRevision = ref(0)
const latestDatasetVersion = ref<number | null>(null)
const loadedOnce = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const total = ref(0)
const summary = ref<ProcurementServerGridSummary>(emptySummary(0))
const gridColumnWidths = ref<Record<string, number>>(readStoredColumnWidths())
const filters = reactive({
  source: 'zakupki',
  law: '',
  status: '',
  workflowStatus: '',
  assignee: '',
  category: '',
  minPrice: '',
  maxPrice: '',
  minScore: 0,
  onlyNew: false,
})

const gridStatus = computed(() => {
  if (errorMessage.value) return errorMessage.value
  if (loading.value && !loadedOnce.value) return 'Загружаем закупки'
  if (latestDatasetVersion.value !== null) return `Версия данных ${latestDatasetVersion.value}`
  return 'Ожидаем данные'
})

const filterNumber = (value: string) => {
  const normalized = value.trim().replace(/\s+/g, '').replace(',', '.')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function buildServerFilters(): ProcurementServerGridFilters {
  return {
    source: filters.source || null,
    law: filters.law || null,
    status: filters.status || null,
    workflowStatus: filters.workflowStatus || null,
    assignee: filters.assignee || null,
    category: filters.category || null,
    minPrice: filterNumber(filters.minPrice),
    maxPrice: filterNumber(filters.maxPrice),
    minScore: filters.minScore > 0 ? filters.minScore : null,
    onlyNew: filters.onlyNew,
  }
}

const predicateFilterOnly = { valueSet: false } satisfies DataGridAppColumnFilterOptions
const percentPredicateFilter = { valueSet: false, normalizeValue: normalizePercentFilterValue } satisfies DataGridAppColumnFilterOptions
const editableCellStyle: DataGridCellStyleResolver = (_row, _rowIndex, column) => {
  if (!PROCUREMENT_GRID_EDITABLE_COLUMN_IDS.has(column.key)) return null
  return { backgroundColor: 'rgba(255, 244, 199, 0.28)' }
}
const quickFilter = {
  placeholder: 'Поиск: номер, заказчик, ИНН, регион, предмет',
  columns: ['registryNumber', 'title', 'customerName', 'customerInn', 'deliveryRegion', 'category', 'assignee'],
  mode: 'tokens' as const,
  applyMode: 'debounce' as const,
  debounceMs: 400,
}
const advancedFilterOptions = {
  buttonLabel: 'Фильтр',
}
const columnLayoutOptions = {
  buttonLabel: 'Колонки',
}
const columnMenuOptions = defineDataGridColumnMenu({
  trigger: 'button+contextmenu',
  items: ['sort', 'pin', 'filter'],
  labels: {
    sort: 'Сортировка',
    pin: 'Закрепление',
    filter: 'Фильтр',
    valueSearchPlaceholder: 'Поиск значений',
    selectedValuesSummary: 'Выбрано {selected} из {total}',
  },
})
const virtualizationOptions = {
  rows: true,
  columns: true,
  rowOverscan: 18,
  columnOverscan: 2,
}
const prefetchOptions = {
  enabled: true,
  triggerViewportFactor: 1,
  windowViewportFactor: 1,
  minBatchSize: 96,
  maxBatchSize: 192,
  directionalBias: 'scroll-direction' as const,
}

const columns = defineDataGridColumns<ProcurementGridRow>()([
  {
    key: 'score',
    label: 'Балл',
    dataType: 'number',
    initialState: { width: 86 },
    presentation: { align: 'right', headerAlign: 'right' },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) =>
      row
        ? h('span', { class: ['procurement-score-pill', `procurement-score-pill--${row.scoreLevel}`] }, String(row.score))
        : '',
  },
  { key: 'scoreLevel', label: 'Сигнал', initialState: { width: 108 }, capabilities: { sortable: true, filterable: true } },
  { key: 'workflowStatus', label: 'Этап', initialState: { width: 150 }, capabilities: { sortable: true, filterable: true, editable: true } },
  { key: 'source', label: 'Источник', initialState: { width: 94 }, capabilities: { sortable: true, filterable: true } },
  {
    key: 'registryNumber',
    label: 'Номер',
    initialState: { width: 142 },
    capabilities: { sortable: true, filterable: true },
    cellRenderer: ({ row, displayValue }) =>
      row?.noticeUrl
        ? h('a', { href: row.noticeUrl, target: '_blank', rel: 'noreferrer', class: 'procurement-grid-link' }, String(displayValue || row.registryNumber))
        : String(displayValue || ''),
  },
  { key: 'law', label: 'Закон', initialState: { width: 86 }, capabilities: { sortable: true, filterable: true } },
  { key: 'customerName', label: 'Заказчик', initialState: { width: 260 }, capabilities: { sortable: true, filterable: true }, filter: predicateFilterOnly },
  { key: 'customerInn', label: 'ИНН', initialState: { width: 120 }, capabilities: { sortable: true, filterable: true }, filter: predicateFilterOnly },
  { key: 'deliveryRegion', label: 'Регион', initialState: { width: 160 }, capabilities: { sortable: true, filterable: true } },
  { key: 'title', label: 'Предмет', initialState: { width: 420 }, capabilities: { sortable: true, filterable: true }, filter: predicateFilterOnly },
  { key: 'category', label: 'Категория', initialState: { width: 150 }, capabilities: { sortable: true, filterable: true } },
  moneyColumn('initialPrice', 'НМЦК', 136),
  numberColumn('quantity', 'Кол-во', 112, true),
  moneyColumn('unitNmck', 'НМЦК/ед.', 130, true),
  datetimeColumn('applicationDeadline', 'Заявки до', 170),
  {
    key: 'specificationUrl',
    label: 'ТЗ',
    initialState: { width: 92 },
    cellRenderer: ({ row }) =>
      row?.specificationUrl
        ? h('a', { href: row.specificationUrl, target: '_blank', rel: 'noreferrer', class: 'procurement-grid-link' }, 'ТЗ')
        : '',
  },
  { key: 'certificateRequirements', label: 'Сертификаты', initialState: { width: 220 }, capabilities: { sortable: true, filterable: true, editable: true }, filter: predicateFilterOnly },
  { key: 'documentationPresent', label: 'Документы', dataType: 'boolean', initialState: { width: 112 }, capabilities: { sortable: true, filterable: true, editable: true } },
  moneyColumn('bidSecurityAmount', 'Обесп. заявки', 148, true),
  moneyColumn('contractSecurityAmount', 'Обесп. контр.', 148, true),
  numberColumn('prepaymentPercent', 'Аванс %', 104, true),
  { key: 'paymentTerms', label: 'Оплата', initialState: { width: 180 }, capabilities: { sortable: true, filterable: true, editable: true }, filter: predicateFilterOnly },
  { key: 'productType', label: 'Тип изделия', initialState: { width: 150 }, capabilities: { sortable: true, filterable: true, editable: true }, filter: predicateFilterOnly },
  { key: 'fabricType', label: 'Ткань', initialState: { width: 140 }, capabilities: { sortable: true, filterable: true, editable: true }, filter: predicateFilterOnly },
  moneyColumn('fabricPrice', 'Ткань/м', 118, true),
  numberColumn('fabricConsumptionPerUnit', 'Расход', 110, true),
  moneyColumn('accessoriesCost', 'Фурнитура', 128, true),
  moneyColumn('sewingCost', 'Пошив', 118, true),
  moneyColumn('extraOperationsCost', 'Доп. операции', 146, true),
  moneyColumn('logisticsCost', 'Логистика', 126, true),
  moneyColumn('packagingCost', 'Упаковка', 126, true),
  numberColumn('defectReservePercent', 'Резерв %', 110, true),
  moneyColumn('adminFotCost', 'Адм./ФОТ', 128, true),
  moneyColumn('costRealistic', 'Себест. реал.', 142),
  moneyColumn('costCautious', 'Себест. осторож.', 162),
  moneyColumn('netProfit', 'Чистая прибыль', 154),
  percentColumn('profitability', 'Маржин.', 112),
  percentColumn('roi', 'ROI', 96),
  moneyColumn('cashGapPeak', 'Кассовый разрыв', 164),
  { key: 'assignee', label: 'Ответственный', initialState: { width: 150 }, capabilities: { sortable: true, filterable: true, editable: true } },
  { key: 'comment', label: 'Комментарий', initialState: { width: 240 }, capabilities: { sortable: true, filterable: true, editable: true }, filter: predicateFilterOnly },
  { key: 'finalDecision', label: 'Решение', initialState: { width: 130 }, capabilities: { sortable: true, filterable: true, editable: true } },
  { key: 'rejectionReason', label: 'Причина отказа', initialState: { width: 200 }, capabilities: { sortable: true, filterable: true, editable: true }, filter: predicateFilterOnly },
  datetimeColumn('scoredAt', 'Оценено', 160),
])

function moneyColumn(key: keyof ProcurementGridRow & string, label: string, width: number, editable = false) {
  return {
    key,
    label,
    dataType: 'currency' as const,
    initialState: { width },
    presentation: {
      align: 'right' as const,
      headerAlign: 'right' as const,
      format: { number: { locale: 'ru-RU', style: 'currency' as const, currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }: { row?: ProcurementGridRow | null }) => formatMoney(row?.[key] as number | null | undefined),
  }
}

function numberColumn(key: keyof ProcurementGridRow & string, label: string, width: number, editable = false) {
  return {
    key,
    label,
    dataType: 'number' as const,
    initialState: { width },
    presentation: { align: 'right' as const, headerAlign: 'right' as const, format: { number: { locale: 'ru-RU', maximumFractionDigits: 3 } } },
    capabilities: { sortable: true, filterable: true, editable },
    filter: predicateFilterOnly,
  }
}

function percentColumn(key: keyof ProcurementGridRow & string, label: string, width: number) {
  return {
    key,
    label,
    dataType: 'number' as const,
    initialState: { width },
    presentation: { align: 'right' as const, headerAlign: 'right' as const, format: { number: { locale: 'ru-RU', style: 'percent' as const, maximumFractionDigits: 1 } } },
    capabilities: { sortable: true, filterable: true },
    filter: percentPredicateFilter,
    cellRenderer: ({ row }: { row?: ProcurementGridRow | null }) => formatPercent(row?.[key] as number | null | undefined),
  }
}

function datetimeColumn(key: keyof ProcurementGridRow & string, label: string, width: number) {
  return {
    key,
    label,
    dataType: 'datetime' as const,
    initialState: { width },
    presentation: {
      format: { dateTime: { locale: 'ru-RU', day: '2-digit' as const, month: '2-digit' as const, year: 'numeric' as const, hour: '2-digit' as const, minute: '2-digit' as const } },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }: { row?: ProcurementGridRow | null }) => formatDateTime(row?.[key] as string | null | undefined),
  }
}

function createDatasource(): ProcurementServerGridDataSource {
  return createProcurementServerDatasource<ProcurementApiRow, ProcurementGridRow>({
    postJson: props.postJson,
    getFilters: buildServerFilters,
    hasFilterModel,
    mapRow,
    allocateRowRevision() {
      rowRevision.value += 1
      return rowRevision.value
    },
    onPullCompleted({ total: nextTotal, datasetVersion, summary: nextSummary }) {
      latestDatasetVersion.value = datasetVersion
      total.value = nextTotal
      summary.value = nextSummary
      loadedOnce.value = true
      loading.value = false
      errorMessage.value = ''
    },
  })
}

function createGridRowModel(): ProcurementRowModel {
  const datasource = createGridDataSource()
  const model = createDataSourceBackedRowModel({
    dataSource: datasource,
    resolveRowId: (row: ProcurementGridRow) => row.id,
    initialTotal: Math.max(total.value || 0, SERVER_ROW_MODEL_INITIAL_FETCH_SIZE),
    rowCacheLimit: ROW_CACHE_LIMIT,
    prefetch: prefetchOptions,
  }) as ProcurementRowModel
  if (typeof model.patchRows !== 'function') {
    model.patchRows = async (updates) => {
      if (!updates.length) return
      await datasource.commitEdits?.({ edits: updates })
      await model.refresh('manual')
    }
  }
  return model
}

function createGridDataSource(): ProcurementDataSource {
  const datasource = createDatasource()
  return {
    pull(request) {
      loading.value = true
      return datasource.pull(request).catch((error: unknown) => {
        loading.value = false
        errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить закупки'
        throw error
      })
    },
    getColumnHistogram(request) {
      return datasource.getColumnHistogram?.(request) ?? Promise.resolve([])
    },
    async commitEdits(request) {
      return commitGridEdits(request)
    },
  }
}

async function commitGridEdits(request: ProcurementCommitEditsRequest): Promise<ProcurementCommitEditsResult> {
  const baseVersion = latestDatasetVersion.value
  if (baseVersion === null) {
    await refreshGrid()
    return { rejected: request.edits.map((edit) => ({ rowId: edit.rowId, reason: 'datasetVersion is not loaded yet' })) }
  }

  const cellEdits: ProcurementGridCellEdit[] = []
  for (const edit of request.edits) {
    cellEdits.push(...buildProcurementGridCellEditsFromPatch(String(edit.rowId), edit.data as Record<string, unknown>))
  }
  if (!cellEdits.length) {
    return { rejected: request.edits.map((edit) => ({ rowId: edit.rowId, reason: 'no editable procurement columns' })) }
  }

  try {
    const response = await commitProcurementGridEdits<ProcurementApiRow>({
      postJson: props.postJson,
      baseVersion,
      edits: cellEdits,
      signal: request.signal,
    })
    latestDatasetVersion.value = response.datasetVersion
    errorMessage.value = ''
    await rowModel.value?.refresh('manual')
    return { committed: request.edits.map((edit) => ({ rowId: edit.rowId, revision: response.datasetVersion })) }
  } catch (error) {
    errorMessage.value = formatCommitError(error)
    await rowModel.value?.refresh('manual')
    return { rejected: request.edits.map((edit) => ({ rowId: edit.rowId, reason: errorMessage.value })) }
  }
}

function mapRow(row: ProcurementApiRow, revision: number): ProcurementGridRow {
  const inputs = row.calculatorInputs ?? {}
  return {
    ...row,
    rowRevision: revision,
    productType: stringInput(inputs.product_type),
    fabricType: stringInput(inputs.fabric_type),
    fabricPrice: numericInput(inputs.fabric_price),
    fabricConsumptionPerUnit: numericInput(inputs.fabric_consumption_per_unit),
    accessoriesCost: numericInput(inputs.accessories_cost),
    sewingCost: numericInput(inputs.sewing_cost),
    extraOperationsCost: numericInput(inputs.extra_operations_cost),
    logisticsCost: numericInput(inputs.logistics_cost),
    packagingCost: numericInput(inputs.packaging_cost),
    defectReservePercent: numericInput(inputs.defect_reserve_percent),
    adminFotCost: numericInput(inputs.admin_fot_cost),
    vatMode: stringInput(inputs.vat_mode),
  }
}

function hasFilterModel(filterModel: DataGridFilterSnapshot | null | undefined) {
  if (!filterModel) return false
  const snapshot = filterModel as DataGridFilterSnapshot & {
    quickFilter?: { query?: string }
    columnStyleFilters?: Record<string, unknown>
  }
  const quickFilterModel = snapshot.quickFilter
  return (
    Object.keys(snapshot.columnFilters ?? {}).length > 0 ||
    Object.keys(snapshot.columnStyleFilters ?? {}).length > 0 ||
    Object.keys(snapshot.advancedFilters ?? {}).length > 0 ||
    Boolean(snapshot.advancedExpression) ||
    (typeof quickFilterModel?.query === 'string' && quickFilterModel.query.trim().length > 0)
  )
}

function refreshGrid() {
  return rowModel.value?.refresh('manual') ?? Promise.resolve()
}

function resetFilters() {
  filters.source = 'zakupki'
  filters.law = ''
  filters.status = ''
  filters.workflowStatus = ''
  filters.assignee = ''
  filters.category = ''
  filters.minPrice = ''
  filters.maxPrice = ''
  filters.minScore = 0
  filters.onlyNew = false
  void refreshGrid()
}

function persistColumnWidths(widths: Readonly<Record<string, number | null>> | null) {
  const normalized = Object.fromEntries(
    Object.entries(widths ?? {}).filter((entry): entry is [string, number] => typeof entry[1] === 'number'),
  )
  gridColumnWidths.value = normalized
  window.localStorage.setItem(GRID_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(normalized))
}

function readStoredColumnWidths(): Record<string, number> {
  try {
    const raw = window.localStorage.getItem(GRID_COLUMN_WIDTHS_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function normalizePercentFilterValue(context: { value: unknown }) {
  if (typeof context.value !== 'number') return context.value
  return Math.abs(context.value) > 1 ? context.value / 100 : context.value
}

function numericInput(value: unknown): number | null {
  if (value === null || typeof value === 'undefined' || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function stringInput(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function formatMoney(value: number | null | undefined) {
  if (value === null || typeof value === 'undefined' || !Number.isFinite(value)) return ''
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value)
}

function formatPercent(value: number | null | undefined) {
  if (value === null || typeof value === 'undefined' || !Number.isFinite(value)) return ''
  return new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 1 }).format(value)
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatCommitError(error: unknown) {
  if (error instanceof Error) return error.message
  return 'Не удалось сохранить изменения'
}

function emptySummary(total: number): ProcurementServerGridSummary {
  return {
    total,
    newCount: 0,
    relevantCount: 0,
    highScoreCount: 0,
    decisionPendingCount: 0,
  }
}

onMounted(() => {
  rowModel.value = createGridRowModel()
})

onUnmounted(() => {
  rowModel.value?.dispose()
  rowModel.value = null
})
</script>

<template>
  <section class="procurement-workspace" aria-label="Закупки">
    <header class="auction-toolbar">
      <div class="toolbar-title">
        <button
          class="app-mobile-menu-button"
          type="button"
          aria-label="Открыть меню"
          :aria-expanded="mobileRailOpen"
          @click="emit('toggleMobileRail')"
        >
          <span></span>
          <span></span>
          <span></span>
        </button>
        <span class="eyebrow">ЕИС Закупки</span>
        <h1>Лоты закупок для отбора</h1>
      </div>
      <div class="procurement-grid-actions">
        <span class="detail-muted">{{ gridStatus }}</span>
        <button class="secondary-button" type="button" @click="resetFilters">Сброс</button>
        <button class="secondary-button" type="button" :disabled="loading" @click="refreshGrid">Обновить</button>
      </div>
    </header>

    <section class="summary-strip" aria-label="Сводка закупок">
      <div class="summary-strip__group">
        <div><span>Всего</span><strong>{{ total }}</strong></div>
        <div><span>Новые</span><strong>{{ summary.newCount }}</strong></div>
        <div><span>Релевантные</span><strong>{{ summary.relevantCount }}</strong></div>
        <div><span>Приоритет</span><strong>{{ summary.highScoreCount }}</strong></div>
        <div><span>На решение</span><strong>{{ summary.decisionPendingCount }}</strong></div>
      </div>
    </section>

    <section class="procurement-filter-bar" aria-label="Фильтры закупок">
      <label>
        <span>Закон</span>
        <input v-model="filters.law" type="text" @change="refreshGrid" />
      </label>
      <label>
        <span>Статус</span>
        <input v-model="filters.status" type="text" @change="refreshGrid" />
      </label>
      <label>
        <span>Этап</span>
        <input v-model="filters.workflowStatus" type="text" @change="refreshGrid" />
      </label>
      <label>
        <span>Категория</span>
        <input v-model="filters.category" type="text" @change="refreshGrid" />
      </label>
      <label>
        <span>Мин. балл</span>
        <input v-model.number="filters.minScore" type="number" min="0" max="100" @change="refreshGrid" />
      </label>
      <label class="procurement-filter-bar__check">
        <input v-model="filters.onlyNew" type="checkbox" @change="refreshGrid" />
        <span>Только новые</span>
      </label>
    </section>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <section class="grid-surface procurement-grid-surface" aria-label="Таблица закупок">
      <DataGrid
        v-if="rowModel"
        ref="gridRef"
        :row-model="rowModel"
        :columns="columns"
        :column-widths="gridColumnWidths"
        :base-row-height="26"
        :theme="workspaceDataGridTheme"
        :is-cell-editable="({ column }) => PROCUREMENT_GRID_EDITABLE_COLUMN_IDS.has(column.key)"
        :cell-style="editableCellStyle"
        :virtualization="virtualizationOptions"
        :advanced-filter="advancedFilterOptions"
        :quick-filter="quickFilter"
        :column-menu="columnMenuOptions"
        :column-layout="columnLayoutOptions"
        fill-handle
        range-move
        layout-mode="fill"
        :row-selection="false"
        :cell-menu="true"
        :chrome="{ toolbarPlacement: 'integrated', density: 'compact', toolbarGap: 0, workspaceGap: 8 }"
        @update:column-widths="persistColumnWidths"
      />
    </section>
  </section>
</template>
