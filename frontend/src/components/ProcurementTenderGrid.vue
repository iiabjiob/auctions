<script setup lang="ts">
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import {
  DataGrid,
  defineDataGridColumnMenu,
  defineDataGridColumns,
  type DataGridAppColumnFilterOptions,
  type DataGridCellStyleResolver,
  type DataGridExposed,
  type DataGridHistoryProp,
} from '@affino/datagrid-vue-app'
import {
  createDataSourceBackedRowModel,
  type DataGridDataSource,
  type DataGridExternalRowUpdate,
  type DataGridDataSourceRowEntry,
  type DataGridFilterSnapshot,
  type DataSourceBackedRowModel,
} from '@affino/datagrid-vue'
import { normalizeDatasourceInvalidation } from '@affino/datagrid-server-client'
import { apiRequest } from '@/api/http'
import AffinoCombobox from '@/components/AffinoCombobox.vue'
import { sanitizeGridSavedView } from '@/app/persistence'
import type { FilterPreset } from '@/app/types'
import { PROCUREMENT_GRID_EDITABLE_COLUMN_IDS } from '@/datagrid/procurementGridEdits'
import {
  PROCUREMENT_ADVANCED_FILTER_OPTIONS,
  PROCUREMENT_COLUMN_LAYOUT_OPTIONS,
  PROCUREMENT_COLUMN_MENU_OPTIONS,
  PROCUREMENT_LOADING_SKELETON_COLUMNS,
  PROCUREMENT_LOADING_SKELETON_ROWS,
  PROCUREMENT_LOADING_SKELETON_TEMPLATE,
  PROCUREMENT_PREFETCH_OPTIONS,
  PROCUREMENT_QUICK_FILTER,
  PROCUREMENT_VIRTUALIZATION_OPTIONS,
} from '@/datagrid/procurementGridUiConfig'
import {
  createProcurementServerDatasource,
  type ProcurementServerDatasource,
  type ProcurementServerGridFilters,
  type ProcurementServerGridSummary,
} from '@/datagrid/procurementServerDatasource'
import { workspaceDataGridTheme } from '@/theme/dataGridTheme'

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>
type GetJson = <TResponse>(path: string, signal?: AbortSignal) => Promise<TResponse>

const props = defineProps<{
  postJson: PostJson
  getJson: GetJson
  mobileRailOpen?: boolean
}>()

const emit = defineEmits<{
  toggleMobileRail: []
}>()

type PresetDialogMode = 'create' | 'update' | 'delete'

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
  lifecycleStatus: string
  finishedAt: string | null
  archivedAt: string | null
  archiveReason: string | null
  actualityCheckedAt: string | null
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

type GridChangeFeedResponse = {
  datasetVersion: number
  changes: Array<{
    type: 'row_updated' | 'row_inserted' | 'row_deleted' | 'invalidation'
    rowId: string | null
    payload: Record<string, unknown>
  }>
  hasMore: boolean
}

type ProcurementPipelineHealthResponse = {
  counters: {
    total_lots: number
    priority_lots: number
    decision_pending_lots: number
    missing_documents: number
    missing_critical_fields: number
    enrichment_requested: number
    enrichment_due_now: number
    enrichment_claimed_active: number
    enrichment_retry_waiting: number
    enrichment_failed_with_error: number
    enrichment_maxed_out: number
    scoring_stale_or_incomplete: number
    scored_current: number
  }
  sources: Array<{
    code: string
    title: string
    enabled: boolean
    website: string
    parser_version: string | null
    last_sync_started_at: string | null
    last_sync_completed_at: string | null
    last_successful_sync_at: string | null
    last_sync_result: string | null
    last_sync_error: string | null
    last_sync_error_code: string | null
    last_sync_fetched: number | null
    last_sync_created: number | null
    last_sync_updated: number | null
    last_sync_unchanged: number | null
    last_sync_status_changed: number | null
    last_sync_parser_failures: number | null
    last_sync_missing_critical_fields: Record<string, number>
  }>
}

type ProcurementWorkspaceRecord = {
  id: number
  source: string
  external_id: string
  registry_number: string
  title: string | null
  status: string | null
  customer_name: string | null
  customer_inn: string | null
  initial_price_value: number | null
  application_deadline_at: string | null
  notice_url: string | null
}

type ProcurementWorkspaceResponse = {
  record: ProcurementWorkspaceRecord
  detail_cached_at: string | null
  detail_payload: Record<string, unknown> | null
  documents: Array<{ title: string | null; url: string | null; source_url: string | null }>
  raw_fields: Array<{ name: string; value: string }>
  changes: {
    observations_count: number
    detail_observations_count: number
    last_observed_at: string | null
    last_detail_observed_at: string | null
    changed_fields: string[]
  }
  current_enrichment_state: {
    requested_at: string | null
    requested_reason: string | null
    last_attempt_at: string | null
    attempt_count: number
    next_attempt_at: string | null
    last_error: string | null
    claimed_at: string | null
    claimed_by: string | null
    claim_expires_at: string | null
  }
}

type ProcurementWorkspaceRefreshResponse = {
  status: string
  refreshed: boolean
  workspace: ProcurementWorkspaceResponse
}

type ProcurementDataSource = DataGridDataSource<ProcurementGridRow>

type ProcurementRowModel = DataSourceBackedRowModel<ProcurementGridRow> & {
  patchRows?: (
    updates: readonly { rowId: string | number; data: Partial<ProcurementGridRow> }[],
    options?: {
      recomputeSort?: boolean
      recomputeFilter?: boolean
      recomputeGroup?: boolean
      emit?: boolean
      signal?: AbortSignal | null
    },
  ) => void | Promise<void>
  dataSource: ProcurementDataSource
}
type ProcurementServerGridDataSource = ProcurementServerDatasource<ProcurementApiRow, ProcurementGridRow>

type GridHistoryStatusLike = {
  canUndo?: boolean
  canRedo?: boolean
  latestUndoOperationId?: string | null
  latestRedoOperationId?: string | null
  datasetVersion?: number | null
}

type GridHistoryRowSnapshot<TApiRow> = {
  id?: string | number
  rowId?: string | number
  index?: number
  row?: TApiRow | ProcurementGridRow | unknown
}

type GridHistoryMutationResponse<TApiRow> = GridHistoryStatusLike & {
  operationId?: string | null
  action?: 'undo' | 'redo'
  rows?: GridHistoryRowSnapshot<TApiRow>[]
  updatedRows?: GridHistoryRowSnapshot<TApiRow>[]
  invalidation?: unknown
  rejected?: readonly unknown[]
}

type ServerPushDataSource = ProcurementDataSource & {
  applyRowSnapshots?: (rows: readonly DataGridDataSourceRowEntry<ProcurementGridRow>[]) => boolean
  applyInvalidation?: (invalidation: unknown, options?: { datasetVersion?: unknown }) => void
}

type HistoryStatusSource = {
  subscribeHistoryStatus?: (listener: (status: GridHistoryStatusLike) => void) => () => void
}

const GRID_COLUMN_WIDTHS_STORAGE_KEY = 'procurement-grid-column-widths-v1'
const DETAIL_PANE_WIDTH_STORAGE_KEY = 'procurement-detail-pane-width'
const PROCUREMENT_LOTS_TABLE_ID = 'procurement-lots'
const SERVER_ROW_MODEL_INITIAL_FETCH_SIZE = 160
const ROW_CACHE_LIMIT = 8_000
const GRID_CHANGES_POLL_INTERVAL_MS = 5_000
const GRID_CHANGES_REFRESH_DEBOUNCE_MS = 650
const DETAIL_PANE_DEFAULT_WIDTH = 560
const DETAIL_PANE_MIN_WIDTH = 420
const DETAIL_PANE_MAX_WIDTH = 920
const PROCUREMENT_FILTER_SYNC_DELAY_MS = 400

const gridRef = ref<DataGridExposed<ProcurementGridRow> | null>(null)
const workspaceRef = ref<HTMLElement | null>(null)
const rowModel = shallowRef<ProcurementRowModel | null>(null)
const datasourceRef = shallowRef<ProcurementServerGridDataSource | null>(null)
const rowRevision = ref(0)
const latestDatasetVersion = ref<number | null>(null)
const presets = ref<FilterPreset[]>([])
const presetsLoading = ref(false)
const selectedPresetId = ref('')
const presetDialogOpen = ref(false)
const presetDialogMode = ref<PresetDialogMode>('create')
const presetNameDraft = ref('')
const presetDialogSaving = ref(false)
const presetDialogError = ref('')
const presetNameInputRef = ref<HTMLInputElement | null>(null)
const historyState = reactive({
  canUndo: false,
  canRedo: false,
  latestUndoOperationId: null as string | null,
  latestRedoOperationId: null as string | null,
  datasetVersion: null as number | null,
})
const pipelineHealth = ref<ProcurementPipelineHealthResponse | null>(null)
const loadedOnce = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const total = ref(0)
const summary = ref<ProcurementServerGridSummary>(emptySummary(0))
const gridColumnWidths = ref<Record<string, number>>(readStoredColumnWidths())
const detailPaneWidth = ref(readStoredDetailPaneWidth())
const selectedRow = ref<ProcurementGridRow | null>(null)
const selectedWorkspace = ref<ProcurementWorkspaceResponse | null>(null)
const workspaceLoading = ref(false)
const workspaceRefreshing = ref(false)
const workspaceError = ref('')
const defaultFilters = {
  source: 'all',
  law: '',
  status: '',
  workflowStatus: '',
  assignee: '',
  category: '',
  minPrice: '',
  maxPrice: '',
  minScore: 0,
  onlyNew: false,
}
const filters = reactive({ ...defaultFilters })
let gridChangesPollTimer: ReturnType<typeof window.setTimeout> | null = null
let gridChangesRefreshTimer: ReturnType<typeof window.setTimeout> | null = null
let gridChangesPolling = false
let gridChangesRefreshInFlight = false
let pipelineHealthAbortController: AbortController | null = null
let workspaceAbortController: AbortController | null = null
let resizeStartX = 0
let resizeStartWidth = 0
let historyStatusUnsubscribe: (() => void) | null = null
let filterSyncTimer: ReturnType<typeof window.setTimeout> | null = null
let filterSyncSignature = ''

const procurementContentClass = computed(() => ({
  'procurement-content--with-detail': Boolean(selectedRow.value),
}))

const gridStatus = computed(() => {
  if (errorMessage.value) return errorMessage.value
  if (loading.value && !loadedOnce.value) return 'Загружаем закупки'
  const source = pipelineHealth.value?.sources.find((item) => item.code === filters.source)
  if (source?.last_successful_sync_at) return `Синк ${formatDateTime(source.last_successful_sync_at)}`
  if (source?.last_sync_result === 'failed') return `Ошибка синка: ${source.last_sync_error_code ?? source.last_sync_error ?? 'source'}`
  if (loadedOnce.value) return `Загружено ${total.value}`
  return 'Ожидаем загрузку'
})

const filterNumber = (value: string) => {
  const normalized = value.trim().replace(/\s+/g, '').replace(',', '.')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function buildServerFilters(): ProcurementServerGridFilters {
  return {
    source: null,
    law: null,
    status: null,
    workflowStatus: null,
    assignee: null,
    category: null,
    minPrice: null,
    maxPrice: null,
    minScore: null,
    onlyNew: false,
  }
}

function buildNativeFilterModel(): DataGridFilterSnapshot | null {
  const conditions: Record<string, unknown>[] = []
  const minPrice = filterNumber(filters.minPrice)
  const maxPrice = filterNumber(filters.maxPrice)

  if (filters.source && filters.source !== 'all') {
    conditions.push({ kind: 'condition', key: 'source', operator: 'equals', value: filters.source })
  }
  if (filters.law) {
    conditions.push({ kind: 'condition', key: 'law', operator: 'equals', value: filters.law })
  }
  if (filters.status) {
    conditions.push({ kind: 'condition', key: 'status', operator: 'contains', value: filters.status })
  }
  if (filters.workflowStatus) {
    conditions.push({ kind: 'condition', key: 'workflowStatus', operator: 'equals', value: filters.workflowStatus })
  }
  if (filters.assignee) {
    conditions.push({ kind: 'condition', key: 'assignee', operator: 'equals', value: filters.assignee })
  }
  if (filters.category) {
    conditions.push({ kind: 'condition', key: 'category', operator: 'equals', value: filters.category })
  }
  if (minPrice !== null) {
    conditions.push({ kind: 'condition', key: 'initialPrice', operator: 'gte', value: minPrice })
  }
  if (maxPrice !== null) {
    conditions.push({ kind: 'condition', key: 'initialPrice', operator: 'lte', value: maxPrice })
  }
  if (filters.minScore > 0) {
    conditions.push({ kind: 'condition', key: 'score', operator: 'gte', value: filters.minScore })
  }
  if (filters.onlyNew) {
    conditions.push({ kind: 'condition', key: 'isNew', operator: 'equals', value: true })
  }

  if (!conditions.length) return null
  return {
    advancedExpression:
      conditions.length === 1
        ? conditions[0]
        : {
            kind: 'group',
            operator: 'and',
            children: conditions,
          },
  } as DataGridFilterSnapshot
}

function serializeNativeFilterModel() {
  return JSON.stringify(buildNativeFilterModel())
}

function clearFilterSyncTimer() {
  if (filterSyncTimer === null) return
  window.clearTimeout(filterSyncTimer)
  filterSyncTimer = null
}

function syncFilterModel() {
  clearFilterSyncTimer()
  const nextSignature = serializeNativeFilterModel()
  if (nextSignature === filterSyncSignature) return
  filterSyncSignature = nextSignature
  rowModel.value?.setFilterModel(buildNativeFilterModel())
}

function scheduleFilterSync() {
  clearFilterSyncTimer()
  filterSyncTimer = window.setTimeout(() => {
    filterSyncTimer = null
    syncFilterModel()
  }, PROCUREMENT_FILTER_SYNC_DELAY_MS)
}

const presetOptions = computed(() => [
  { label: 'Без среза', value: '' },
  ...presets.value.map((preset) => ({
    label: preset.is_favorite ? `${preset.name} *` : preset.name,
    value: preset.id,
  })),
])

const selectedPreset = computed(() => presets.value.find((preset) => preset.id === selectedPresetId.value) ?? null)
const currentFilterModel = computed(() => buildNativeFilterModel())
const hasAppliedFilters = computed(() => currentFilterModel.value !== null)
const canSavePreset = computed(() => hasAppliedFilters.value)
const canUpdatePreset = computed(() => Boolean(selectedPreset.value) && hasAppliedFilters.value)

function sortPresets(items: FilterPreset[]) {
  return [...items].sort((left, right) => {
    if (left.is_favorite !== right.is_favorite) {
      return left.is_favorite ? -1 : 1
    }
    return left.name.localeCompare(right.name, 'ru')
  })
}

async function loadPresets() {
  presetsLoading.value = true
  presetDialogError.value = ''
  try {
    presets.value = sortPresets(await apiRequest<FilterPreset[]>('/filter-presets', { auth: true }))
    if (selectedPresetId.value && !presets.value.some((preset) => preset.id === selectedPresetId.value)) {
      selectedPresetId.value = ''
    }
  } catch (error) {
    presetDialogError.value = error instanceof Error ? error.message : 'Не удалось загрузить срезы'
  } finally {
    presetsLoading.value = false
  }
}

function buildPresetPayload(name?: string) {
  return {
    name: (name ?? selectedPreset.value?.name ?? '').trim(),
    filters: { ...filters },
    grid_view: gridRef.value?.getSavedView() ?? null,
    is_favorite: selectedPreset.value?.is_favorite ?? false,
  }
}

async function applyPresetById(presetId: string) {
  selectedPresetId.value = presetId
  const preset = presets.value.find((item) => item.id === presetId)
  if (!preset) return

  Object.assign(filters, defaultFilters, preset.filters)
  await nextTick()
  if (preset.grid_view) {
    gridRef.value?.applySavedView(sanitizeGridSavedView(preset.grid_view))
  }
  syncFilterModel()
}

function openPresetDialog(mode: PresetDialogMode) {
  presetDialogMode.value = mode
  presetNameDraft.value = mode === 'create' ? '' : selectedPreset.value?.name ?? ''
  presetDialogError.value = ''
  presetDialogOpen.value = true
  void nextTick(() => presetNameInputRef.value?.focus())
}

function closePresetDialog() {
  presetDialogOpen.value = false
  presetDialogError.value = ''
}

async function submitPresetDialog() {
  if (presetDialogMode.value === 'delete') {
    await confirmDeletePreset()
    return
  }

  const nextName = presetNameDraft.value.trim()
  if (!nextName) {
    presetDialogError.value = 'Название среза не должно быть пустым'
    return
  }

  presetDialogSaving.value = true
  presetDialogError.value = ''
  try {
    if (presetDialogMode.value === 'update' && selectedPreset.value) {
      const preset = await apiRequest<FilterPreset>(`/filter-presets/${selectedPreset.value.id}`, {
        auth: true,
        method: 'PATCH',
        body: JSON.stringify(buildPresetPayload(nextName)),
      })
      presets.value = sortPresets(presets.value.map((item) => (item.id === preset.id ? preset : item)))
      selectedPresetId.value = preset.id
      await applyPresetById(preset.id)
    } else {
      const preset = await apiRequest<FilterPreset>('/filter-presets', {
        auth: true,
        method: 'POST',
        body: JSON.stringify(buildPresetPayload(nextName)),
      })
      presets.value = sortPresets([...presets.value, preset])
      selectedPresetId.value = preset.id
    }
    closePresetDialog()
  } catch (error) {
    presetDialogError.value = error instanceof Error ? error.message : 'Не удалось сохранить срез'
  } finally {
    presetDialogSaving.value = false
  }
}

async function confirmDeletePreset() {
  if (!selectedPreset.value) return

  presetDialogSaving.value = true
  presetDialogError.value = ''
  try {
    await apiRequest(`/filter-presets/${selectedPreset.value.id}`, {
      auth: true,
      method: 'DELETE',
    })
    presets.value = presets.value.filter((preset) => preset.id !== selectedPreset.value?.id)
    selectedPresetId.value = ''
    closePresetDialog()
  } catch (error) {
    presetDialogError.value = error instanceof Error ? error.message : 'Не удалось удалить срез'
  } finally {
    presetDialogSaving.value = false
  }
}

const predicateFilterOnly = { valueSet: false } satisfies DataGridAppColumnFilterOptions
const percentPredicateFilter = { valueSet: false, normalizeValue: normalizePercentFilterValue } satisfies DataGridAppColumnFilterOptions
const editableCellStyle: DataGridCellStyleResolver = (_row, _rowIndex, column) => {
  if (!PROCUREMENT_GRID_EDITABLE_COLUMN_IDS.has(column.key)) return null
  return { backgroundColor: 'rgba(255, 244, 199, 0.28)' }
}
const quickFilter = PROCUREMENT_QUICK_FILTER
const loadingSkeletonColumns = PROCUREMENT_LOADING_SKELETON_COLUMNS
const loadingSkeletonRows = PROCUREMENT_LOADING_SKELETON_ROWS
const loadingSkeletonTemplate = PROCUREMENT_LOADING_SKELETON_TEMPLATE
const advancedFilterOptions = PROCUREMENT_ADVANCED_FILTER_OPTIONS
const columnLayoutOptions = PROCUREMENT_COLUMN_LAYOUT_OPTIONS
const columnMenuOptions = defineDataGridColumnMenu(PROCUREMENT_COLUMN_MENU_OPTIONS)
const virtualizationOptions = PROCUREMENT_VIRTUALIZATION_OPTIONS
const prefetchOptions = PROCUREMENT_PREFETCH_OPTIONS

const columns = defineDataGridColumns<ProcurementGridRow>()([
  {
    key: 'workspace',
    label: '',
    initialState: { width: 94 },
    capabilities: { sortable: false, filterable: false },
    cellInteraction: {
      click: true,
      keyboard: ['enter', 'space'],
      role: 'button',
      label: ({ row }) => (row ? `Открыть карточку ${row.registryNumber}` : 'Открыть карточку'),
      onInvoke: ({ row }) => {
        if (row) void openWorkspace(row)
      },
    },
    cellRenderer: ({ row, interactive }) =>
      row
        ? h(
            'span',
            {
              class: ['procurement-detail-trigger', { 'procurement-detail-trigger--disabled': interactive?.enabled === false }],
              onClick: (event: MouseEvent) => {
                event.stopPropagation()
                interactive?.activate('click')
              },
            },
            '',
          )
        : '',
  },
  {
    key: 'score',
    label: 'Рейтинг',
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
  { key: 'source', label: 'Площадка', initialState: { width: 120 }, capabilities: { sortable: true, filterable: true } },
  {
    key: 'registryNumber',
    label: 'Закупка',
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
  { key: 'deliveryRegion', label: 'Локация', initialState: { width: 180 }, capabilities: { sortable: true, filterable: true } },
  { key: 'title', label: 'Наименование', initialState: { width: 430 }, capabilities: { sortable: true, filterable: true }, filter: predicateFilterOnly },
  { key: 'category', label: 'Категория', initialState: { width: 150 }, capabilities: { sortable: true, filterable: true } },
  moneyColumn('initialPrice', 'Начальная цена', 150),
  numberColumn('quantity', 'Кол-во', 112, true),
  moneyColumn('unitNmck', 'НМЦК/ед.', 130, true),
  datetimeColumn('applicationDeadline', 'Прием заявок до', 180),
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
    getJson: props.getJson,
    getFilters: buildServerFilters,
    hasFilterModel,
    mapRow,
    allocateRowRevision,
    onPullCompleted({ total: nextTotal, datasetVersion, summary: nextSummary }) {
      latestDatasetVersion.value = datasetVersion
      total.value = nextTotal
      summary.value = nextSummary
      loadedOnce.value = true
      loading.value = false
      errorMessage.value = ''
      startGridChangePolling()
    },
  })
}

function createGridRowModel(): ProcurementRowModel {
  const datasource = createGridDataSource()
  const model = createDataSourceBackedRowModel({
    dataSource: datasource,
    resolveRowId: (row: ProcurementGridRow) => row.id,
    initialTotal: Math.max(total.value || 0, SERVER_ROW_MODEL_INITIAL_FETCH_SIZE),
    initialFilterModel: buildNativeFilterModel(),
    rowCacheLimit: ROW_CACHE_LIMIT,
    prefetch: prefetchOptions,
  }) as ProcurementRowModel
  model.patchRows = async (updates) => {
    if (!updates.length) return
    await datasource.commitEdits?.({ edits: updates })
  }
  return model
}

function createGridDataSource(): ProcurementDataSource {
  const datasource = createDatasource()
  datasourceRef.value = datasource
  return {
    ...datasource,
    pull(request) {
      loading.value = true
      return datasource.pull(request).catch((error: unknown) => {
        loading.value = false
        if (isAbortLikeError(error)) {
          return Promise.reject(error)
        }
        errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить закупки'
        throw error
      })
    },
    getColumnHistogram(request) {
      return datasource.getColumnHistogram?.(request) ?? Promise.resolve([])
    },
    async commitEdits(request) {
      const commitEdits = datasource.commitEdits
      if (typeof commitEdits !== 'function') {
        throw new Error('Procurement grid datasource does not support edits')
      }
      const result = await commitEdits(request)
      updateHistoryState(result as unknown as GridHistoryStatusLike)
      if (typeof (result as { datasetVersion?: unknown }).datasetVersion === 'number') {
        latestDatasetVersion.value = (result as { datasetVersion: number }).datasetVersion
      }
      const localApplied = applyProcurementCommitResult(
        result as GridHistoryMutationResponse<ProcurementApiRow>,
        Array.isArray(request.edits) ? request.edits : [],
      )
      if (!localApplied && !result.rejected?.length) {
        await refreshGrid()
      }
      if (!result.rejected?.length) {
        errorMessage.value = ''
      }
      return result
    },
  }
}

const procurementGridHistoryOptions = computed<DataGridHistoryProp>(() => {
  const canUndo = historyState.canUndo
  const canRedo = historyState.canRedo
  return {
    enabled: true,
    shortcuts: 'grid',
    controls: true,
    adapter: {
      captureSnapshot: () => null,
      recordIntentTransaction: () => undefined,
      canUndo: () => canUndo,
      canRedo: () => canRedo,
      runHistoryAction: runProcurementGridHistoryAction,
    },
  }
})

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

async function openWorkspace(row: ProcurementGridRow, options: { refresh?: boolean } = {}) {
  selectedRow.value = row
  workspaceError.value = ''
  workspaceAbortController?.abort()
  const controller = new AbortController()
  workspaceAbortController = controller
  workspaceLoading.value = !options.refresh
  workspaceRefreshing.value = Boolean(options.refresh)
  try {
    const params = new URLSearchParams()
    if (options.refresh) params.set('refresh', 'true')
    const query = params.toString()
    selectedWorkspace.value = await props.getJson<ProcurementWorkspaceResponse>(
      `/api/v1/procurements/${encodeURIComponent(row.source)}/lots/${encodeURIComponent(row.externalId)}/workspace${query ? `?${query}` : ''}`,
      controller.signal,
    )
  } catch (error) {
    if (!isAbortLikeError(error)) {
      workspaceError.value = formatCommitError(error)
    }
  } finally {
    if (workspaceAbortController === controller) {
      workspaceAbortController = null
    }
    workspaceLoading.value = false
    workspaceRefreshing.value = false
  }
}

async function refreshWorkspaceLive() {
  const row = selectedRow.value
  if (!row) return
  workspaceRefreshing.value = true
  workspaceError.value = ''
  try {
    const response = await props.postJson<ProcurementWorkspaceRefreshResponse>(
      `/api/v1/procurements/${encodeURIComponent(row.source)}/lots/${encodeURIComponent(row.externalId)}/workspace/refresh`,
      {},
    )
    selectedWorkspace.value = response.workspace
    await refreshGrid()
    await loadPipelineHealth()
  } catch (error) {
    workspaceError.value = formatCommitError(error)
  } finally {
    workspaceRefreshing.value = false
  }
}

function closeWorkspace() {
  workspaceAbortController?.abort()
  workspaceAbortController = null
  selectedRow.value = null
  selectedWorkspace.value = null
  workspaceError.value = ''
  workspaceLoading.value = false
  workspaceRefreshing.value = false
}

function clampDetailPaneWidth(value: number) {
  return Math.min(DETAIL_PANE_MAX_WIDTH, Math.max(DETAIL_PANE_MIN_WIDTH, Math.round(value)))
}

function readStoredDetailPaneWidth() {
  try {
    const raw = window.localStorage.getItem(DETAIL_PANE_WIDTH_STORAGE_KEY)
    if (!raw) return DETAIL_PANE_DEFAULT_WIDTH
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? clampDetailPaneWidth(parsed) : DETAIL_PANE_DEFAULT_WIDTH
  } catch {
    return DETAIL_PANE_DEFAULT_WIDTH
  }
}

function saveDetailPaneWidth() {
  window.localStorage.setItem(DETAIL_PANE_WIDTH_STORAGE_KEY, String(detailPaneWidth.value))
}

function startDetailResize(event: PointerEvent) {
  resizeStartX = event.clientX
  resizeStartWidth = detailPaneWidth.value
  window.addEventListener('pointermove', handleDetailResize)
  window.addEventListener('pointerup', stopDetailResize)
  window.addEventListener('pointercancel', stopDetailResize)
}

function handleDetailResize(event: PointerEvent) {
  const nextWidth = resizeStartWidth + resizeStartX - event.clientX
  detailPaneWidth.value = clampDetailPaneWidth(nextWidth)
}

function stopDetailResize() {
  window.removeEventListener('pointermove', handleDetailResize)
  window.removeEventListener('pointerup', stopDetailResize)
  window.removeEventListener('pointercancel', stopDetailResize)
  saveDetailPaneWidth()
}

async function runProcurementGridHistoryAction(direction: 'undo' | 'redo') {
  const result = await props.postJson<GridHistoryMutationResponse<ProcurementApiRow>>(
    `/api/history/${direction}`,
    { table_id: PROCUREMENT_LOTS_TABLE_ID },
  )
  if (applyProcurementMutationResult(result)) {
    errorMessage.value = ''
    return result.operationId ?? null
  }

  await rowModel.value?.refresh('manual')
  errorMessage.value = ''
  return result.operationId ?? null
}

function updateHistoryState(status: GridHistoryStatusLike | null | undefined) {
  if (!status) return
  if (typeof status.canUndo === 'boolean') historyState.canUndo = status.canUndo
  if (typeof status.canRedo === 'boolean') historyState.canRedo = status.canRedo
  if (typeof status.latestUndoOperationId !== 'undefined') {
    historyState.latestUndoOperationId = status.latestUndoOperationId ?? null
  }
  if (typeof status.latestRedoOperationId !== 'undefined') {
    historyState.latestRedoOperationId = status.latestRedoOperationId ?? null
  }
  if (typeof status.datasetVersion !== 'undefined') {
    historyState.datasetVersion = typeof status.datasetVersion === 'number' ? status.datasetVersion : null
  }
}

function applyProcurementMutationResult(result: GridHistoryMutationResponse<ProcurementApiRow> | null | undefined) {
  if (!result) return false
  updateHistoryState(result)
  if (typeof result.datasetVersion === 'number') {
    latestDatasetVersion.value = result.datasetVersion
  }

  const rows = result.rows?.length ? result.rows : result.updatedRows ?? []
  if (applyProcurementHistoryRows(rows)) return true

  if (result.invalidation) {
    return applyProcurementInvalidation(result.invalidation, result.datasetVersion)
  }

  return false
}

function applyProcurementCommitResult(
  result: GridHistoryMutationResponse<ProcurementApiRow> | null | undefined,
  edits: readonly { rowId: string | number; data: Partial<ProcurementGridRow> }[],
) {
  if (!result) return false
  updateHistoryState(result)
  if (typeof result.datasetVersion === 'number') {
    latestDatasetVersion.value = result.datasetVersion
  }

  const rows = result.rows?.length ? result.rows : result.updatedRows ?? []
  if (rows.length && applyProcurementHistoryRows(rows)) return true

  if (edits.length) {
    return applyProcurementLocalPatches(edits)
  }

  return false
}

function applyProcurementLocalPatches(updates: readonly { rowId: string | number; data: Partial<ProcurementGridRow> }[]) {
  if (!updates.length) return false

  const rowModelApi = rowModel.value as ProcurementRowModel | null
  if (!rowModelApi?.applyExternalUpdates) return false

  rowModelApi.applyExternalUpdates(
    updates.map((update) => ({
      rowId: update.rowId,
      data: update.data,
    })),
    {
      recompute: {
        sort: true,
        filter: true,
        group: true,
      },
    },
  )

  for (const update of updates) {
    if (selectedRow.value?.id === String(update.rowId)) {
      selectedRow.value = {
        ...selectedRow.value,
        ...update.data,
      }
    }
  }

  return true
}

function applyProcurementInvalidation(invalidation: unknown, datasetVersion: number | null | undefined) {
  const datasource = rowModel.value?.dataSource as ServerPushDataSource | undefined
  const applyInvalidation = datasource?.applyInvalidation
  if (typeof applyInvalidation !== 'function') return false
  applyInvalidation.call(datasource, invalidation, { datasetVersion })
  return true
}

function applyProcurementGridChangeFeedResponse(response: GridChangeFeedResponse) {
  if (response.hasMore) return false

  const rows = collectProcurementChangeFeedRows(response)
  if (applyProcurementHistoryRows(rows)) {
    latestDatasetVersion.value = response.datasetVersion
    return true
  }

  const rowIds = collectGridChangeRowIds(response)
  if (rowIds.length && applyProcurementInvalidation({ type: 'rows', rowIds, reason: 'change_feed' }, response.datasetVersion)) {
    latestDatasetVersion.value = response.datasetVersion
    return true
  }

  for (const change of response.changes) {
    const invalidation = normalizeDatasourceInvalidation(change.payload.invalidation ?? change.payload)
    if (!invalidation) continue
    if (applyProcurementInvalidation(invalidation, response.datasetVersion)) {
      latestDatasetVersion.value = response.datasetVersion
      return true
    }
  }

  return false
}

function collectProcurementChangeFeedRows(response: GridChangeFeedResponse) {
  const rows: GridHistoryRowSnapshot<ProcurementApiRow>[] = []
  for (const change of response.changes) {
    const payload = change.payload
    const payloadRows = payload.rows ?? payload.updatedRows
    if (Array.isArray(payloadRows)) {
      rows.push(...payloadRows as GridHistoryRowSnapshot<ProcurementApiRow>[])
    }
    if (payload.row && typeof payload.row === 'object') {
      rows.push({ rowId: change.rowId ?? undefined, row: payload.row })
    }
  }
  return rows
}

function collectGridChangeRowIds(response: GridChangeFeedResponse) {
  const rowIds = new Set<string>()
  for (const change of response.changes) {
    if (change.type === 'invalidation') continue
    if (typeof change.rowId === 'string' && change.rowId.trim()) {
      rowIds.add(change.rowId)
    }
  }
  return [...rowIds]
}

function applyProcurementHistoryRows(rows: readonly GridHistoryRowSnapshot<ProcurementApiRow>[]) {
  if (!rows.length) return false

  const revision = allocateRowRevision()
  const updatesByRowId = new Map<string, { rowId: string | number; data: Partial<ProcurementGridRow> }>()
  for (const snapshot of rows) {
    const row = extractHistorySnapshotRow(snapshot)
    const mapped = isProcurementApiHistoryRow(row)
      ? mapRow(row, revision)
      : isProcurementGridHistoryRow(row)
        ? row
        : null
    if (!mapped) continue
    updatesByRowId.set(mapped.id, {
      rowId: mapped.id,
      data: mapped,
    })
  }

  const updates = [...updatesByRowId.values()]
  return applyProcurementLocalPatches(updates)
}

function allocateRowRevision() {
  rowRevision.value += 1
  return rowRevision.value
}

function extractHistorySnapshotRow<TApiRow>(snapshot: GridHistoryRowSnapshot<TApiRow>) {
  if (snapshot && typeof snapshot === 'object' && 'row' in snapshot) {
    return snapshot.row
  }
  return snapshot
}

function isProcurementApiHistoryRow(value: unknown): value is ProcurementApiRow {
  return Boolean(value && typeof value === 'object' && typeof (value as { id?: unknown }).id === 'string' && 'externalId' in value)
}

function isProcurementGridHistoryRow(value: unknown): value is ProcurementGridRow {
  return Boolean(value && typeof value === 'object' && typeof (value as { id?: unknown }).id === 'string' && 'rowRevision' in value)
}

function subscribeHistoryStatus() {
  historyStatusUnsubscribe?.()
  const source = datasourceRef.value as unknown as HistoryStatusSource | null
  historyStatusUnsubscribe = source?.subscribeHistoryStatus?.(updateHistoryState) ?? null
}

async function loadPipelineHealth() {
  pipelineHealthAbortController?.abort()
  const controller = new AbortController()
  pipelineHealthAbortController = controller
  try {
    pipelineHealth.value = await props.getJson<ProcurementPipelineHealthResponse>(
      '/api/v1/health/procurement-pipeline',
      controller.signal,
    )
  } catch (error) {
    if (!isAbortLikeError(error)) {
      console.warn('[procurement-pipeline-health] failed to load', error)
    }
  } finally {
    if (pipelineHealthAbortController === controller) {
      pipelineHealthAbortController = null
    }
  }
}

function shouldPollGridChanges() {
  return !document.hidden && latestDatasetVersion.value !== null
}

function startGridChangePolling(delay = GRID_CHANGES_POLL_INTERVAL_MS) {
  if (!shouldPollGridChanges() || gridChangesPollTimer !== null) return

  gridChangesPollTimer = window.setTimeout(() => {
    gridChangesPollTimer = null
    void pollGridChanges()
  }, delay)
}

function stopGridChangePolling() {
  if (gridChangesPollTimer !== null) {
    window.clearTimeout(gridChangesPollTimer)
    gridChangesPollTimer = null
  }
  if (gridChangesRefreshTimer !== null) {
    window.clearTimeout(gridChangesRefreshTimer)
    gridChangesRefreshTimer = null
  }
}

async function pollGridChanges() {
  if (!shouldPollGridChanges()) return
  if (gridChangesPolling) {
    startGridChangePolling()
    return
  }

  const sinceVersion = latestDatasetVersion.value
  if (sinceVersion === null) return

  gridChangesPolling = true
  try {
    const datasource = datasourceRef.value
    if (!datasource) {
      throw new Error('Procurement grid datasource is not initialized')
    }
    const response = await datasource.getChangesSinceVersion({ sinceVersion }) as GridChangeFeedResponse
    const currentVersion = latestDatasetVersion.value ?? 0
    if (response.changes.length > 0 || response.datasetVersion > currentVersion) {
      if (!applyProcurementGridChangeFeedResponse(response)) {
        scheduleGridChangeRefresh()
      }
    }
  } catch (error) {
    if (!document.hidden) {
      console.warn('[procurement-grid] change polling failed', error)
    }
  } finally {
    gridChangesPolling = false
    startGridChangePolling()
  }
}

function scheduleGridChangeRefresh() {
  if (gridChangesRefreshInFlight || gridChangesRefreshTimer !== null) return

  gridChangesRefreshTimer = window.setTimeout(() => {
    gridChangesRefreshTimer = null
    void refreshGridAfterChange()
  }, GRID_CHANGES_REFRESH_DEBOUNCE_MS)
}

async function refreshGridAfterChange() {
  if (!rowModel.value || document.hidden) return
  gridChangesRefreshInFlight = true
  try {
    await refreshGrid()
    await loadPipelineHealth()
  } finally {
    gridChangesRefreshInFlight = false
  }
}

function handleGridVisibilityChange() {
  if (document.hidden) {
    stopGridChangePolling()
    return
  }
  void loadPipelineHealth()
  startGridChangePolling(0)
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

function isAbortLikeError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
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
  filterSyncSignature = serializeNativeFilterModel()
  void loadPresets()
  subscribeHistoryStatus()
  void loadPipelineHealth()
  document.addEventListener('visibilitychange', handleGridVisibilityChange)
})

watch(filters, () => {
  scheduleFilterSync()
}, { deep: true })

onUnmounted(() => {
  historyStatusUnsubscribe?.()
  historyStatusUnsubscribe = null
  document.removeEventListener('visibilitychange', handleGridVisibilityChange)
  stopGridChangePolling()
  pipelineHealthAbortController?.abort()
  pipelineHealthAbortController = null
  stopDetailResize()
  clearFilterSyncTimer()
  rowModel.value?.dispose()
  rowModel.value = null
})
</script>

<template>
  <section ref="workspaceRef" class="procurement-workspace" aria-label="Закупки">
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
    </header>

    <section class="summary-strip" aria-label="Сводка закупок">
      <div class="summary-strip__group">
        <div><span>Найдено</span><strong>{{ total }}</strong></div>
        <div><span>Новые</span><strong>{{ summary.newCount }}</strong></div>
        <div><span>Релевантные</span><strong>{{ summary.relevantCount }}</strong></div>
        <div><span>Рейтинг 75+</span><strong>{{ summary.highScoreCount }}</strong></div>
        <div><span>На решение</span><strong>{{ summary.decisionPendingCount }}</strong></div>
      </div>
      <div class="summary-strip__controls">
        <AffinoCombobox
          id="procurement-preset-combobox"
          v-model="selectedPresetId"
          class="summary-strip__preset-combobox"
          placeholder="Выберите срез"
          :options="presetOptions"
          @change="applyPresetById"
        />
        <div class="summary-strip__buttons">
          <button v-if="canSavePreset" class="primary-button" type="button" @click="openPresetDialog('create')">
            Сохранить текущий фильтр
          </button>
          <button v-if="canUpdatePreset" class="secondary-button" type="button" @click="openPresetDialog('update')">
            Обновить срез
          </button>
          <button v-if="selectedPreset" class="secondary-button secondary-button--danger" type="button" @click="openPresetDialog('delete')">
            Удалить срез
          </button>
        </div>
      </div>
      <p class="summary-strip__status">{{ gridStatus }}</p>
    </section>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <section class="procurement-content" :class="procurementContentClass" :style="selectedRow ? { '--detail-pane-width': `${detailPaneWidth}px` } : undefined">
      <section class="grid-surface procurement-grid-surface" aria-label="Таблица закупок">
        <div v-if="loading && !loadedOnce" class="loading-state" role="status" aria-live="polite">
          <div class="table-skeleton" :style="{ '--skeleton-columns': loadingSkeletonTemplate }">
            <div class="table-skeleton__toolbar">
              <span class="table-skeleton__status">Загружаю закупки</span>
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
          ref="gridRef"
          v-show="loadedOnce || !loading || total > 0"
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
          :history="procurementGridHistoryOptions"
          @update:column-widths="persistColumnWidths"
        />
      </section>

      <aside v-if="selectedRow" class="procurement-detail-pane" aria-label="Карточка закупки">
        <button
          class="side-pane-resizer"
          type="button"
          aria-label="Изменить ширину панели"
          @pointerdown="startDetailResize"
        ></button>
        <header class="side-pane__header procurement-detail-pane__header">
          <div>
            <span>{{ selectedRow.registryNumber }}</span>
            <strong>{{ selectedRow.title || 'Без названия' }}</strong>
          </div>
          <button type="button" class="icon-button" aria-label="Закрыть" @click="closeWorkspace">×</button>
        </header>

        <div class="detail-pane__body procurement-detail-pane__body">
          <div v-if="workspaceError" class="error-banner">{{ workspaceError }}</div>
          <div v-if="workspaceLoading" class="procurement-detail-pane__muted">Загружаем карточку</div>

          <template v-if="selectedWorkspace">
            <dl class="procurement-detail-list">
              <div><dt>Статус</dt><dd>{{ selectedWorkspace.record.status || '—' }}</dd></div>
              <div><dt>Заказчик</dt><dd>{{ selectedWorkspace.record.customer_name || '—' }}</dd></div>
              <div><dt>ИНН</dt><dd>{{ selectedWorkspace.record.customer_inn || '—' }}</dd></div>
              <div><dt>НМЦК</dt><dd>{{ formatMoney(selectedWorkspace.record.initial_price_value) }}</dd></div>
              <div><dt>Заявки до</dt><dd>{{ formatDateTime(selectedWorkspace.record.application_deadline_at) }}</dd></div>
              <div><dt>Детали</dt><dd>{{ formatDateTime(selectedWorkspace.detail_cached_at) }}</dd></div>
              <div><dt>Наблюдений</dt><dd>{{ selectedWorkspace.changes.observations_count }} / {{ selectedWorkspace.changes.detail_observations_count }}</dd></div>
              <div><dt>Enrichment</dt><dd>{{ selectedWorkspace.current_enrichment_state.requested_reason || selectedWorkspace.current_enrichment_state.last_error || '—' }}</dd></div>
            </dl>

            <section class="procurement-detail-section">
              <h2>Документы</h2>
              <ul v-if="selectedWorkspace.documents.length">
                <li v-for="document in selectedWorkspace.documents.slice(0, 12)" :key="document.url || document.title || ''">
                  <a v-if="document.url" :href="document.url" target="_blank" rel="noreferrer">{{ document.title || document.url }}</a>
                  <span v-else>{{ document.title }}</span>
                </li>
              </ul>
              <p v-else>Нет документов</p>
            </section>

            <section class="procurement-detail-section">
              <h2>Поля ЕИС</h2>
              <dl class="procurement-detail-list">
                <div v-for="field in selectedWorkspace.raw_fields.slice(0, 16)" :key="field.name">
                  <dt>{{ field.name }}</dt>
                  <dd>{{ field.value }}</dd>
                </div>
              </dl>
            </section>
          </template>
        </div>

        <footer class="side-pane__footer procurement-detail-pane__footer">
          <button type="button" class="secondary-button" :disabled="workspaceRefreshing" @click="refreshWorkspaceLive">
            {{ workspaceRefreshing ? 'Обновляем' : 'Live refresh' }}
          </button>
          <a v-if="selectedRow.noticeUrl" class="primary-button" :href="selectedRow.noticeUrl" target="_blank" rel="noreferrer">ЕИС</a>
        </footer>
      </aside>

      <Teleport to="#affino-dialog-host">
        <transition name="dialog-layer">
          <div
            v-if="presetDialogOpen"
            class="app-dialog-layer"
            @click.self="closePresetDialog"
          >
            <div
              class="app-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="procurement-preset-dialog-title"
              tabindex="-1"
            >
              <header class="app-dialog__header">
                <div>
                  <span class="eyebrow">Срезы</span>
                  <h2 id="procurement-preset-dialog-title">
                    {{ presetDialogMode === 'delete' ? 'Удалить срез' : presetDialogMode === 'update' ? 'Обновить срез' : 'Сохранить срез' }}
                  </h2>
                </div>
                <button class="icon-button" type="button" aria-label="Закрыть окно" @click="closePresetDialog">×</button>
              </header>

              <div class="app-dialog__body app-dialog__body--scroll">
                <p v-if="presetDialogMode !== 'delete'" class="app-dialog__text">
                  {{ presetDialogMode === 'update' ? 'Обновим текущий срез с учетом активных фильтров и раскладки таблицы.' : 'Сохраним текущие фильтры и раскладку таблицы как новый срез.' }}
                </p>
                <p v-else class="app-dialog__text">
                  Срез "{{ selectedPreset?.name ?? '' }}" будет удален без возможности восстановления.
                </p>

                <label v-if="presetDialogMode !== 'delete'" class="app-dialog__field">
                  <span>Название среза</span>
                  <input
                    ref="presetNameInputRef"
                    v-model="presetNameDraft"
                    type="text"
                    maxlength="160"
                    placeholder="Например, Контракты по 44-ФЗ"
                    @keydown.enter.prevent="void submitPresetDialog()"
                  />
                </label>

                <p v-if="presetDialogError" class="error-banner error-banner--inline">{{ presetDialogError }}</p>
              </div>

              <footer class="app-dialog__footer">
                <button class="secondary-button" type="button" @click="closePresetDialog">Отмена</button>
                <button
                  class="primary-button"
                  type="button"
                  :disabled="presetDialogSaving"
                  @click="void submitPresetDialog()"
                >
                  {{ presetDialogMode === 'delete' ? 'Удалить' : presetDialogSaving ? 'Сохраняю' : 'Сохранить' }}
                </button>
              </footer>
            </div>
          </div>
        </transition>
      </Teleport>
    </section>
  </section>
</template>
