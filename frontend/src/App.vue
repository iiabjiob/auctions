<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  UiMenu,
  UiMenuContent,
  UiMenuItem,
  UiMenuLabel,
  UiMenuSeparator,
  UiMenuTrigger,
} from '@affino/menu-vue'
import {
  type DataGridCellStyleResolver,
  type DataGridExposed,
  type DataGridFocusAnchor,
  type DataGridHistoryProp,
  type DataGridSavedViewSnapshot,
} from '@affino/datagrid-vue-app'
import {
  createDataSourceBackedRowModel,
  type DataGridColumnHistogram,
  type DataGridDataSource,
  type DataGridDataSourceRowEntry,
  type DataGridExternalRowUpdate,
  type DataGridFilterSnapshot,
  type DataGridSetStateOptions,
  type DataGridSortState,
  type DataGridDataSourcePushListener,
  type DataSourceBackedRowModel,
} from '@affino/datagrid-vue'
import { normalizeDatasourceInvalidation } from '@affino/datagrid-server-client'
import { ApiRequestError as ApiClientRequestError } from './api/http'
import { fetchLotDecisionReport } from './api/decisionReports'
import {
  formatDateTime,
  formatDecisionLevel,
  formatLifecycleStatus,
  lifecycleStatusTone,
  parseDateTime,
  parseNumber,
} from './app/formatters'
import { hasGridFilterModel } from './app/gridFilters'
import { renderHelpMarkdown } from './app/markdown'
import {
  type AnalysisConfigDraft,
  type AnalysisConfigDraftRule,
  type PresetDialogMode,
  useAppUiState,
} from './app/useAppUiState'
import { useAuctionDetailState } from './app/useAuctionDetailState'
import {
  buildAuctionServerGridFilters,
  buildCatalogFilterModel,
  buildCatalogServerViewportRange,
  createAuthHeaders,
  isAbortLikeError,
  resolveCatalogPullFilterModel,
  resolveCatalogServerViewportSize,
  resolveViewportRangeSize,
  serializeCatalogFilterModel,
  serializeCatalogQueryScope,
  apiUrl,
  API_BASE_URL,
} from './app/catalogWorkspaceHelpers'
import type {
  AnalysisConfigCategoryRule,
  AnalysisConfigLegalRiskRules,
  AnalysisConfigResponse,
  ApiAuctionSummary,
  ApiColumn,
  ApiDebtor,
  ApiDocument,
  ApiField,
  ApiLotImage,
  ApiLotRow,
  ApiLotSummary,
  ApiOrganizer,
  ApiPriceScheduleStep,
  ApiSource,
  AuctionDetailResponse,
  AuctionPipelineHealthResponse,
  AuctionPipelineSourceSyncStatus,
  AuctionWorkspaceExposed,
  CatalogAuctionServerDataSource,
  CatalogColumnHistogramRequest,
  CatalogDataSource,
  CatalogRowModel,
  DatasetPeriod,
  FilterPreset,
  GridApi,
  GridChangeFeedResponse,
  GridColumnWidthsState,
  GridHistoryMutationResponse,
  GridHistoryRowSnapshot,
  GridHistoryStatusLike,
  GridLotRow,
  GridSelectionSnapshot,
  GridWorkSnapshot,
  HistoryStatusSource,
  LotChangeSummary,
  LotDetailResponse,
  LotEconomy,
  LotFieldChange,
  LotHistogramPayload,
  LotWorkItem,
  LotWorkspaceEnrichmentState,
  LotWorkspaceRefreshResponse,
  LotWorkspaceResponse,
  LotsResponse,
  OwnerScoringProfile,
  ProcurementAttractiveness,
  ProcurementLot,
  ProcurementLotListResponse,
  RatingBreakdown,
  ScoringDimensionWeights,
  ServerQuickFiltersState,
  WorkDraft,
  MobileInlineEditTarget,
} from './app/types'
import {
  clampDetailPaneWidth,
  persistServerFilters as persistStoredServerFilters,
  readStoredDetailPaneWidth,
  readStoredGridColumnWidths,
  readStoredServerFilters,
  sanitizeGridColumnWidths,
  sanitizeGridSavedView,
  sanitizeServerFilters,
  saveDetailPaneWidth,
} from './app/persistence'
import {
  createUserInterestProfileFromPreset,
  deleteUserInterestProfile,
  fetchUserInterestProfiles,
  refreshUserInterestProfileFromPreset,
  updateUserInterestProfile,
} from './api/userInterestProfiles'
import { createTelegramConnectToken } from './api/telegram'
import AuthLoginScreen from './components/AuthLoginScreen.vue'
import AffinoCombobox from './components/AffinoCombobox.vue'
import AuctionWorkspace from './components/AuctionWorkspace.vue'
import ProcurementTenderGrid from './components/ProcurementTenderGrid.vue'
import AnalysisConfigRoute from './views/AnalysisConfigRoute.vue'
import InterestProfilesRoute from './views/InterestProfilesRoute.vue'
import SourceDiagnosticsView from './components/SourceDiagnosticsView.vue'
import {
  createAuctionServerDatasource,
  type AuctionServerDatasource,
  type AuctionServerGridSummary,
} from './datagrid/auctionServerDatasource'
import { AUCTION_GRID_EDITABLE_COLUMN_IDS } from './datagrid/auctionGridEdits'
import {
  catalogAdvancedFilterOptions,
  catalogGridStatePersistence,
  catalogLoadingSkeletonColumns,
  catalogQuickFilter,
  catalogRowModelPrefetchOptions,
  catalogVirtualizationOptions,
} from './datagrid/auctionGridUiConfig'
import { createAuctionColumnMenuOptions, createAuctionGridColumns } from './datagrid/auctionGridColumns'
import { useAuthStore } from './stores/auth'
import { workspaceDataGridTheme } from './theme/dataGridTheme'
import type { ActionRecommendation, DecisionLevel, LotDecisionReport } from './types/decisionReport'
import type { UserInterestProfile } from './types/userInterestProfiles'
import howItWorksMarkdown from '../../docs/how-it-works.md?raw'

const allRows = ref<GridLotRow[]>([])
const catalogTotal = ref(0)
const catalogSummary = ref<AuctionServerGridSummary>({
  total: 0,
  newCount: 0,
  activeCount: 0,
  openApplicationsCount: 0,
  highRatingCount: 0,
})
const presets = ref<FilterPreset[]>([])
const telegramPresets = ref<FilterPreset[]>([])
const userInterestProfiles = ref<UserInterestProfile[]>([])
const analysisConfig = ref<AnalysisConfigResponse | null>(null)
const auctionPipelineHealth = ref<AuctionPipelineHealthResponse | null>(null)
const loading = ref(false)
const presetsLoading = ref(false)
const interestProfilesLoading = ref(false)
const interestProfilesSaving = ref(false)
const interestProfilesError = ref('')
const telegramConnectLoading = ref(false)
const telegramConnectUrl = ref('')
const telegramConnectExpiresAt = ref('')
const analysisConfigLoading = ref(false)
const analysisConfigSaving = ref(false)
const analysisConfigError = ref('')
const errorMessage = ref('')
const procurementLots = ref<ProcurementLot[]>([])
const procurementTotal = ref(0)
const procurementLoading = ref(false)
const procurementError = ref('')
const lastLoadedAt = ref<string | null>(null)
const backgroundStatus = ref('Ожидаем фоновое обновление')
const selectedLot = ref<GridLotRow | null>(null)
const selectedLotDetails = ref<LotDetailResponse | null>(null)
const selectedAuctionDetails = ref<AuctionDetailResponse | null>(null)
const selectedWorkspace = ref<LotWorkspaceResponse | null>(null)
const selectedDecisionReport = ref<LotDecisionReport | null>(null)
const decisionReportLoading = ref(false)
const decisionReportStatus = ref<'idle' | 'empty' | 'error'>('idle')
const decisionReportError = ref('')
const detailLoading = ref(false)
const detailLiveRefreshing = ref(false)
const detailReanalyzing = ref(false)
const detailStatus = ref('')
const DETAIL_PANE_WIDTH_STORAGE_KEY = 'auction-detail-pane-width'
const GRID_COLUMN_WIDTHS_STORAGE_KEY = 'auction-grid-column-widths-v1'
const SERVER_FILTERS_STORAGE_KEY = 'auction-server-filters'
const AUCTION_GRID_CHANGES_POLL_INTERVAL_MS = 3_000
const AUCTION_GRID_CHANGES_REFRESH_DEBOUNCE_MS = 300
const CATALOG_TOTAL_ROW_LIMIT = 1_000_000
const CATALOG_SERVER_FETCH_LIMIT = 10_000
const CATALOG_ROW_CACHE_LIMIT = 20_000
const DETAIL_PANE_DEFAULT_WIDTH = 720
const DETAIL_PANE_MIN_WIDTH = 420
const DETAIL_PANE_MAX_WIDTH = 980
const LOTS_RELOAD_DELAY_MS = 400
const CATALOG_FILTER_SYNC_DELAY_MS = LOTS_RELOAD_DELAY_MS
const SYNC_PROGRESS_RELOAD_INTERVAL_MS = 30_000
const SERVER_ROW_MODEL_INITIAL_FETCH_SIZE = 256
const advancedFilterOptions = catalogAdvancedFilterOptions
const quickFilter = catalogQuickFilter
const DETAIL_FETCH_TIMEOUT_MS = 15_000
const DETAIL_RENDER_RAW_FIELDS_LIMIT = 120
const DETAIL_RENDER_DOCUMENTS_LIMIT = 120
const DETAIL_RENDER_IMAGES_LIMIT = 80
const DETAIL_RENDER_PRICE_SCHEDULE_LIMIT = 120
const DETAIL_RENDER_CHANGE_FIELDS_LIMIT = 40
const DETAIL_RENDER_TEXT_LIMIT = 2_000
const LOADING_SKELETON_MIN_ROWS = 16
const LOADING_SKELETON_TOOLBAR_HEIGHT = 42
const LOADING_SKELETON_HEADER_HEIGHT = 34
const LOADING_SKELETON_ROW_HEIGHT = 26
const detailPaneWidth = ref(readStoredDetailPaneWidth(DETAIL_PANE_WIDTH_STORAGE_KEY, {
  defaultWidth: DETAIL_PANE_DEFAULT_WIDTH,
  minWidth: DETAIL_PANE_MIN_WIDTH,
  maxWidth: DETAIL_PANE_MAX_WIDTH,
}))
const gridRef = ref<AuctionWorkspaceExposed | null>(null)
const gridSurfaceRef = ref<HTMLElement | null>(null)
const gridColumnWidths = ref(readStoredGridColumnWidths(GRID_COLUMN_WIDTHS_STORAGE_KEY))
const gridRowsById = shallowRef(new Map<string, GridLotRow>())
const catalogGridHasLoadedOnce = ref(false)
const gridRowRevision = ref(0)
const latestAuctionGridDatasetVersion = ref<number | null>(null)
const auctionHistoryState = reactive({
  canUndo: false,
  canRedo: false,
  latestUndoOperationId: null as string | null,
  latestRedoOperationId: null as string | null,
  datasetVersion: null as number | null,
})
const loadingSkeletonVisibleRows = ref(LOADING_SKELETON_MIN_ROWS)
let resizeStartX = 0
let resizeStartWidth = 0
let detailRequestId = 0
let decisionReportRequestId = 0
let detailAbortController: AbortController | null = null
let detailGridFocusAnchor: DataGridFocusAnchor | null = null
let detailLiveRefreshTimeout: ReturnType<typeof window.setTimeout> | null = null
const queuedRowUpdates = new Map<string, ApiLotRow>()
const catalogDataSourceListeners = new Set<DataGridDataSourcePushListener<GridLotRow>>()
let rowUpdateFrame: number | null = null
let deferredLotsReloadTimer: ReturnType<typeof window.setTimeout> | null = null
let deferredLotsReloadShouldResetViewport = false
let lastLotsReloadStartedAt = 0
let catalogPullRequestSeq = 0
let catalogSoftReloadSeq = 0
let catalogSoftRefreshAbortController: AbortController | null = null
let catalogFilterSyncTimer: ReturnType<typeof window.setTimeout> | null = null
let catalogFilterSyncSignature = ''
let catalogQueryScopeSyncSignature = ''
let keepCatalogEditErrorOnNextPull = false
const catalogFetchRequests = new Map<string, Promise<LotsResponse>>()
let auctionGridChangesPollTimer: ReturnType<typeof window.setTimeout> | null = null
let auctionGridChangesRefreshTimer: ReturnType<typeof window.setTimeout> | null = null
let auctionGridChangesPolling = false
let auctionGridChangesRefreshInFlight = false
let gridSurfaceResizeObserver: ResizeObserver | null = null
let auctionHistoryStatusUnsubscribe: (() => void) | null = null

const DEFAULT_SERVER_FILTERS: ServerQuickFiltersState = {
  period: 'month',
  source: 'tbankrot',
  analysisColor: '',
  status: '',
  minPrice: '',
  maxPrice: '',
  onlyNew: false,
  shortlist: false,
  minRating: 0,
  includeArchived: false,
}
const SHORTLIST_DECISIONS = new Set(['watch', 'calculate', 'inspection', 'bid'])

const filters = reactive(readStoredServerFilters(SERVER_FILTERS_STORAGE_KEY, DEFAULT_SERVER_FILTERS))

const emptyWorkDraft = (): WorkDraft => ({
  decision_status: '',
  assignee: '',
  comment: '',
  inspection_at: '',
  inspection_result: '',
  final_decision: '',
  investor: '',
  deposit_status: '',
  application_status: '',
  exclude_from_analysis: false,
  exclusion_reason: '',
  category_override: '',
  market_value: '',
  platform_fee: '',
  delivery_cost: '',
  dismantling_cost: '',
  repair_cost: '',
  storage_cost: '',
  legal_cost: '',
  other_costs: '',
  target_profit: '',
})

const EDITABLE_GRID_COLUMN_KEYS = AUCTION_GRID_EDITABLE_COLUMN_IDS

const savedGridWorkSnapshots = new Map<string, string>()
const loadedGridRowIds = new Set<string>()
const workDraft = reactive<WorkDraft>(emptyWorkDraft())
const emptyAnalysisConfigDraft = (): AnalysisConfigDraft => ({
  categoryRules: [],
  exclusionKeywordsText: '',
  highRiskKeywordsText: '',
  mediumRiskKeywordsText: '',
  mediumRiskCategoriesText: '',
})
const analysisConfigDraft = reactive<AnalysisConfigDraft>(emptyAnalysisConfigDraft())
const authStore = useAuthStore()
const { accessToken, currentUser, isAuthenticated, isRestoring } = storeToRefs(authStore)
const route = useRoute()
const router = useRouter()
const {
  selectedPresetId,
  presetDialogMode,
  presetNameDraft,
  telegramPresetIdDraft,
  mobileRailOpen,
  accountMenuRef,
  accountMenuOpen,
  presetDialogTriggerRef,
  presetDialogRef,
  presetDialogInitialRef,
  presetDialog,
  setPresetDialogInitialRef,
  setAnalysisConfigInitialRef,
  closeMobileRail,
  toggleMobileRail,
} = useAppUiState()
let analysisConfigRuleSeed = 0

const loadingSkeletonColumns = catalogLoadingSkeletonColumns
const loadingSkeletonRows = computed(() => Array.from({ length: loadingSkeletonVisibleRows.value }, (_, index) => index))
const loadingSkeletonTemplate = catalogLoadingSkeletonColumns.map((column) => `${column.width}px`).join(' ')
const columns = createAuctionGridColumns(openLotDetails)
const columnMenuOptions = createAuctionColumnMenuOptions(columns)

function resolveClientGridRowId(row: Pick<GridLotRow, 'id'>) {
  return row.id
}

const catalogRowModel = shallowRef<CatalogRowModel | null>(null)
const isGridCellEditable = ({ column }: { column: { key: string } }) => EDITABLE_GRID_COLUMN_KEYS.has(column.key)
const editableGridCellStyle: DataGridCellStyleResolver = (_row, _rowIndex, column) => {
  if (!EDITABLE_GRID_COLUMN_KEYS.has(column.key)) return null
  return {
    backgroundColor: 'rgba(255, 244, 199, 0.28)',
  }
}
const isMobileViewport = ref(false)
const columnLayoutOptions = {
  buttonLabel: 'Колонки',
  labels: {
    buttonLabel: 'Колонки',
    eyebrow: 'Колонки',
    title: 'Настройка колонок',
    close: 'Закрыть',
    cancel: 'Отмена',
    apply: 'Применить',
    moveUp: 'Выше',
    moveDown: 'Ниже',
  },
}
const gridStatePersistence = catalogGridStatePersistence

const catalogPresetOptions = computed(() => [
  { label: 'Без среза', value: '' },
  ...presets.value.map((preset) => ({
    label: preset.is_favorite ? `${preset.name} *` : preset.name,
    value: preset.id,
  })),
])
const catalogFilterModel = computed(() => buildCatalogFilterModel(filters))
const hasCatalogAppliedFilters = computed(() => hasGridFilterModel(catalogFilterModel.value))
const canUpdateCatalogPreset = computed(() => Boolean(selectedPreset.value) && hasCatalogAppliedFilters.value)
const activeModule = computed(() => {
  if (route.name === 'analysis-config') return 'analysis-config'
  if (route.name === 'interest-profiles') return 'interest-profiles'
  if (route.name === 'diagnostics') return 'diagnostics'
  if (route.name === 'tenders') return 'tenders'
  if (route.name === 'help') return 'help'
  return 'auctions'
})
const isAuctionsModule = computed(() => activeModule.value === 'auctions')
const isTendersModule = computed(() => activeModule.value === 'tenders')
const isHelpModule = computed(() => activeModule.value === 'help')
const isDiagnosticsModule = computed(() => activeModule.value === 'diagnostics')
const helpDocumentHtml = computed(() => renderHelpMarkdown(howItWorksMarkdown))
const currentUserInitials = computed(() => {
  const tokens = currentUser.value?.full_name
    ?.split(/\s+/)
    .map((value) => value.trim())
    .filter(Boolean) ?? []

  if (!tokens.length) return 'AU'

  return tokens
    .slice(0, 2)
    .map((token) => token.charAt(0).toUpperCase())
    .join('')
})

const selectedPreset = computed(() => presets.value.find((preset) => preset.id === selectedPresetId.value) ?? null)
const isAnalysisConfigRoute = computed(() => route.name === 'analysis-config')
const isInterestProfilesRoute = computed(() => route.name === 'interest-profiles')
const presetDialogTitle = computed(() => {
  if (presetDialogMode.value === 'delete') return 'Удалить срез'
  if (presetDialogMode.value === 'update') return 'Обновить срез'
  return 'Сохранить срез'
})
const presetDialogDescription = computed(() => {
  if (presetDialogMode.value === 'delete') {
    return `Срез "${selectedPreset.value?.name ?? ''}" будет удален без возможности восстановления.`
  }
  if (presetDialogMode.value === 'update') {
    return 'Обновим имя среза и сохраним текущее состояние фильтров и таблицы.'
  }
  return 'Сохраним текущие фильтры и раскладку таблицы как новый срез.'
})
const presetDialogSubmitLabel = computed(() => {
  if (presetDialogMode.value === 'delete') return 'Удалить'
  if (presetDialogMode.value === 'update') return 'Обновить'
  return 'Сохранить'
})
const analysisConfigUpdatedAt = computed(() => formatDateTime(analysisConfig.value?.updated_at ?? null))

const totalRows = computed(() => catalogSummary.value.total || catalogTotal.value)
const loadedRowsCount = computed(() => allRows.value.length)
const activeRowsCount = computed(() => catalogSummary.value.activeCount)
const newCount = computed(() => catalogSummary.value.newCount)
const highRatingCount = computed(() => catalogSummary.value.highRatingCount)

const {
  detailTitle,
  liveAuction,
  liveLot,
  liveOrganizer,
  liveDebtor,
  detailLotUrl,
  detailAuctionUrl,
  detailFields,
  lotInfoFields,
  lotTextFields,
  priceScheduleSteps,
  priceScheduleFields,
  organizerFields,
  auctionInfoFields,
  debtorFields,
  rawLotFields,
  rawAuctionFields,
  auctionLots,
  economyFields,
  decisionReportSummaryFields,
  decisionReportReasons,
  decisionReportRisks,
  decisionReportNextActions,
  analysisReasonItems,
  detailCachedAt,
  selectedSourceSyncStatus,
  selectedCurrentEnrichmentState,
  detailActualityFields,
  changeFields,
  changeSummaryFields,
  detailDocuments,
  detailImages,
  lockedTbankrotImageCount,
  mediaDocuments,
  fileDocuments,
  activeDetailImageIndex,
  activeDetailImage,
  selectDetailImage,
  showPreviousDetailImage,
  showNextDetailImage,
} = useAuctionDetailState({
  selectedLot,
  selectedLotDetails,
  selectedAuctionDetails,
  selectedWorkspace,
  selectedDecisionReport,
  auctionPipelineHealth,
})

watch(
  () => route.fullPath,
  () => {
    closeMobileRail()
  },
)

watch(activeModule, (module) => {
    if (!isAuthenticated.value) return
    if (module === 'auctions') {
      void loadLots()
      startAuctionEvents()
      startAuctionGridChangePolling(0)
      void nextTick(() => startGridSurfaceResizeObserver())
      return
    }
    stopGridSurfaceResizeObserver()
    stopAuctionEvents()
    stopAuctionGridChangePolling()
    catalogSoftRefreshAbortController?.abort()
    catalogSoftRefreshAbortController = null
})

function setGridColumnWidths(widths: unknown, options: { persist?: boolean } = {}) {
  const nextWidths = sanitizeGridColumnWidths(widths)
  gridColumnWidths.value = nextWidths
  if (options.persist !== false) {
    window.localStorage.setItem(GRID_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(nextWidths))
  }
  return nextWidths
}

function ensureCatalogServerViewport(preferredRange?: { start: number; end: number } | null) {
  const size = resolveCatalogServerViewportSize(
    preferredRange,
    catalogRowModel.value?.getSnapshot().viewportRange,
    {
      initialFetchSize: SERVER_ROW_MODEL_INITIAL_FETCH_SIZE,
      serverFetchLimit: CATALOG_SERVER_FETCH_LIMIT,
    },
  )
  const rowModel = catalogRowModel.value
  if (!rowModel) return false

  const nextRange = { start: 0, end: size - 1 }
  const currentSnapshot = rowModel.getSnapshot()
  const currentRange = currentSnapshot.viewportRange
  rowModel.setViewportRange(nextRange)
  const appliedRange = rowModel.getSnapshot().viewportRange
  return currentRange.start !== appliedRange.start || currentRange.end !== appliedRange.end
}

function expandCollapsedCatalogServerViewport() {
  const range = catalogRowModel.value?.getSnapshot().viewportRange
  if (resolveViewportRangeSize(range) > 1) return false
  return ensureCatalogServerViewport()
}

function applyGridSavedView(savedView: DataGridSavedViewSnapshot<GridLotRow & Record<string, unknown>>) {
  if (!gridRef.value) return false

  return gridRef.value.applySavedView(savedView, {
    dataSource: {
      atomic: true,
      resetViewportRange: buildCatalogServerViewportRange(savedView.state.rows.snapshot.viewportRange),
    },
  })
}

function persistGridColumnWidths(widths: Readonly<Record<string, number | null>> | null) {
  setGridColumnWidths(widths)
}

function writeGridSavedView(view: unknown | null) {
  if (!gridRef.value || !view) return
  const migratedView = view as NonNullable<ReturnType<NonNullable<typeof gridRef.value>['getSavedView']>>
  const stableView = sanitizeGridSavedView(migratedView)
  setGridColumnWidths(stableView.state.columns.widths)
  applyGridSavedView(stableView)
  scheduleGridSummaryRefresh()
}

function clearCatalogFilterSyncTimer() {
  if (catalogFilterSyncTimer === null) return
  window.clearTimeout(catalogFilterSyncTimer)
  catalogFilterSyncTimer = null
}

function syncCatalogFilterModel() {
  clearCatalogFilterSyncTimer()
  const rowModel = catalogRowModel.value
  if (!rowModel) return
  const nextFilterSignature = serializeCatalogFilterModel(filters)
  const nextQueryScopeSignature = serializeCatalogQueryScope(filters)
  const filterChanged = nextFilterSignature !== catalogFilterSyncSignature
  const queryScopeChanged = nextQueryScopeSignature !== catalogQueryScopeSyncSignature
  if (!filterChanged && !queryScopeChanged) return
  catalogFilterSyncSignature = nextFilterSignature
  catalogQueryScopeSyncSignature = nextQueryScopeSignature
  if (filterChanged) {
    rowModel.setFilterModel(buildCatalogFilterModel(filters))
    return
  }
  void rowModel.refresh('manual')
}

function scheduleCatalogFilterSync() {
  clearCatalogFilterSyncTimer()
  catalogFilterSyncTimer = window.setTimeout(() => {
    catalogFilterSyncTimer = null
    syncCatalogFilterModel()
  }, CATALOG_FILTER_SYNC_DELAY_MS)
}

async function postAuctionServerGridJson<TResponse>(path: string, payload: unknown, signal?: AbortSignal) {
  return fetchJson<TResponse>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

async function postProcurementServerGridJson<TResponse>(path: string, payload: unknown, signal?: AbortSignal) {
  return fetchJson<TResponse>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

async function getProcurementServerJson<TResponse>(path: string, signal?: AbortSignal) {
  return fetchJson<TResponse>(path, { signal })
}

function createAuctionServerCatalogDataSource(): CatalogAuctionServerDataSource {
  return createAuctionServerDatasource<ApiLotRow, GridLotRow>({
    postJson: postAuctionServerGridJson,
    getJson: (path, signal) => fetchJson(path, { signal }),
    getFilters: () => buildAuctionServerGridFilters(filters),
    hasFilterModel: hasGridFilterModel,
    mapRow: mapApiRow,
    allocateRowRevision() {
      const nextRevision = gridRowRevision.value + 1
      gridRowRevision.value = nextRevision
      return nextRevision
    },
    onPullCompleted({ rows, total, datasetVersion, summary, reason, priority }) {
      const isBackgroundPrefetch = reason === 'prefetch' || priority === 'background'
      latestAuctionGridDatasetVersion.value = datasetVersion
      catalogTotal.value = total
      catalogSummary.value = summary
      rememberLoadedRows(rows, { trackLoadedRows: !isBackgroundPrefetch })
      if (!isBackgroundPrefetch) {
        lastLoadedAt.value = new Date().toLocaleString('ru-RU')
        startAuctionGridChangePolling()
      }
    },
  })
}

const auctionServerDataSource = createAuctionServerCatalogDataSource()

const auctionGridHistoryOptions = computed<DataGridHistoryProp>(() => {
  const canUndo = auctionHistoryState.canUndo
  const canRedo = auctionHistoryState.canRedo
  return {
    enabled: true,
    shortcuts: 'grid',
    controls: true,
    adapter: {
      captureSnapshot: () => null,
      recordIntentTransaction: () => undefined,
      canUndo: () => canUndo,
      canRedo: () => canRedo,
      runHistoryAction: runAuctionGridHistoryAction,
    },
  }
})

function rememberLoadedRows(rows: GridLotRow[], options: { trackLoadedRows?: boolean } = {}) {
  const trackLoadedRows = options.trackLoadedRows !== false
  const byId = gridRowsById.value
  for (const row of rows) {
    const existing = byId.get(row.id)
    if (existing) {
      Object.assign(existing, row, { rowRevision: existing.rowRevision })
      if (trackLoadedRows && !loadedGridRowIds.has(existing.id)) {
        loadedGridRowIds.add(existing.id)
        allRows.value.push(existing)
      }
      rememberGridWorkSnapshot(existing)
      continue
    }
    byId.set(row.id, row)
    if (trackLoadedRows) {
      loadedGridRowIds.add(row.id)
      allRows.value.push(row)
    }
    rememberGridWorkSnapshot(row)
  }
}

function startUiPerfTrace(_name: string, _context: Record<string, unknown> = {}) {
  return {
    end(_extra: Record<string, unknown> = {}) {},
  }
}

async function requestAuctionServerLotsWindow(request: {
  start: number
  end: number
  signal?: AbortSignal
  sortModel?: readonly DataGridSortState[]
  filterModel?: DataGridFilterSnapshot | null
}) {
  const snapshot = catalogRowModel.value?.getSnapshot()
  const snapshotFilterModel = snapshot?.filterModel ?? null
  const effectiveFilterModel = hasGridFilterModel(request.filterModel)
    ? request.filterModel ?? null
    : hasGridFilterModel(snapshotFilterModel)
      ? snapshotFilterModel
      : request.filterModel ?? null
  return auctionServerDataSource.pullWindow({
    start: Math.max(0, request.start),
    end: Math.max(Math.max(0, request.start), request.end),
    signal: request.signal,
    sortModel: request.sortModel ?? snapshot?.sortModel,
    filterModel: effectiveFilterModel,
    reason: 'manual-window',
    priority: 'normal',
  })
}

async function fetchLotsRange(request: {
  start: number
  end: number
  signal?: AbortSignal
  sortModel?: readonly DataGridSortState[]
  filterModel?: DataGridFilterSnapshot | null
}) {
  if (request.signal?.aborted) {
    throw new DOMException('Request aborted', 'AbortError')
  }
  return requestAuctionServerLotsWindow({
    start: Math.max(0, request.start),
    end: Math.max(Math.max(0, request.start), request.end),
    signal: request.signal,
    sortModel: request.sortModel,
    filterModel: request.filterModel,
  })
}

function clearCatalogViewportDim() {
  // Legacy query-busy overlay removed. Keep the hook as a no-op so callers stay simple.
}

function createCatalogDataSource(): CatalogDataSource {
  return {
    ...auctionServerDataSource,
    subscribe(listener) {
      catalogDataSourceListeners.add(listener)
      return () => {
        catalogDataSourceListeners.delete(listener)
      }
    },
    async pull(request) {
      const requestSeq = catalogPullRequestSeq + 1
      catalogPullRequestSeq = requestSeq
      const isBackgroundPrefetch = request.reason === 'prefetch' || request.priority === 'background'
      if (!isBackgroundPrefetch && allRows.value.length === 0) {
        loading.value = true
      }
      if (!isBackgroundPrefetch) {
        if (keepCatalogEditErrorOnNextPull) {
          keepCatalogEditErrorOnNextPull = false
        } else {
          errorMessage.value = ''
        }
      }
      try {
        const effectiveFilterModel = resolveCatalogPullFilterModel(
          request.filterModel,
          request.reason,
          catalogRowModel.value?.getSnapshot().filterModel ?? null,
        )
        const result = await auctionServerDataSource.pull({
          ...request,
          range: request.range,
          filterModel: effectiveFilterModel,
        })
        return result
      } catch (error) {
        if (!isBackgroundPrefetch && !isAbortLikeError(error) && requestSeq === catalogPullRequestSeq) {
          errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить лоты'
        }
        throw error
      } finally {
        if (!isBackgroundPrefetch && requestSeq === catalogPullRequestSeq) {
          loading.value = false
          catalogGridHasLoadedOnce.value = true
        }
        if (!isBackgroundPrefetch) {
          scheduleGridSummaryRefresh()
        }
      }
    },
    getColumnHistogram(request) {
      return auctionServerDataSource.getColumnHistogram?.(request) ?? Promise.resolve([])
    },
    async commitEdits(request) {
      const commitEdits = auctionServerDataSource.commitEdits
      if (typeof commitEdits !== 'function') {
        throw new Error('Auction grid datasource does not support edits')
      }
      const result = await commitEdits(request)
      applyAuctionCommitResult(
        result as GridHistoryMutationResponse<ApiLotRow>,
        Array.isArray(request.edits) ? request.edits : [],
      )
      if (!result.rejected?.length) {
        errorMessage.value = ''
      }
      return result
    },
  }
}

function createCatalogRowModel(): CatalogRowModel {
  const rowModel = createDataSourceBackedRowModel({
    dataSource: createCatalogDataSource(),
    resolveRowId: resolveClientGridRowId,
    initialTotal: Math.min(CATALOG_TOTAL_ROW_LIMIT, Math.max(catalogTotal.value || 0, SERVER_ROW_MODEL_INITIAL_FETCH_SIZE)),
    initialFilterModel: buildCatalogFilterModel(filters),
    rowCacheLimit: CATALOG_ROW_CACHE_LIMIT,
    prefetch: catalogRowModelPrefetchOptions,
  }) as CatalogRowModel
  rowModel.patchRows = async (updates) => {
    if (!updates.length) return
    const commitEdits = rowModel.dataSource.commitEdits
    if (typeof commitEdits !== 'function') return
    await commitEdits({
      edits: updates,
    })
  }
  return rowModel
}

async function runAuctionGridHistoryAction(direction: 'undo' | 'redo') {
  const result = await postAuctionServerGridJson<GridHistoryMutationResponse<ApiLotRow>>(
    `/api/history/${direction}`,
    { table_id: 'auction-lots' },
  )
  if (applyAuctionMutationResult(result)) {
    errorMessage.value = ''
    return result.operationId ?? null
  }

  await catalogRowModel.value?.refresh('manual')
  errorMessage.value = ''
  return result.operationId ?? null
}

function updateAuctionHistoryState(status: GridHistoryStatusLike | null | undefined) {
  if (!status) return
  if (typeof status.canUndo === 'boolean') auctionHistoryState.canUndo = status.canUndo
  if (typeof status.canRedo === 'boolean') auctionHistoryState.canRedo = status.canRedo
  if (typeof status.latestUndoOperationId !== 'undefined') {
    auctionHistoryState.latestUndoOperationId = status.latestUndoOperationId ?? null
  }
  if (typeof status.latestRedoOperationId !== 'undefined') {
    auctionHistoryState.latestRedoOperationId = status.latestRedoOperationId ?? null
  }
  if (typeof status.datasetVersion !== 'undefined') {
    auctionHistoryState.datasetVersion = typeof status.datasetVersion === 'number' ? status.datasetVersion : null
  }
}

function applyAuctionMutationResult(result: GridHistoryMutationResponse<ApiLotRow> | null | undefined) {
  if (!result) return false
  updateAuctionHistoryState(result)
  if (typeof result.datasetVersion === 'number') {
    latestAuctionGridDatasetVersion.value = result.datasetVersion
  }

  const rows = result.rows?.length ? result.rows : result.updatedRows ?? []
  if (applyAuctionHistoryRows(rows)) return true

  if (result.invalidation) {
    return applyAuctionInvalidation(result.invalidation, result.datasetVersion)
  }

  return false
}

function applyAuctionPatchUpdates(updates: readonly { rowId: string | number; data: Partial<GridLotRow> }[]) {
  const entries: DataGridDataSourceRowEntry<GridLotRow>[] = []
  for (const update of updates) {
    const rowId = String(update.rowId)
    const existing = gridRowsById.value.get(rowId)
    if (!existing) continue

    const patched = recomputeGridEconomyFields({
      ...existing,
      ...update.data,
      id: existing.id,
      rowRevision: existing.rowRevision,
    })
    gridRowsById.value.set(patched.id, patched)

    const rowIndex = allRows.value.findIndex((row) => row.id === patched.id)
    if (rowIndex >= 0) {
      allRows.value[rowIndex] = patched
    }
    if (selectedLot.value?.id === patched.id) {
      selectedLot.value = patched
    }
    rememberGridWorkSnapshot(patched)

    entries.push({
      index: rowIndex >= 0 ? rowIndex : 0,
      row: patched,
      rowId: patched.id,
    })
  }

  emitCatalogRowEntriesUpsert(entries)
  return entries.length > 0
}

function applyAuctionCommitResult(
  result: GridHistoryMutationResponse<ApiLotRow> | null | undefined,
  edits: readonly { rowId: string | number; data: Partial<GridLotRow> }[],
) {
  if (!result) return false
  updateAuctionHistoryState(result)
  if (typeof result.datasetVersion === 'number') {
    latestAuctionGridDatasetVersion.value = result.datasetVersion
  }

  const rows = result.rows?.length ? result.rows : result.updatedRows ?? []
  if (rows.length && applyAuctionHistoryRows(rows)) return true

  if (edits.length) {
    return applyAuctionPatchUpdates(edits)
  }

  return false
}

function applyAuctionGridChangeFeedResponse(response: GridChangeFeedResponse) {
  if (response.hasMore) return false

  const rows = collectAuctionChangeFeedRows(response)
  if (applyAuctionHistoryRows(rows)) {
    latestAuctionGridDatasetVersion.value = response.datasetVersion
    return true
  }

  const rowIds = collectGridChangeRowIds(response)
  if (rowIds.length) {
    if (applyAuctionInvalidation({ type: 'rows', rowIds, reason: 'change_feed' }, response.datasetVersion)) {
      latestAuctionGridDatasetVersion.value = response.datasetVersion
      return true
    }
  }

  for (const change of response.changes) {
    const invalidation = normalizeDatasourceInvalidation(change.payload.invalidation ?? change.payload)
    if (!invalidation) continue
    if (applyAuctionInvalidation(invalidation, response.datasetVersion)) {
      latestAuctionGridDatasetVersion.value = response.datasetVersion
      return true
    }
  }

  return false
}

function collectAuctionChangeFeedRows(response: GridChangeFeedResponse) {
  const rows: GridHistoryRowSnapshot<ApiLotRow>[] = []
  for (const change of response.changes) {
    const payload = change.payload
    const payloadRows = payload.rows ?? payload.updatedRows
    if (Array.isArray(payloadRows)) {
      rows.push(...payloadRows as GridHistoryRowSnapshot<ApiLotRow>[])
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

function applyAuctionHistoryRows(rows: readonly GridHistoryRowSnapshot<ApiLotRow>[]) {
  if (!rows.length) return false

  const updatesByRowId = new Map<string, { rowId: string | number; data: Partial<GridLotRow> }>()
  for (const snapshot of rows) {
    const row = extractHistorySnapshotRow(snapshot)
    if (isAuctionApiHistoryRow(row)) {
      const mapped = mapApiRow(row)
      updatesByRowId.set(mapped.id, {
        rowId: mapped.id,
        data: mapped,
      })
    } else if (isAuctionGridHistoryRow(row)) {
      updatesByRowId.set(row.id, {
        rowId: row.id,
        data: row,
      })
    }
  }

  const updates = [...updatesByRowId.values()]
  return applyAuctionPatchUpdates(updates)
}

function extractHistorySnapshotRow<TApiRow>(snapshot: GridHistoryRowSnapshot<TApiRow>) {
  if (snapshot && typeof snapshot === 'object' && 'row' in snapshot) {
    return snapshot.row
  }
  return snapshot
}

function isAuctionApiHistoryRow(value: unknown): value is ApiLotRow {
  return Boolean(value && typeof value === 'object' && typeof (value as { row_id?: unknown }).row_id === 'string')
}

function isAuctionGridHistoryRow(value: unknown): value is GridLotRow {
  return Boolean(value && typeof value === 'object' && typeof (value as { id?: unknown }).id === 'string' && 'lotName' in value)
}

function emitCatalogRowsUpsert(rows: readonly GridLotRow[], total: number, startIndex: number) {
  emitCatalogRowEntriesUpsert(
    rows.map((row, index) => ({
      index: startIndex + index,
      row,
      rowId: row.id,
    })),
    total,
  )
}

function emitCatalogRowEntriesUpsert(rows: readonly DataGridDataSourceRowEntry<GridLotRow>[], total?: number) {
  if (!catalogDataSourceListeners.size || !rows.length) return

  const event = {
    type: 'upsert' as const,
    ...(typeof total === 'number' ? { total } : {}),
    rows,
  }
  for (const listener of catalogDataSourceListeners) {
    listener(event)
  }
}

function subscribeAuctionHistoryStatus() {
  auctionHistoryStatusUnsubscribe?.()
  const source = auctionServerDataSource as unknown as HistoryStatusSource
  auctionHistoryStatusUnsubscribe = source.subscribeHistoryStatus?.(updateAuctionHistoryState) ?? null
}

function applyAuctionInvalidation(invalidation: unknown, datasetVersion: number | null | undefined) {
  const normalized = normalizeDatasourceInvalidation(invalidation)
  if (!normalized) return false
  auctionServerDataSource.applyInvalidation?.(normalized, { datasetVersion: datasetVersion ?? undefined })
  return true
}

function resolveCatalogReloadRange() {
  const snapshot = catalogRowModel.value?.getSnapshot()
  const viewportRange = snapshot?.viewportRange
  const rowCount = snapshot?.rowCount ?? catalogTotal.value
  const size = resolveCatalogServerViewportSize(
    viewportRange,
    snapshot?.viewportRange,
    {
      initialFetchSize: SERVER_ROW_MODEL_INITIAL_FETCH_SIZE,
      serverFetchLimit: CATALOG_SERVER_FETCH_LIMIT,
    },
  )
  const start = Math.max(0, viewportRange?.start ?? 0)
  const maxStart = Math.max(0, rowCount - 1)
  const safeStart = Math.min(start, maxStart)
  return {
    start: safeStart,
    end: Math.min(Math.max(0, rowCount - 1), safeStart + size - 1),
  }
}

async function softRefreshCatalogRows(options: {
  range?: { start: number; end: number }
  expandViewportAfter?: boolean
  sortModel?: readonly DataGridSortState[]
  filterModel?: DataGridFilterSnapshot | null
} = {}) {
  if (!isAuctionsModule.value || !isAuthenticated.value || !catalogRowModel.value) return

  const reloadSeq = catalogSoftReloadSeq + 1
  catalogSoftReloadSeq = reloadSeq
  catalogSoftRefreshAbortController?.abort()
  const controller = new AbortController()
  catalogSoftRefreshAbortController = controller
  const range = options.range ?? resolveCatalogReloadRange()
  try {
    const result = await fetchLotsRange({
      start: range.start,
      end: range.end,
      signal: controller.signal,
      sortModel: options.sortModel,
      filterModel: options.filterModel,
    })
    if (reloadSeq !== catalogSoftReloadSeq) return
    latestAuctionGridDatasetVersion.value = result.datasetVersion
    catalogTotal.value = result.total
    catalogSummary.value = result.summary
    rememberLoadedRows(result.rows)
    lastLoadedAt.value = new Date().toLocaleString('ru-RU')
    startAuctionGridChangePolling()
    emitCatalogRowsUpsert(result.rows, result.total, result.start)
    if (options.expandViewportAfter === true) {
      ensureCatalogServerViewport(range)
    }
    errorMessage.value = ''
  } catch (error) {
    if (!isAbortLikeError(error) && reloadSeq === catalogSoftReloadSeq) {
      errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить лоты'
    }
  } finally {
    if (catalogSoftRefreshAbortController === controller) {
      catalogSoftRefreshAbortController = null
    }
    scheduleGridSummaryRefresh()
  }
}

function resetCatalogRowModel() {
  clearCatalogFilterSyncTimer()
  catalogRowModel.value?.dispose()
  catalogDataSourceListeners.clear()
  clearCatalogViewportDim()
  allRows.value = []
  loadedGridRowIds.clear()
  gridRowsById.value.clear()
  catalogSummary.value = {
    total: 0,
    newCount: 0,
    activeCount: 0,
    openApplicationsCount: 0,
    highRatingCount: 0,
  }
  catalogGridHasLoadedOnce.value = false
  catalogRowModel.value = createCatalogRowModel()
  catalogFilterSyncSignature = serializeCatalogFilterModel(filters)
  catalogQueryScopeSyncSignature = serializeCatalogQueryScope(filters)
}

async function loadLots() {
  if (!isAuctionsModule.value || !isAuthenticated.value) return
  resetCatalogRowModel()
  savedGridWorkSnapshots.clear()
  await nextTick()
  const viewportChanged = ensureCatalogServerViewport({ start: 0, end: SERVER_ROW_MODEL_INITIAL_FETCH_SIZE - 1 })
  if (!viewportChanged) {
    await catalogRowModel.value?.refresh('manual')
  }
  void loadAuctionPipelineHealth()
}

function matchesQuickFilters(row: GridLotRow) {
  if (filters.source !== 'all' && row.source !== filters.source) return false
  if (filters.analysisColor && row.analysisColor !== filters.analysisColor) return false
  if (filters.status && row.status !== filters.status) return false
  if (filters.onlyNew && !row.isNew) return false
  if (filters.shortlist && row.ratingScore < 85 && !SHORTLIST_DECISIONS.has(row.workDecisionStatus)) return false
  if (filters.minRating > 0 && row.ratingScore < filters.minRating) return false

  const minPrice = parseFilterNumber(filters.minPrice)
  if (minPrice !== null && (row.price === null || row.price < minPrice)) return false

  const maxPrice = parseFilterNumber(filters.maxPrice)
  if (maxPrice !== null && (row.price === null || row.price > maxPrice)) return false

  return true
}

function parseFilterNumber(value: string) {
  const normalized = value.trim().replace(/\s+/g, '').replace(',', '.')
  if (!normalized) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function mapApiRow(row: ApiLotRow, rowRevision = gridRowRevision.value): GridLotRow {
  return recomputeGridEconomyFields({
    id: row.row_id,
    rowRevision,
    analysisStatus: row.analysis.status,
    analysisColor: row.analysis.color,
    analysisLabel: row.analysis.label,
    analysisCategory: row.category ?? row.model_category ?? row.analysis.category ?? '',
    analysisReasons: Array.isArray(row.analysis.reasons) ? row.analysis.reasons : [],
    source: row.source,
    sourceTitle: row.source_title,
    auctionId: row.auction_id ?? '',
    auctionNumber: row.auction_number ?? '',
    auctionName: row.auction_name ?? '',
    publicationDate: parseDateTime(row.publication_date),
    lotId: row.lot_id ?? '',
    lotNumber: row.lot_number ?? '',
    lotName: row.lot_name ?? '',
    lotDescription: row.lot_description ?? '',
    location: row.location ?? '',
    locationRegion: row.location_region ?? '',
    locationCity: row.location_city ?? '',
    locationAddress: row.location_address ?? '',
    locationCoordinates: row.location_coordinates ?? '',
    debtorName: row.debtor_name ?? '',
    status: row.status ?? '',
    initialPrice: parseNumber(row.initial_price_value),
    price: parseNumber(row.current_price_value ?? row.initial_price_value),
    minimumPrice: parseNumber(row.minimum_price_value),
    marketValue: parseNumber(row.market_value),
    priceSchedule: row.price_schedule ?? [],
    platformFee: parseNumber(row.platform_fee) ?? 0,
    deliveryCost: parseNumber(row.delivery_cost) ?? 0,
    dismantlingCost: parseNumber(row.dismantling_cost) ?? 0,
    repairCost: parseNumber(row.repair_cost) ?? 0,
    storageCost: parseNumber(row.storage_cost) ?? 0,
    legalCost: parseNumber(row.legal_cost) ?? 0,
    otherCosts: parseNumber(row.other_costs) ?? 0,
    targetProfit: parseNumber(row.target_profit) ?? 0,
    totalExpenses: parseNumber(row.total_expenses),
    fullEntryCost: parseNumber(row.full_entry_cost),
    potentialProfit: parseNumber(row.potential_profit),
    roiValue: parseNumber(row.roi),
    marketDiscount: parseNumber(row.market_discount),
    formulaMaxPurchasePrice: parseNumber(row.formula_max_purchase_price),
    excludeFromAnalysis: row.exclude_from_analysis,
    exclusionReason: row.exclusion_reason ?? '',
    organizer: row.organizer_name ?? '',
    applicationDeadline: parseDateTime(row.application_deadline),
    auctionDate: parseDateTime(row.auction_date),
    isNew: row.freshness.is_new,
    firstSeenAt: parseDateTime(row.freshness.first_seen_at),
    lastSeenAt: parseDateTime(row.freshness.last_seen_at),
    lifecycleStatus: row.lifecycle_status ?? 'active',
    actualityCheckedAt: parseDateTime(row.actuality_checked_at),
    ratingScore: row.rating.score,
    ratingLevel: row.rating.level,
    ratingReasons: Array.isArray(row.rating.reasons) ? row.rating.reasons : [],
    ratingBreakdown: row.rating.breakdown ?? null,
    workDecisionStatus: row.work_decision_status ?? '',
    lotUrl: row.lot_url ?? '',
    auctionUrl: row.auction_url ?? '',
    images: row.images ?? [],
    primaryImageUrl: row.primary_image_url ?? '',
    imageCount: row.image_count ?? row.images?.length ?? 0,
  })
}

function applyWorkspaceRow(row: ApiLotRow, options: { clearOptimistic?: boolean; refreshSummary?: boolean } = {}) {
  applyWorkspaceRows([row], options)
}

function applyWorkspaceRows(
  rows: ApiLotRow[],
  options: { clearOptimistic?: boolean; refreshSummary?: boolean; patchGrid?: boolean } = {},
) {
  if (!rows.length) return
  const trace = startUiPerfTrace('applyWorkspaceRows', {
    rowCount: rows.length,
    refreshSummary: options.refreshSummary !== false,
    clearOptimistic: options.clearOptimistic === true,
  })
  const mappedUpdates: GridLotRow[] = []
  const byId = gridRowsById.value

  for (const update of rows) {
    const existing = byId.get(update.row_id)
    const nextRevision = existing?.rowRevision ?? gridRowRevision.value + 1
    if (!existing) {
      gridRowRevision.value = Math.max(gridRowRevision.value, nextRevision)
    }

    const mapped = mapApiRow(update, nextRevision)
    if (!existing && !matchesQuickFilters(mapped)) continue

    if (existing) {
      mapped.rowRevision = existing.rowRevision
      byId.set(mapped.id, mapped)
      const rowIndex = allRows.value.findIndex((row) => row.id === mapped.id)
      if (rowIndex >= 0) {
        allRows.value[rowIndex] = mapped
      }
      mappedUpdates.push(mapped)
    } else {
      byId.set(mapped.id, mapped)
      loadedGridRowIds.add(mapped.id)
      allRows.value.push(mapped)
      mappedUpdates.push(mapped)
    }
  }

  if (!mappedUpdates.length) return
  if (options.patchGrid !== false) {
    applyExternalGridRowUpdates(mappedUpdates, { recompute: true })
  }
  if (options.refreshSummary !== false) {
    scheduleGridSummaryRefresh()
  }

  for (const mapped of mappedUpdates) {
    if (selectedLot.value?.id === mapped.id) {
      selectedLot.value = mapped
    }
    rememberGridWorkSnapshot(mapped)
  }

  if (selectedWorkspace.value) {
    const workspaceRow = rows.find((row) => row.row_id === selectedWorkspace.value?.row.row_id)
    if (workspaceRow) {
      selectedWorkspace.value = {
        ...selectedWorkspace.value,
        row: workspaceRow,
      }
    }
  }
  trace.end({ updatedCount: mappedUpdates.length })
}

function applyExternalGridRowUpdates(
  rows: readonly GridLotRow[],
  options: { recompute?: boolean } = {},
) {
  const api = gridRef.value?.getApi()
  if (!api?.rows.hasExternalUpdateSupport() || !rows.length) return

  const updates: DataGridExternalRowUpdate<GridLotRow>[] = rows.map((row) => ({
    rowId: resolveClientGridRowId(row),
    row,
  }))
  api.rows.applyExternalUpdates(updates, {
    recompute: options.recompute === false ? false : true,
  })
}

function scheduleGridSummaryRefresh() {
  return
}

function queueWorkspaceRows(rows: ApiLotRow[]) {
  for (const row of rows) {
    queuedRowUpdates.set(row.row_id, row)
  }
  if (rowUpdateFrame !== null) return
  rowUpdateFrame = window.requestAnimationFrame(flushQueuedWorkspaceRows)
}

function flushQueuedWorkspaceRows() {
  rowUpdateFrame = null
  const rows = Array.from(queuedRowUpdates.values())
  queuedRowUpdates.clear()
  applyWorkspaceRows(rows)
}

function scheduleLotsReload(
  delayMs = LOTS_RELOAD_DELAY_MS,
  replacePending = true,
  options: { resetViewport?: boolean } = {},
) {
  deferredLotsReloadShouldResetViewport ||= options.resetViewport === true
  if (deferredLotsReloadTimer !== null) {
    if (!replacePending) return
    window.clearTimeout(deferredLotsReloadTimer)
  }
  deferredLotsReloadTimer = window.setTimeout(() => {
    const shouldResetViewport = deferredLotsReloadShouldResetViewport
    deferredLotsReloadTimer = null
    deferredLotsReloadShouldResetViewport = false
    lastLotsReloadStartedAt = Date.now()
    const resetRange = shouldResetViewport ? buildCatalogServerViewportRange() : null
    const viewportChanged = resetRange ? ensureCatalogServerViewport(resetRange) : expandCollapsedCatalogServerViewport()
    if (resetRange) {
      void softRefreshCatalogRows({ range: resetRange, expandViewportAfter: true })
      return
    }
    if (!viewportChanged) {
      void softRefreshCatalogRows()
    }
  }, delayMs)
}

function scheduleProgressLotsReload() {
  const elapsedSinceLastReload = Date.now() - lastLotsReloadStartedAt
  const remainingDelay = Math.max(0, SYNC_PROGRESS_RELOAD_INTERVAL_MS - elapsedSinceLastReload)
  scheduleLotsReload(Math.max(LOTS_RELOAD_DELAY_MS, remainingDelay), false)
}

function recomputeGridEconomyFields(row: GridLotRow) {
  const totalExpenses: number = [
    row.platformFee,
    row.deliveryCost,
    row.dismantlingCost,
    row.repairCost,
    row.storageCost,
    row.legalCost,
    row.otherCosts,
  ].reduce<number>((sum, value) => sum + (value ?? 0), 0)
  row.totalExpenses = totalExpenses
  row.fullEntryCost = row.price === null ? null : row.price + totalExpenses
  row.potentialProfit = row.marketValue === null || row.fullEntryCost === null ? null : row.marketValue - row.fullEntryCost
  row.roiValue = row.potentialProfit === null || !row.fullEntryCost ? null : row.potentialProfit / row.fullEntryCost
  row.marketDiscount = row.marketValue && row.price !== null ? 1 - row.price / row.marketValue : null
  row.formulaMaxPurchasePrice = row.marketValue === null ? null : row.marketValue - totalExpenses - (row.targetProfit ?? 0)
  return row
}

function snapshotGridWorkState(row: GridLotRow): GridWorkSnapshot {
  return {
    marketValue: row.marketValue,
    platformFee: row.platformFee,
    deliveryCost: row.deliveryCost,
    dismantlingCost: row.dismantlingCost,
    repairCost: row.repairCost,
    storageCost: row.storageCost,
    legalCost: row.legalCost,
    otherCosts: row.otherCosts,
    targetProfit: row.targetProfit,
    excludeFromAnalysis: row.excludeFromAnalysis,
    exclusionReason: (row.exclusionReason ?? '').trim(),
  }
}

function serializeGridWorkState(row: GridLotRow) {
  return JSON.stringify(snapshotGridWorkState(row))
}

function rememberGridWorkSnapshot(row: GridLotRow) {
  savedGridWorkSnapshots.set(row.id, serializeGridWorkState(row))
}

async function loadAuctionPipelineHealth() {
  if (!isAuthenticated.value) return

  try {
    auctionPipelineHealth.value = await fetchJson<AuctionPipelineHealthResponse>('/api/v1/health/auction-pipeline')
  } catch (error) {
    console.warn('[auction-pipeline-health] failed to load', error)
    auctionPipelineHealth.value = null
  }
}

async function loadProcurementLots() {
  if (!isAuthenticated.value || procurementLoading.value) return
  procurementLoading.value = true
  procurementError.value = ''
  try {
    const response = await fetchJson<ProcurementLotListResponse>('/api/v1/procurements/lots?page=1&page_size=100')
    procurementLots.value = response.items
    procurementTotal.value = response.total
  } catch (error) {
    procurementError.value = error instanceof Error ? error.message : 'Не удалось загрузить закупки'
  } finally {
    procurementLoading.value = false
  }
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resolvedUrl = apiUrl(url)
  const startedAt = performance.now()
  let response: Response
  try {
    response = await fetch(resolvedUrl, {
      ...init,
      headers: new Headers({
        ...Object.fromEntries(createAuthHeaders(accessToken.value).entries()),
        ...Object.fromEntries(new Headers(init?.headers ?? {}).entries()),
      }),
    })
  } catch (error) {
    if (isAbortLikeError(error) || Boolean(init?.signal?.aborted)) {
      throw error
    }
    console.warn('[api-fetch] request failed before response', {
      url: resolvedUrl,
      method: init?.method ?? 'GET',
      elapsedMs: Math.round(performance.now() - startedAt),
      apiBaseUrl: API_BASE_URL || '(same-origin)',
      online: navigator.onLine,
      aborted: init?.signal?.aborted === true,
      errorName: error instanceof Error ? error.name : null,
      errorMessage: error instanceof Error ? error.message : String(error),
    })
    throw error
  }
  if (response.status === 401) {
    authStore.logout()
    throw new Error('Сессия истекла. Войдите снова.')
  }
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.clone().json()
    } catch {
      body = null
    }
    throw new ApiClientRequestError(`API вернул ${response.status}`, response.status, body)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function shouldPollAuctionGridChanges() {
  return isAuctionsModule.value && isAuthenticated.value && !document.hidden && latestAuctionGridDatasetVersion.value !== null
}

function startAuctionGridChangePolling(delay = AUCTION_GRID_CHANGES_POLL_INTERVAL_MS) {
  if (!shouldPollAuctionGridChanges() || auctionGridChangesPollTimer !== null) return

  auctionGridChangesPollTimer = window.setTimeout(() => {
    auctionGridChangesPollTimer = null
    void pollAuctionGridChanges()
  }, delay)
}

function stopAuctionGridChangePolling() {
  if (auctionGridChangesPollTimer !== null) {
    window.clearTimeout(auctionGridChangesPollTimer)
    auctionGridChangesPollTimer = null
  }
  if (auctionGridChangesRefreshTimer !== null) {
    window.clearTimeout(auctionGridChangesRefreshTimer)
    auctionGridChangesRefreshTimer = null
  }
}

function resetAuctionGridChangePolling() {
  stopAuctionGridChangePolling()
  latestAuctionGridDatasetVersion.value = null
  auctionGridChangesPolling = false
  auctionGridChangesRefreshInFlight = false
}

async function pollAuctionGridChanges() {
  if (!shouldPollAuctionGridChanges()) return
  if (auctionGridChangesPolling) {
    startAuctionGridChangePolling()
    return
  }

  const sinceVersion = latestAuctionGridDatasetVersion.value
  if (sinceVersion === null) return

  auctionGridChangesPolling = true
  try {
    const response = await auctionServerDataSource.getChangesSinceVersion({ sinceVersion }) as GridChangeFeedResponse
    const currentVersion = latestAuctionGridDatasetVersion.value ?? 0
    if (response.changes.length > 0 || response.datasetVersion > currentVersion) {
      if (!applyAuctionGridChangeFeedResponse(response)) {
        scheduleAuctionGridChangeRefresh()
      }
    }
  } catch (error) {
    if (isAuthenticated.value && !document.hidden) {
      console.warn('[auction-grid] change polling failed', error)
    }
  } finally {
    auctionGridChangesPolling = false
    startAuctionGridChangePolling()
  }
}

function scheduleAuctionGridChangeRefresh() {
  if (auctionGridChangesRefreshInFlight || auctionGridChangesRefreshTimer !== null) return

  auctionGridChangesRefreshTimer = window.setTimeout(() => {
    auctionGridChangesRefreshTimer = null
    void refreshAuctionGridAfterChange()
  }, AUCTION_GRID_CHANGES_REFRESH_DEBOUNCE_MS)
}

async function refreshAuctionGridAfterChange() {
  if (!isAuctionsModule.value || !isAuthenticated.value || document.hidden || !catalogRowModel.value) return
  auctionGridChangesRefreshInFlight = true
  try {
    await softRefreshCatalogRows({ range: resolveCatalogReloadRange() })
  } finally {
    auctionGridChangesRefreshInFlight = false
  }
}

function handleAuctionGridVisibilityChange() {
  if (document.hidden) {
    stopAuctionGridChangePolling()
    return
  }
  if (!isAuctionsModule.value) return
  startAuctionGridChangePolling(0)
}

async function loadPresets() {
  if (!isAuthenticated.value) return

  presetsLoading.value = true
  try {
    presets.value = sortPresets(await fetchJson<FilterPreset[]>('/api/v1/auctions/filter-presets'))
    if (selectedPresetId.value && !presets.value.some((preset) => preset.id === selectedPresetId.value)) {
      selectedPresetId.value = ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить подборки'
  } finally {
    presetsLoading.value = false
  }
}

async function loadTelegramPresets() {
  if (!isAuthenticated.value) return

  presetsLoading.value = true
  try {
    const [auctionPresets, procurementPresets] = await Promise.all([
      fetchJson<FilterPreset[]>('/api/v1/auctions/filter-presets'),
      fetchJson<FilterPreset[]>('/api/v1/procurements/filter-presets'),
    ])
    telegramPresets.value = sortPresets([...auctionPresets, ...procurementPresets])
    if (telegramPresetIdDraft.value && !telegramPresets.value.some((preset) => preset.id === telegramPresetIdDraft.value)) {
      telegramPresetIdDraft.value = ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить срезы Telegram'
  } finally {
    presetsLoading.value = false
  }
}

async function loadUserInterestProfiles() {
  if (!isAuthenticated.value) return

  interestProfilesLoading.value = true
  interestProfilesError.value = ''
  try {
    userInterestProfiles.value = sortUserInterestProfiles(await fetchUserInterestProfiles())
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось загрузить профили интересов'
  } finally {
    interestProfilesLoading.value = false
  }
}

function buildPresetPayload(name?: string) {
  return {
    name: (name ?? selectedPreset.value?.name ?? '').trim(),
    filters: sanitizeServerFilters(filters, DEFAULT_SERVER_FILTERS),
    grid_view: gridRef.value?.getSavedView() ?? null,
    is_favorite: selectedPreset.value?.is_favorite ?? false,
  }
}

function telegramPresetLabel(preset: FilterPreset) {
  return `${preset.scope === 'procurement' ? 'Тендер' : 'Торги'} · ${preset.name}`
}

type TelegramPresetFilterChip = {
  label: string
}

const TELEGRAM_PRESET_PERIOD_LABELS: Record<DatasetPeriod, string> = {
  week: 'Неделя',
  month: 'Месяц',
  year: 'Год',
}

const TELEGRAM_PRESET_COLUMN_LABELS: Record<string, string> = {
  __shortlist: 'Shortlist',
  analysisColor: 'Анализ',
  assignee: 'Ответственный',
  category: 'Категория',
  finalDecision: 'Решение',
  initialPrice: 'НМЦК',
  isNew: 'Новые',
  law: 'Закон',
  price: 'Цена',
  ratingScore: 'Рейтинг',
  score: 'Оценка',
  source: 'Площадка',
  status: 'Статус',
  workflowStatus: 'Этап',
}

const TELEGRAM_PRESET_OPERATOR_LABELS: Record<string, string> = {
  contains: 'содержит',
  startsWith: 'начинается с',
  endsWith: 'заканчивается на',
  equals: '=',
  notEquals: '!=',
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<=',
  isEmpty: 'пусто',
  notEmpty: 'заполнено',
  isNull: 'пусто',
  notNull: 'заполнено',
}

function formatTelegramPresetValue(value: unknown): string {
  if (value === true) return 'да'
  if (value === false) return 'нет'
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return Number.isFinite(value) ? value.toLocaleString('ru-RU') : '—'
  if (Array.isArray(value)) return value.map(formatTelegramPresetValue).join(', ')
  return String(value)
}

function addTelegramPresetChip(chips: TelegramPresetFilterChip[], seen: Set<string>, label: string) {
  const normalized = label.trim()
  if (!normalized || seen.has(normalized)) return
  seen.add(normalized)
  chips.push({ label: normalized })
}

function getTelegramPresetColumnLabel(key: string) {
  return TELEGRAM_PRESET_COLUMN_LABELS[key] ?? key
}

function formatTelegramPresetCondition(condition: Record<string, unknown>) {
  const key = String(condition.key ?? condition.field ?? '').trim()
  if (!key) return ''

  const operator = String(condition.operator ?? 'equals')
  const column = getTelegramPresetColumnLabel(key)
  if (operator === 'isEmpty' || operator === 'isNull' || operator === 'notEmpty' || operator === 'notNull') {
    return `${column}: ${TELEGRAM_PRESET_OPERATOR_LABELS[operator] ?? operator}`
  }

  const operatorLabel = TELEGRAM_PRESET_OPERATOR_LABELS[operator] ?? operator
  return `${column} ${operatorLabel} ${formatTelegramPresetValue(condition.value)}`
}

function collectTelegramPresetExpressionChips(
  expression: unknown,
  chips: TelegramPresetFilterChip[],
  seen: Set<string>,
) {
  if (!expression || typeof expression !== 'object') return
  const node = expression as Record<string, unknown>
  if (node.kind === 'condition') {
    addTelegramPresetChip(chips, seen, formatTelegramPresetCondition(node))
    return
  }
  if (node.kind === 'not') {
    const before = chips.length
    collectTelegramPresetExpressionChips(node.child, chips, seen)
    if (chips.length > before) {
      const lastChip = chips[chips.length - 1]
      if (lastChip) {
        chips[chips.length - 1] = { label: `Не ${lastChip.label}` }
      }
    }
    return
  }
  if (node.kind === 'group' && Array.isArray(node.children)) {
    node.children.forEach((child) => collectTelegramPresetExpressionChips(child, chips, seen))
  }
}

function collectTelegramPresetGridFilterChips(
  filterModel: unknown,
  chips: TelegramPresetFilterChip[],
  seen: Set<string>,
) {
  if (!filterModel || typeof filterModel !== 'object') return
  const snapshot = filterModel as Record<string, unknown>
  const quickFilter = snapshot.quickFilter as Record<string, unknown> | undefined
  if (typeof quickFilter?.query === 'string' && quickFilter.query.trim()) {
    addTelegramPresetChip(chips, seen, `Поиск: ${quickFilter.query.trim()}`)
  }

  const columnFilters = snapshot.columnFilters
  if (columnFilters && typeof columnFilters === 'object') {
    for (const [key, entry] of Object.entries(columnFilters as Record<string, unknown>)) {
      if (Array.isArray(entry) && entry.length) {
        addTelegramPresetChip(chips, seen, `${getTelegramPresetColumnLabel(key)}: ${entry.slice(0, 4).map(formatTelegramPresetValue).join(', ')}${entry.length > 4 ? ` +${entry.length - 4}` : ''}`)
        continue
      }
      if (!entry || typeof entry !== 'object') continue
      const filter = entry as Record<string, unknown>
      if (filter.kind === 'valueSet' && Array.isArray(filter.tokens) && filter.tokens.length) {
        addTelegramPresetChip(chips, seen, `${getTelegramPresetColumnLabel(key)}: ${filter.tokens.slice(0, 4).map(formatTelegramPresetValue).join(', ')}${filter.tokens.length > 4 ? ` +${filter.tokens.length - 4}` : ''}`)
      } else if (filter.kind === 'predicate') {
        addTelegramPresetChip(chips, seen, formatTelegramPresetCondition({ ...filter, key }))
      }
    }
  }

  collectTelegramPresetExpressionChips(snapshot.advancedExpression, chips, seen)
}

function getTelegramPresetGridFilterModel(preset: FilterPreset) {
  const savedView = preset.grid_view as Record<string, unknown> | null
  const state = savedView?.state as Record<string, unknown> | undefined
  const rows = state?.rows as Record<string, unknown> | undefined
  const snapshot = rows?.snapshot as Record<string, unknown> | undefined
  return snapshot?.filterModel ?? null
}

function telegramPresetFilterChips(preset: FilterPreset): TelegramPresetFilterChip[] {
  const chips: TelegramPresetFilterChip[] = []
  const seen = new Set<string>()
  const filters = (preset.filters ?? {}) as Record<string, unknown>

  if (preset.scope === 'procurement') {
    if (typeof filters.source === 'string' && filters.source && filters.source !== 'all') addTelegramPresetChip(chips, seen, `Площадка: ${filters.source}`)
    if (typeof filters.law === 'string' && filters.law) addTelegramPresetChip(chips, seen, `Закон: ${filters.law}`)
    if (typeof filters.status === 'string' && filters.status) addTelegramPresetChip(chips, seen, `Статус содержит ${filters.status}`)
    if (typeof filters.workflowStatus === 'string' && filters.workflowStatus) addTelegramPresetChip(chips, seen, `Этап: ${filters.workflowStatus}`)
    if (typeof filters.assignee === 'string' && filters.assignee) addTelegramPresetChip(chips, seen, `Ответственный: ${filters.assignee}`)
    if (typeof filters.category === 'string' && filters.category) addTelegramPresetChip(chips, seen, `Категория: ${filters.category}`)
    if (typeof filters.minPrice === 'string' && filters.minPrice.trim()) addTelegramPresetChip(chips, seen, `НМЦК от ${filters.minPrice.trim()}`)
    if (typeof filters.maxPrice === 'string' && filters.maxPrice.trim()) addTelegramPresetChip(chips, seen, `НМЦК до ${filters.maxPrice.trim()}`)
    if (typeof filters.minScore === 'number' && filters.minScore > 0) addTelegramPresetChip(chips, seen, `Оценка >= ${filters.minScore}`)
    if (filters.onlyNew === true) addTelegramPresetChip(chips, seen, 'Только новые')
  } else {
    const auctionFilters = sanitizeServerFilters(preset.filters, DEFAULT_SERVER_FILTERS)
    addTelegramPresetChip(chips, seen, `Период: ${TELEGRAM_PRESET_PERIOD_LABELS[auctionFilters.period]}`)
    if (auctionFilters.includeArchived) addTelegramPresetChip(chips, seen, 'С архивом')
    if (auctionFilters.source && auctionFilters.source !== 'all') addTelegramPresetChip(chips, seen, `Площадка: ${auctionFilters.source}`)
    if (auctionFilters.status) addTelegramPresetChip(chips, seen, `Статус: ${auctionFilters.status}`)
    if (auctionFilters.analysisColor) addTelegramPresetChip(chips, seen, `Анализ: ${auctionFilters.analysisColor}`)
    if (auctionFilters.minPrice.trim()) addTelegramPresetChip(chips, seen, `Цена от ${auctionFilters.minPrice.trim()}`)
    if (auctionFilters.maxPrice.trim()) addTelegramPresetChip(chips, seen, `Цена до ${auctionFilters.maxPrice.trim()}`)
    if (auctionFilters.onlyNew) addTelegramPresetChip(chips, seen, 'Только новые')
    if (auctionFilters.shortlist) addTelegramPresetChip(chips, seen, 'Shortlist')
    if (auctionFilters.minRating > 0) addTelegramPresetChip(chips, seen, `Рейтинг >= ${auctionFilters.minRating}`)
  }

  collectTelegramPresetGridFilterChips(getTelegramPresetGridFilterModel(preset), chips, seen)
  return chips.length ? chips : [{ label: 'Без дополнительных фильтров' }]
}

function telegramPresetMinRating(preset: FilterPreset) {
  const filters = preset.filters as Record<string, unknown>
  const auctionFilters = sanitizeServerFilters(preset.filters, DEFAULT_SERVER_FILTERS)
  const procurementMinScore =
    typeof filters.minScore === 'number' && Number.isFinite(filters.minScore)
      ? Math.max(0, Math.min(100, filters.minScore))
      : null
  return auctionFilters.minRating > 0 ? auctionFilters.minRating : procurementMinScore ?? 0
}

async function applyPresetById(presetId: string) {
  selectedPresetId.value = presetId
  const preset = presets.value.find((item) => item.id === presetId)
  if (!preset) return

  const nextFilters = sanitizeServerFilters(preset.filters, DEFAULT_SERVER_FILTERS)
  Object.assign(filters, nextFilters)
  await nextTick()
  writeGridSavedView(preset.grid_view)
  syncCatalogFilterModel()
}

function sortPresets(items: FilterPreset[]) {
  return [...items].sort((left, right) => {
    if (left.is_favorite !== right.is_favorite) {
      return left.is_favorite ? -1 : 1
    }
    return left.name.localeCompare(right.name, 'ru')
  })
}

function sortUserInterestProfiles(items: UserInterestProfile[]) {
  return [...items].sort((left, right) => {
    if (left.is_active !== right.is_active) {
      return left.is_active ? -1 : 1
    }
    return left.name.localeCompare(right.name, 'ru')
  })
}

function createAnalysisConfigDraftRule(category = '', keywords: string[] = []): AnalysisConfigDraftRule {
  analysisConfigRuleSeed += 1
  return {
    id: analysisConfigRuleSeed,
    category,
    keywordsText: keywords.join('\n'),
  }
}

function resetAnalysisConfigDraft() {
  analysisConfigDraft.categoryRules = []
  analysisConfigDraft.exclusionKeywordsText = ''
  analysisConfigDraft.highRiskKeywordsText = ''
  analysisConfigDraft.mediumRiskKeywordsText = ''
  analysisConfigDraft.mediumRiskCategoriesText = ''
}

function applyAnalysisConfigDraft(config: AnalysisConfigResponse) {
  analysisConfigDraft.categoryRules = config.category_rules.map((rule) =>
    createAnalysisConfigDraftRule(rule.category, rule.keywords),
  )
  analysisConfigDraft.exclusionKeywordsText = config.exclusion_keywords.join('\n')
  analysisConfigDraft.highRiskKeywordsText = config.legal_risk_rules.high_keywords.join('\n')
  analysisConfigDraft.mediumRiskKeywordsText = config.legal_risk_rules.medium_keywords.join('\n')
  analysisConfigDraft.mediumRiskCategoriesText = config.legal_risk_rules.medium_categories.join('\n')
}

function addAnalysisConfigCategoryRule() {
  analysisConfigDraft.categoryRules = [...analysisConfigDraft.categoryRules, createAnalysisConfigDraftRule()]
}

function removeAnalysisConfigCategoryRule(ruleId: number) {
  analysisConfigDraft.categoryRules = analysisConfigDraft.categoryRules.filter((rule) => rule.id !== ruleId)
}

function splitAnalysisConfigLines(value: string) {
  const seen = new Set<string>()
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter((item) => {
      const normalized = item.toLowerCase()
      if (!normalized || seen.has(normalized)) return false
      seen.add(normalized)
      return true
    })
}

function buildAnalysisConfigPayload() {
  return {
    category_rules: analysisConfigDraft.categoryRules
      .map((rule) => ({
        category: rule.category.trim(),
        keywords: splitAnalysisConfigLines(rule.keywordsText),
      }))
      .filter((rule) => rule.category),
    exclusion_keywords: splitAnalysisConfigLines(analysisConfigDraft.exclusionKeywordsText),
    legal_risk_rules: {
      high_keywords: splitAnalysisConfigLines(analysisConfigDraft.highRiskKeywordsText),
      medium_keywords: splitAnalysisConfigLines(analysisConfigDraft.mediumRiskKeywordsText),
      medium_categories: splitAnalysisConfigLines(analysisConfigDraft.mediumRiskCategoriesText),
    },
    owner_profile: analysisConfig.value?.owner_profile,
    dimension_weights: analysisConfig.value?.dimension_weights,
  }
}

async function loadAnalysisConfig() {
  if (!isAuthenticated.value) return

  analysisConfigLoading.value = true
  analysisConfigError.value = ''
  try {
    analysisConfig.value = await fetchJson<AnalysisConfigResponse>('/api/v1/auctions/analysis-config')
    if (analysisConfig.value) {
      applyAnalysisConfigDraft(analysisConfig.value)
    }
  } catch (error) {
    analysisConfigError.value = error instanceof Error ? error.message : 'Не удалось загрузить конфиг анализа'
  } finally {
    analysisConfigLoading.value = false
  }
}

function openAnalysisConfigDialog(event?: Event) {
  void event
  void router.push({ name: 'analysis-config' })
}

function openInterestProfilesDialog(event?: Event) {
  void event
  void router.push({ name: 'interest-profiles' })
}

function interestProfileNote(profile: UserInterestProfile) {
  const parts = []
  parts.push(profile.source_filter_preset_id ? 'Срез Telegram' : 'Профиль интересов')
  parts.push(`рейтинг ${profile.min_rating}+`)
  return parts.join(' · ')
}

async function createInterestProfileFromSelectedPreset() {
  const preset = telegramPresets.value.find((item) => item.id === telegramPresetIdDraft.value)
  if (!preset) {
    interestProfilesError.value = 'Выберите сохраненный срез для Telegram'
    return
  }

  interestProfilesSaving.value = true
  interestProfilesError.value = ''
  try {
    const profile = await createUserInterestProfileFromPreset({
      preset_id: preset.id,
      name: preset.name,
      min_rating: telegramPresetMinRating(preset) > 0 ? telegramPresetMinRating(preset) : null,
      telegram_enabled: true,
      is_active: true,
    })
    userInterestProfiles.value = sortUserInterestProfiles([...userInterestProfiles.value, profile])
    telegramPresetIdDraft.value = preset.id
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось подключить срез к Telegram'
  } finally {
    interestProfilesSaving.value = false
  }
}

async function connectTelegramBot() {
  telegramConnectLoading.value = true
  interestProfilesError.value = ''
  try {
    const response = await createTelegramConnectToken()
    telegramConnectUrl.value = response.connect_url
    telegramConnectExpiresAt.value = response.expires_at
    window.open(response.connect_url, '_blank', 'noopener,noreferrer')
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось создать ссылку подключения Telegram'
  } finally {
    telegramConnectLoading.value = false
  }
}

async function toggleInterestProfileActive(profile: UserInterestProfile) {
  await patchInterestProfile(profile, { is_active: !profile.is_active })
}

async function toggleInterestProfileTelegram(profile: UserInterestProfile) {
  await patchInterestProfile(profile, { telegram_enabled: !profile.telegram_enabled })
}

async function patchInterestProfile(profile: UserInterestProfile, payload: Parameters<typeof updateUserInterestProfile>[1]) {
  interestProfilesSaving.value = true
  interestProfilesError.value = ''
  try {
    const updated = await updateUserInterestProfile(profile.id, payload)
    userInterestProfiles.value = sortUserInterestProfiles(
      userInterestProfiles.value.map((item) => (item.id === updated.id ? updated : item)),
    )
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось обновить профиль интересов'
  } finally {
    interestProfilesSaving.value = false
  }
}

async function refreshInterestProfileFromPreset(profile: UserInterestProfile) {
  if (!profile.source_filter_preset_id) return

  interestProfilesSaving.value = true
  interestProfilesError.value = ''
  try {
    const updated = await refreshUserInterestProfileFromPreset(profile.id)
    userInterestProfiles.value = sortUserInterestProfiles(
      userInterestProfiles.value.map((item) => (item.id === updated.id ? updated : item)),
    )
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось обновить профиль из среза'
  } finally {
    interestProfilesSaving.value = false
  }
}

async function removeInterestProfile(profile: UserInterestProfile) {
  interestProfilesSaving.value = true
  interestProfilesError.value = ''
  try {
    await deleteUserInterestProfile(profile.id)
    userInterestProfiles.value = userInterestProfiles.value.filter((item) => item.id !== profile.id)
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось удалить профиль интересов'
  } finally {
    interestProfilesSaving.value = false
  }
}

async function submitAnalysisConfigDialog() {
  analysisConfigSaving.value = true
  analysisConfigError.value = ''
  try {
    analysisConfig.value = await fetchJson<AnalysisConfigResponse>('/api/v1/auctions/analysis-config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildAnalysisConfigPayload()),
    })
    if (analysisConfig.value) {
      applyAnalysisConfigDraft(analysisConfig.value)
    }
    await router.push('/auctions')
  } catch (error) {
    analysisConfigError.value = error instanceof Error ? error.message : 'Не удалось сохранить конфиг анализа'
  } finally {
    analysisConfigSaving.value = false
  }
}

function openCreatePresetDialog(event?: Event) {
  presetDialogTriggerRef.value = event?.currentTarget as HTMLElement | null
  presetDialogMode.value = 'create'
  presetNameDraft.value = ''
  presetDialog.open('trigger')
}

function openUpdatePresetDialog(event?: Event) {
  if (!selectedPreset.value) return
  presetDialogTriggerRef.value = event?.currentTarget as HTMLElement | null
  presetDialogMode.value = 'update'
  presetNameDraft.value = selectedPreset.value.name
  presetDialog.open('trigger')
}

function openDeletePresetDialog(event?: Event) {
  if (!selectedPreset.value) return
  presetDialogTriggerRef.value = event?.currentTarget as HTMLElement | null
  presetDialogMode.value = 'delete'
  presetNameDraft.value = selectedPreset.value.name
  presetDialog.open('trigger')
}

async function submitPresetDialog() {
  if (presetDialogMode.value === 'delete') {
    await confirmDeletePreset()
    return
  }

  const nextName = presetNameDraft.value.trim()
  if (!nextName) {
    errorMessage.value = 'Название среза не должно быть пустым'
    return
  }

  if (presetDialogMode.value === 'update' && selectedPreset.value) {
    try {
      const preset = await fetchJson<FilterPreset>(`/api/v1/auctions/filter-presets/${selectedPreset.value.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPresetPayload(nextName)),
      })
    presets.value = sortPresets(presets.value.map((item) => (item.id === preset.id ? preset : item)))
    selectedPresetId.value = preset.id
    await syncInterestProfilesForPreset(preset.id)
    await presetDialog.close('programmatic')
  } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Не удалось обновить срез'
    }
    return
  }

  try {
    const preset = await fetchJson<FilterPreset>('/api/v1/auctions/filter-presets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPresetPayload(nextName)),
    })
    presets.value = sortPresets([...presets.value, preset])
    selectedPresetId.value = preset.id
    await presetDialog.close('programmatic')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось сохранить срез'
  }
}

async function syncInterestProfilesForPreset(presetId: string) {
  const linkedProfiles = userInterestProfiles.value.filter((profile) => profile.source_filter_preset_id === presetId)
  if (!linkedProfiles.length) return

  interestProfilesSaving.value = true
  interestProfilesError.value = ''
  try {
    const updatedProfiles = await Promise.all(
      linkedProfiles.map((profile) => refreshUserInterestProfileFromPreset(profile.id)),
    )
    const updatedById = new Map(updatedProfiles.map((profile) => [profile.id, profile]))
    userInterestProfiles.value = sortUserInterestProfiles(
      userInterestProfiles.value.map((profile) => updatedById.get(profile.id) ?? profile),
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Не удалось синхронизировать Telegram-профили со срезом'
    interestProfilesError.value = message
    errorMessage.value = message
  } finally {
    interestProfilesSaving.value = false
  }
}

async function confirmDeletePreset() {
  if (!selectedPreset.value) return

  try {
    await fetchJson(`/api/v1/auctions/filter-presets/${selectedPreset.value.id}`, {
      method: 'DELETE',
    })
    presets.value = presets.value.filter((preset) => preset.id !== selectedPreset.value?.id)
    selectedPresetId.value = ''
    await presetDialog.close('programmatic')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось удалить подборку'
  }
}

const interestProfilesRouteBindings = {
  presets,
  telegramPresets,
  presetsLoading,
  userInterestProfiles,
  interestProfilesLoading,
  interestProfilesSaving,
  interestProfilesError,
  telegramConnectLoading,
  telegramConnectUrl,
  telegramConnectExpiresAt,
  telegramPresetIdDraft,
  formatDateTime,
  loadPresets,
  loadTelegramPresets,
  loadUserInterestProfiles,
  createInterestProfileFromSelectedPreset,
  telegramPresetLabel,
  telegramPresetFilterChips,
  connectTelegramBot,
  toggleInterestProfileActive,
  toggleInterestProfileTelegram,
  refreshInterestProfileFromPreset,
  removeInterestProfile,
  interestProfileNote,
}

const analysisConfigRouteBindings = {
  analysisConfigLoading,
  analysisConfigSaving,
  analysisConfigError,
  analysisConfigUpdatedAt,
  analysisConfigDraft,
  setAnalysisConfigInitialRef,
  loadAnalysisConfig,
  submitAnalysisConfigDialog,
  addAnalysisConfigCategoryRule,
  removeAnalysisConfigCategoryRule,
}

function resetWorkDraft() {
  Object.assign(workDraft, emptyWorkDraft())
}

function hydrateWorkDraft(workItem: LotWorkItem | null) {
  resetWorkDraft()
  if (!workItem) return

  workDraft.decision_status = workItem.decision_status ?? ''
  workDraft.assignee = workItem.assignee ?? ''
  workDraft.comment = workItem.comment ?? ''
  workDraft.inspection_at = workItem.inspection_at ?? ''
  workDraft.inspection_result = workItem.inspection_result ?? ''
  workDraft.final_decision = workItem.final_decision ?? ''
  workDraft.investor = workItem.investor ?? ''
  workDraft.deposit_status = workItem.deposit_status ?? ''
  workDraft.application_status = workItem.application_status ?? ''
  workDraft.exclude_from_analysis = workItem.exclude_from_analysis === true
  workDraft.exclusion_reason = workItem.exclusion_reason ?? ''
  workDraft.category_override = workItem.category_override ?? ''
  workDraft.market_value = normalizeDraftNumber(workItem.market_value)
  workDraft.platform_fee = normalizeDraftNumber(workItem.platform_fee)
  workDraft.delivery_cost = normalizeDraftNumber(workItem.delivery_cost)
  workDraft.dismantling_cost = normalizeDraftNumber(workItem.dismantling_cost)
  workDraft.repair_cost = normalizeDraftNumber(workItem.repair_cost)
  workDraft.storage_cost = normalizeDraftNumber(workItem.storage_cost)
  workDraft.legal_cost = normalizeDraftNumber(workItem.legal_cost)
  workDraft.other_costs = normalizeDraftNumber(workItem.other_costs)
  workDraft.target_profit = normalizeDraftNumber(workItem.target_profit)
}

function hydrateGridEditableWorkDraft(row: GridLotRow) {
  workDraft.exclude_from_analysis = row.excludeFromAnalysis
  workDraft.exclusion_reason = row.exclusionReason
  workDraft.market_value = normalizeDraftNumber(row.marketValue)
  workDraft.platform_fee = normalizeDraftNumber(row.platformFee)
  workDraft.delivery_cost = normalizeDraftNumber(row.deliveryCost)
  workDraft.dismantling_cost = normalizeDraftNumber(row.dismantlingCost)
  workDraft.repair_cost = normalizeDraftNumber(row.repairCost)
  workDraft.storage_cost = normalizeDraftNumber(row.storageCost)
  workDraft.legal_cost = normalizeDraftNumber(row.legalCost)
  workDraft.other_costs = normalizeDraftNumber(row.otherCosts)
  workDraft.target_profit = normalizeDraftNumber(row.targetProfit)
}

function syncSelectedWorkDraftFromGridRows(rows: ApiLotRow[]) {
  const selectedWorkspaceRowId = selectedWorkspace.value?.row.row_id
  if (!selectedWorkspaceRowId || !rows.some((row) => row.row_id === selectedWorkspaceRowId)) return

  const selectedRow = gridRowsById.value.get(selectedWorkspaceRowId) ?? selectedLot.value
  if (selectedRow) {
    hydrateGridEditableWorkDraft(selectedRow)
  }
}

function normalizeDraftNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return ''
  const parsed = parseNumber(value)
  return parsed === null ? '' : String(parsed)
}

function getActiveGridCellFromSnapshot(selectionSnapshot: GridSelectionSnapshot) {
  const activeRange = selectionSnapshot?.ranges[selectionSnapshot.activeRangeIndex] ?? selectionSnapshot?.ranges[0]
  return selectionSnapshot?.activeCell ?? activeRange?.focus ?? activeRange?.anchor ?? null
}

function updateMobileViewportState() {
  isMobileViewport.value = window.matchMedia('(max-width: 760px)').matches
}

function updateAppViewportHeight() {
  const viewportHeight = window.visualViewport?.height ?? window.innerHeight
  document.documentElement.style.setProperty('--app-viewport-height', `${Math.round(viewportHeight)}px`)
}

async function restoreDetailGridFocus() {
  const anchor = detailGridFocusAnchor
  detailGridFocusAnchor = null
  if (!anchor) return

  await nextTick()
  try {
    await gridRef.value?.restoreFocusAnchor(anchor, {
      preventScroll: true,
      scrollIntoView: false,
      retries: 3,
    })
  } catch {
    // The row may have left the current filtered/sorted viewport before focus is restored.
  }
}

const mobileInlineEditTarget = computed<MobileInlineEditTarget | null>(() => {
  if (!isMobileViewport.value) return null
  const api = gridRef.value?.getApi()
  const runtime = gridRef.value?.getRuntime()
  if (!api?.selection.hasSupport() || !runtime) return null

  const selectionSnapshot = api.selection.getSnapshot()
  const activeCell = getActiveGridCellFromSnapshot(selectionSnapshot)
  if (!activeCell) return null

  const visibleColumn = runtime.columnSnapshot.value.visibleColumns[activeCell.colIndex]
  if (!visibleColumn) return null

  const bodyRow = runtime.getBodyRowAtIndex(activeCell.rowIndex)
  if (!bodyRow || !isGridCellEditable({ column: { key: visibleColumn.key } })) return null

  return {
    rowId: bodyRow.rowId,
    rowIndex: activeCell.rowIndex,
    columnIndex: activeCell.colIndex,
    columnKey: visibleColumn.key,
  }
})

function openMobileInlineEdit() {
  const target = mobileInlineEditTarget.value
  if (!target) return

  const gridRoot = gridSurfaceRef.value?.querySelector<HTMLElement>('.affino-datagrid-app-root') ?? null
  if (!gridRoot) return

  const escapeSelectorValue = (value: string) =>
    typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(value)
      : value.replace(/["\\]/g, '\\$&')
  const rowSelector = `[data-row-id="${escapeSelectorValue(String(target.rowId))}"]`
  const selectors = [
    `.grid-cell${rowSelector}[data-column-key="${escapeSelectorValue(target.columnKey)}"]`,
    `.grid-cell${rowSelector}[data-column-index="${target.columnIndex}"]`,
    `.grid-cell${rowSelector}`,
    '.grid-cell[tabindex="0"]',
  ]

  let cellElement: HTMLElement | null = null
  for (const selector of selectors) {
    const found = gridRoot.querySelector<HTMLElement>(selector)
    if (found) {
      cellElement = found
      break
    }
  }

  if (!cellElement) return

  cellElement.dispatchEvent(
    new MouseEvent('dblclick', {
      bubbles: true,
      cancelable: true,
      view: window,
      detail: 2,
    }),
  )
}

function buildLotWorkspacePath(row: GridLotRow, suffix = '', options: { includeDetail?: boolean } = {}) {
  const params = new URLSearchParams()
  if (row.auctionId) params.set('auction_id', row.auctionId)
  if (typeof options.includeDetail === 'boolean') params.set('include_detail', String(options.includeDetail))
  const query = params.toString()
  return `/api/v1/auctions/${row.source}/lots/${encodeURIComponent(row.lotId)}/workspace${suffix}${query ? `?${query}` : ''}`
}

function applyDetailWorkspace(workspace: LotWorkspaceResponse, options: { updateGrid?: boolean } = {}) {
  selectedWorkspace.value = workspace
  selectedLotDetails.value = workspace.lot_detail
  selectedAuctionDetails.value = workspace.auction_detail
  if (options.updateGrid !== false) {
    applyWorkspaceRow(workspace.row, { refreshSummary: false })
  }
  hydrateWorkDraft(workspace.work_item)
}

function resetDecisionReportState() {
  selectedDecisionReport.value = null
  decisionReportLoading.value = false
  decisionReportStatus.value = 'idle'
  decisionReportError.value = ''
}

async function loadSelectedDecisionReport(recordId: number, requestId: number) {
  const reportRequestId = ++decisionReportRequestId
  selectedDecisionReport.value = null
  decisionReportLoading.value = true
  decisionReportStatus.value = 'idle'
  decisionReportError.value = ''
  try {
    const report = await fetchLotDecisionReport(recordId)
    if (requestId !== detailRequestId || reportRequestId !== decisionReportRequestId) return
    selectedDecisionReport.value = report
  } catch (error) {
    if (requestId !== detailRequestId || reportRequestId !== decisionReportRequestId) return
    if (error instanceof ApiClientRequestError && error.status === 404) {
      decisionReportStatus.value = 'empty'
      return
    }
    decisionReportStatus.value = 'error'
    decisionReportError.value = error instanceof Error ? error.message : 'Не удалось загрузить отчет решения'
  } finally {
    if (requestId === detailRequestId && reportRequestId === decisionReportRequestId) {
      decisionReportLoading.value = false
    }
  }
}

function clearDetailLiveRefreshTimeout() {
  if (detailLiveRefreshTimeout !== null) {
    window.clearTimeout(detailLiveRefreshTimeout)
    detailLiveRefreshTimeout = null
  }
}

function finishDetailLiveRefresh(message: string) {
  clearDetailLiveRefreshTimeout()
  detailLiveRefreshing.value = false
  detailStatus.value = message
}

function isSelectedLotEvent(payload: Record<string, unknown>) {
  const row = selectedLot.value
  if (!row) return false
  if (payload.source && payload.source !== row.source) return false
  if (payload.lot_id && payload.lot_id !== row.lotId) return false
  if (payload.auction_id && payload.auction_id !== row.auctionId) return false
  return true
}

async function refreshLiveLotDetails(row: GridLotRow, requestId: number) {
  if (!row.lotId) return

  clearDetailLiveRefreshTimeout()
  detailLiveRefreshing.value = true
  detailStatus.value = 'Ставлю live refresh в очередь'
  try {
    const refresh = await fetchJson<LotWorkspaceRefreshResponse>(buildLotWorkspacePath(row, '/refresh'), {
      method: 'POST',
    })
    if (requestId !== detailRequestId) return
    if (refresh.status === 'queued') {
      finishDetailLiveRefresh('Live refresh поставлен в очередь')
      return
    }
    if (refresh.status === 'already_pending') {
      finishDetailLiveRefresh('Live refresh уже ожидает обработки')
      return
    }
    const allowedAt = refresh.next_allowed_at ? formatDateTime(refresh.next_allowed_at) : 'позже'
    finishDetailLiveRefresh(`Live refresh временно недоступен до ${allowedAt}`)
  } catch (error) {
    if (requestId !== detailRequestId) return
    finishDetailLiveRefresh(error instanceof Error ? `Live refresh не запущен: ${error.message}` : 'Live refresh не запущен')
  } finally {
    if (requestId === detailRequestId) {
      detailLiveRefreshing.value = false
    }
  }
}

async function reanalyzeLocalLotDetails(row: GridLotRow, requestId: number) {
  if (!row.lotId) return

  detailReanalyzing.value = true
  detailStatus.value = 'Пересчитываю карточку локально'
  try {
    const workspace = await fetchJson<LotWorkspaceResponse>(buildLotWorkspacePath(row, '/reanalyze', { includeDetail: true }), {
      method: 'POST',
    })
    if (requestId !== detailRequestId) return
    applyDetailWorkspace(workspace)
    detailStatus.value = 'Локальный пересчет завершен'
  } catch (error) {
    if (requestId !== detailRequestId) return
    detailStatus.value = error instanceof Error ? `Локальный пересчет не удался: ${error.message}` : 'Локальный пересчет не удался'
  } finally {
    if (requestId === detailRequestId) {
      detailReanalyzing.value = false
    }
  }
}

async function reloadSelectedWorkspaceAfterLiveRefresh(requestId: number) {
  const row = selectedLot.value
  if (!row?.lotId) return
  detailStatus.value = 'Загружаю обновленные live-данные'
  try {
    const workspace = await fetchJson<LotWorkspaceResponse>(buildLotWorkspacePath(row, '', { includeDetail: true }))
    if (requestId !== detailRequestId) return
    applyDetailWorkspace(workspace)
    finishDetailLiveRefresh('Live-данные обновлены')
  } catch (error) {
    if (requestId !== detailRequestId) return
    finishDetailLiveRefresh(
      error instanceof Error ? `Live-данные обновлены, но карточку не удалось перечитать: ${error.message}` : 'Live-данные обновлены, но карточку не удалось перечитать',
    )
  }
}

function refreshSelectedLotLiveDetails() {
  const row = selectedLot.value
  if (!row?.lotId || detailLiveRefreshing.value || detailReanalyzing.value) return
  void refreshLiveLotDetails(row, detailRequestId)
}

function reanalyzeSelectedLotDetails() {
  const row = selectedLot.value
  if (!row?.lotId || detailLiveRefreshing.value || detailReanalyzing.value) return
  void reanalyzeLocalLotDetails(row, detailRequestId)
}

async function openLotDetails(row: GridLotRow) {
  const trace = startUiPerfTrace('openLotDetails', { rowId: row.id, lotId: row.lotId })
  const requestId = ++detailRequestId
  detailGridFocusAnchor = gridRef.value?.captureFocusAnchor({
    includeSelection: true,
    includeRowSelection: true,
  }) ?? null
  selectedLot.value = row
  selectedLotDetails.value = null
  selectedAuctionDetails.value = null
  selectedWorkspace.value = null
  resetDecisionReportState()
  resetWorkDraft()
  errorMessage.value = ''
  detailLiveRefreshing.value = false
  detailReanalyzing.value = false
  detailStatus.value = 'Открыта карточка из каталога'

  if (!row.lotId) return

  detailAbortController?.abort()
  detailAbortController = new AbortController()
  detailLoading.value = true
  detailStatus.value = 'Загружаю рабочую карточку из локальной БД'
  const timeoutId = window.setTimeout(() => {
    if (requestId !== detailRequestId) return
    detailStatus.value = 'Локальная карточка не ответила вовремя, каталог остается доступным'
    detailAbortController?.abort()
  }, DETAIL_FETCH_TIMEOUT_MS)
  try {
    const workspace = await fetchJson<LotWorkspaceResponse>(buildLotWorkspacePath(row, '', { includeDetail: false }), {
      signal: detailAbortController.signal,
    })

    if (requestId !== detailRequestId) return

    detailLoading.value = false
    detailStatus.value = workspace.detail_cached_at
      ? 'Показана карточка из локальной БД'
      : 'Показана карточка из каталога'
    await nextTick()
    applyDetailWorkspace(workspace, { updateGrid: false })
    void loadSelectedDecisionReport(workspace.record_id, requestId)
    trace.end({ stage: 'rendered' })
  } catch (error) {
    if (isAbortLikeError(error)) {
      trace.end({ stage: 'aborted' })
      return
    }
    detailStatus.value = 'Рабочая карточка не загрузилась, карточка из каталога доступна'
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить рабочую карточку лота'
    trace.end({ stage: 'error', message: error instanceof Error ? error.message : String(error) })
  } finally {
    window.clearTimeout(timeoutId)
    if (requestId === detailRequestId) {
      detailLoading.value = false
      detailAbortController = null
    }
  }
}

function closeLotDetails() {
  const trace = startUiPerfTrace('closeLotDetails', { rowId: selectedLot.value?.id ?? null })
  detailRequestId += 1
  decisionReportRequestId += 1
  detailAbortController?.abort()
  detailAbortController = null
  clearDetailLiveRefreshTimeout()
  selectedLot.value = null
  selectedLotDetails.value = null
  selectedAuctionDetails.value = null
  selectedWorkspace.value = null
  resetDecisionReportState()
  resetWorkDraft()
  detailLoading.value = false
  detailLiveRefreshing.value = false
  detailReanalyzing.value = false
  detailStatus.value = ''
  void restoreDetailGridFocus()
  trace.end({ stage: 'closed' })
}

function resetCatalogState() {
  resetAuctionGridChangePolling()
  catalogSoftRefreshAbortController?.abort()
  catalogSoftRefreshAbortController = null
  catalogRowModel.value?.dispose()
  catalogRowModel.value = null
  clearCatalogViewportDim()
  allRows.value = []
  loadedGridRowIds.clear()
  gridRowsById.value.clear()
  catalogTotal.value = 0
  catalogSummary.value = {
    total: 0,
    newCount: 0,
    activeCount: 0,
    openApplicationsCount: 0,
    highRatingCount: 0,
  }
  presets.value = []
  userInterestProfiles.value = []
  interestProfilesError.value = ''
  selectedPresetId.value = ''
  selectedLot.value = null
  selectedLotDetails.value = null
  selectedAuctionDetails.value = null
  selectedWorkspace.value = null
  resetDecisionReportState()
  detailStatus.value = ''
  updateAuctionHistoryState({
    canUndo: false,
    canRedo: false,
    latestUndoOperationId: null,
    latestRedoOperationId: null,
    datasetVersion: null,
  })
  errorMessage.value = ''
  lastLoadedAt.value = null
  detailLoading.value = false
  clearDetailLiveRefreshTimeout()
  detailLiveRefreshing.value = false
  detailReanalyzing.value = false
  backgroundStatus.value = 'Ожидаем фоновое обновление'
  resetWorkDraft()
  catalogGridHasLoadedOnce.value = false
}

function updateLoadingSkeletonRows() {
  const surfaceHeight = gridSurfaceRef.value?.clientHeight ?? 0
  const bodyHeight = surfaceHeight - LOADING_SKELETON_TOOLBAR_HEIGHT - LOADING_SKELETON_HEADER_HEIGHT
  const rowCount = Math.ceil(Math.max(0, bodyHeight) / LOADING_SKELETON_ROW_HEIGHT) + 2
  loadingSkeletonVisibleRows.value = Math.max(LOADING_SKELETON_MIN_ROWS, rowCount)
}

function startGridSurfaceResizeObserver() {
  if (gridSurfaceResizeObserver || !gridSurfaceRef.value || typeof ResizeObserver === 'undefined') {
    updateLoadingSkeletonRows()
    return
  }

  gridSurfaceResizeObserver = new ResizeObserver(() => updateLoadingSkeletonRows())
  gridSurfaceResizeObserver.observe(gridSurfaceRef.value)
  updateLoadingSkeletonRows()
}

function stopGridSurfaceResizeObserver() {
  gridSurfaceResizeObserver?.disconnect()
  gridSurfaceResizeObserver = null
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
  saveDetailPaneWidth(DETAIL_PANE_WIDTH_STORAGE_KEY, detailPaneWidth.value)
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (presetDialog.snapshot.value.isOpen) {
    if (['Escape', 'Esc'].includes(event.key)) {
      event.preventDefault()
      event.stopPropagation()
      void presetDialog.close('escape-key')
    }
    return
  }
  if (!['Escape', 'Esc'].includes(event.key) || !selectedLot.value) return
  event.preventDefault()
  event.stopPropagation()
  closeLotDetails()
}

function subscribeToAuctionEvents() {
  const events = new EventSource(apiUrl('/api/v1/auctions/events'))

  events.addEventListener('sync.started', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    backgroundStatus.value = `Фоновое обновление: ${data.payload.source}`
  })

  events.addEventListener('sync.completed', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const payload = data.payload
    backgroundStatus.value = `Фоново обновлено: ${payload.source}, новых ${payload.created}, изменено ${payload.updated}`
    scheduleLotsReload()
  })

  events.addEventListener('sync.progress', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const payload = data.payload
    backgroundStatus.value = `Фоновое обновление: ${payload.source} · ${payload.processed}/${payload.fetched} · новых ${payload.created}`
    scheduleProgressLotsReload()
  })

  events.addEventListener('analysis.started', () => {
    backgroundStatus.value = 'Фоновая аналитика пересчитывает сигналы и рейтинг'
  })

  events.addEventListener('analysis.completed', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const payload = data.payload
    backgroundStatus.value = `Аналитика обновлена: обработано ${payload.processed}, изменено ${payload.updated}`
  })

  events.addEventListener('analysis.failed', () => {
    backgroundStatus.value = 'Ошибка фоновой аналитики'
  })

  events.addEventListener('lot.row_updated', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const row = data.payload?.row as ApiLotRow | undefined
    if (row) {
      queueWorkspaceRows([row])
    }
  })

  events.addEventListener('lot.rows_updated', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const rows = data.payload?.rows as ApiLotRow[] | undefined
    if (rows?.length) {
      queueWorkspaceRows(rows)
    }
  })

  events.addEventListener('lot.detail_refresh_completed', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const payload = data.payload ?? {}
    backgroundStatus.value = `Live refresh обновлен: ${payload.source ?? 'source'}`
    if (isSelectedLotEvent(payload)) {
      if (selectedWorkspace.value) {
        selectedWorkspace.value = {
          ...selectedWorkspace.value,
          detail_cached_at: payload.detail_cached_at ?? selectedWorkspace.value.detail_cached_at,
        }
      }
      void reloadSelectedWorkspaceAfterLiveRefresh(detailRequestId)
    }
  })

  events.addEventListener('lot.detail_refresh_failed', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    const payload = data.payload ?? {}
    backgroundStatus.value = `Live refresh не удался: ${payload.source ?? 'source'}`
    if (isSelectedLotEvent(payload)) {
      finishDetailLiveRefresh(typeof payload.message === 'string' ? payload.message : 'Live-данные не удалось прочитать')
    }
  })

  events.addEventListener('sync.failed', (event) => {
    const data = JSON.parse((event as MessageEvent).data)
    backgroundStatus.value = `Ошибка фонового обновления: ${data.payload.source}`
  })

  events.onerror = () => {
    backgroundStatus.value = 'Ждем связь с фоновым обновлением'
  }

  return events
}

let auctionEvents: EventSource | null = null

function startAuctionEvents() {
  if (auctionEvents || !isAuctionsModule.value || !isAuthenticated.value) return
  auctionEvents = subscribeToAuctionEvents()
}

function stopAuctionEvents() {
  auctionEvents?.close()
  auctionEvents = null
}

watch(filters, () => {
  if (!isAuctionsModule.value) return
  persistStoredServerFilters(SERVER_FILTERS_STORAGE_KEY, filters, DEFAULT_SERVER_FILTERS)
  scheduleCatalogFilterSync()
}, { deep: true })

watch(isAuthenticated, (authenticated) => {
  if (authenticated) {
    if (isAuctionsModule.value) {
      void loadLots()
      startAuctionEvents()
      startAuctionGridChangePolling(0)
      void nextTick(() => startGridSurfaceResizeObserver())
    }
    void loadPresets()
    void loadUserInterestProfiles()
    return
  }

  stopGridSurfaceResizeObserver()
  stopAuctionEvents()
  resetCatalogState()
})

onMounted(() => {
  subscribeAuctionHistoryStatus()
  if (isAuthenticated.value) {
    if (isAuctionsModule.value) {
      void loadLots()
      startAuctionEvents()
      startAuctionGridChangePolling(0)
      void nextTick(() => startGridSurfaceResizeObserver())
    }
    void loadPresets()
    void loadUserInterestProfiles()
  }
  updateAppViewportHeight()
  updateMobileViewportState()
  window.addEventListener('resize', updateLoadingSkeletonRows)
  window.addEventListener('resize', updateAppViewportHeight)
  window.visualViewport?.addEventListener('resize', updateAppViewportHeight)
  window.addEventListener('resize', updateMobileViewportState)
  document.addEventListener('keydown', handleGlobalKeydown, true)
  document.addEventListener('visibilitychange', handleAuctionGridVisibilityChange)
})
onUnmounted(() => {
  auctionHistoryStatusUnsubscribe?.()
  auctionHistoryStatusUnsubscribe = null
  detailAbortController?.abort()
  detailAbortController = null
  catalogSoftRefreshAbortController?.abort()
  catalogSoftRefreshAbortController = null
  clearDetailLiveRefreshTimeout()
  detailReanalyzing.value = false
  catalogRowModel.value?.dispose()
  catalogRowModel.value = null
  clearCatalogViewportDim()
  stopGridSurfaceResizeObserver()
  stopDetailResize()
  window.removeEventListener('resize', updateLoadingSkeletonRows)
  window.removeEventListener('resize', updateAppViewportHeight)
  window.visualViewport?.removeEventListener('resize', updateAppViewportHeight)
  window.removeEventListener('resize', updateMobileViewportState)
  document.removeEventListener('keydown', handleGlobalKeydown, true)
  document.removeEventListener('visibilitychange', handleAuctionGridVisibilityChange)
  stopAuctionEvents()
  resetAuctionGridChangePolling()
  if (rowUpdateFrame !== null) {
    window.cancelAnimationFrame(rowUpdateFrame)
    rowUpdateFrame = null
  }
  if (deferredLotsReloadTimer !== null) {
    window.clearTimeout(deferredLotsReloadTimer)
    deferredLotsReloadTimer = null
  }
  clearCatalogFilterSyncTimer()
  queuedRowUpdates.clear()
})
</script>

<template>
  <AuthLoginScreen v-if="isRestoring || !isAuthenticated" />
  <main v-else class="app-shell">
    <button
      class="app-rail-backdrop"
      :class="{ 'app-rail-backdrop--visible': mobileRailOpen }"
      type="button"
      aria-label="Закрыть меню"
      @click="closeMobileRail"
    ></button>

    <aside
      class="app-sidebar app-rail app-rail--green"
      :class="{ 'app-rail--mobile-open': mobileRailOpen }"
      aria-label="Навигация и срезы"
    >
      <RouterLink class="app-rail__brand" to="/auctions" aria-label="torgi-radar">
        torgi-radar
      </RouterLink>

      <div class="app-rail__cluster">
        <RouterLink
          class="app-rail__item"
          :class="{ 'app-rail__item--active': isAuctionsModule }"
          to="/auctions"
          :aria-current="isAuctionsModule ? 'page' : undefined"
        >
          <span class="app-rail__item-icon" aria-hidden="true">A</span>
          <span class="app-rail__item-label">Аукционы</span>
        </RouterLink>
        <RouterLink
          class="app-rail__item"
          :class="{ 'app-rail__item--active': isTendersModule }"
          to="/tenders"
          :aria-current="isTendersModule ? 'page' : undefined"
        >
          <span class="app-rail__item-icon" aria-hidden="true">T</span>
          <span class="app-rail__item-label">Тендеры</span>
        </RouterLink>

        <div class="app-rail__separator" aria-hidden="true"></div>

        <button class="app-rail__item" type="button" @click="openAnalysisConfigDialog">
          <span class="app-rail__item-icon" aria-hidden="true">⚙</span>
          <span class="app-rail__item-label">Анализ</span>
        </button>

        <button class="app-rail__item" type="button" @click="openInterestProfilesDialog">
          <span class="app-rail__item-icon" aria-hidden="true">I</span>
          <span class="app-rail__item-label">Интересы</span>
        </button>
      </div>

      <div class="app-rail__cluster app-rail__cluster--bottom">
        <RouterLink
          class="app-rail__item"
          :class="{ 'app-rail__item--active': isHelpModule }"
          to="/help"
          :aria-current="isHelpModule ? 'page' : undefined"
        >
          <span class="app-rail__item-icon" aria-hidden="true">?</span>
          <span class="app-rail__item-label">Помощь</span>
        </RouterLink>

        <RouterLink
          class="app-rail__item"
          :class="{ 'app-rail__item--active': isDiagnosticsModule }"
          to="/diagnostics"
          :aria-current="isDiagnosticsModule ? 'page' : undefined"
        >
          <span class="app-rail__item-icon" aria-hidden="true">D</span>
          <span class="app-rail__item-label">Диагностика</span>
        </RouterLink>

        <UiMenu ref="accountMenuRef" placement="right" align="end" :gutter="10">
          <UiMenuTrigger as-child>
            <button
              class="app-rail__item app-rail__account-trigger"
              :class="{ 'app-rail__item--active': accountMenuOpen }"
              type="button"
              aria-haspopup="menu"
            >
              <span class="app-rail__account-avatar">{{ currentUserInitials }}</span>
              <span class="app-rail__item-label app-rail__account-label">{{ currentUser?.full_name ?? 'User' }}</span>
            </button>
          </UiMenuTrigger>

          <UiMenuContent class="app-rail__menu-content app-rail__menu-content--account">
            <UiMenuLabel>{{ currentUser?.full_name ?? 'Пользователь' }}</UiMenuLabel>
            <UiMenuSeparator />
            <UiMenuItem @select="() => authStore.logout()">Выйти</UiMenuItem>
          </UiMenuContent>
        </UiMenu>
      </div>
    </aside>

    <section class="workspace-area">
      <AnalysisConfigRoute v-if="isAnalysisConfigRoute" :bindings="analysisConfigRouteBindings" />
      <InterestProfilesRoute v-else-if="isInterestProfilesRoute" :bindings="interestProfilesRouteBindings" />
      <template v-else-if="isAuctionsModule">
        <section class="auction-toolbar" aria-label="Фильтры каталога лотов">
          <div class="toolbar-title">
            <button
              class="app-mobile-menu-button"
              type="button"
              aria-label="Открыть меню"
              :aria-expanded="mobileRailOpen"
              @click="toggleMobileRail"
            >
              <span></span>
              <span></span>
              <span></span>
            </button>
            <span class="eyebrow">Каталог банкротных торгов</span>
            <h1>Лоты для отбора</h1>
          </div>
          <div class="toolbar-actions">
            <button class="primary-button" type="button" @click="openCreatePresetDialog">
              Сохранить срез
            </button>
            <button
              v-if="mobileInlineEditTarget"
              class="auction-toolbar__edit-button"
              type="button"
              @click="openMobileInlineEdit"
            >
              Редактировать ячейку
            </button>
          </div>
        </section>

        <section class="summary-strip" aria-label="Сводка каталога">
          <div class="summary-strip__group">
            <div>
              <span>Найдено</span>
              <strong>{{ totalRows }}</strong>
            </div>
            <div>
              <span>Новые</span>
              <strong>{{ newCount }}</strong>
            </div>
            <div>
              <span>Активные</span>
              <strong>{{ activeRowsCount }}</strong>
            </div>
            <div>
              <span>Рейтинг 75+</span>
              <strong>{{ highRatingCount }}</strong>
            </div>
          </div>
          <div class="summary-strip__controls">
            <AffinoCombobox
              id="catalog-preset-combobox"
              v-model="selectedPresetId"
              class="summary-strip__preset-combobox"
              placeholder="Выберите срез"
              :options="catalogPresetOptions"
              @change="applyPresetById"
            />
            <div class="summary-strip__buttons">
              <button v-if="canUpdateCatalogPreset" class="secondary-button" type="button" @click="openUpdatePresetDialog">
                Обновить срез
              </button>
              <button v-if="selectedPreset" class="secondary-button secondary-button--danger" type="button" @click="openDeletePresetDialog">
                Удалить срез
              </button>
            </div>
          </div>
          <p class="summary-strip__status">
            {{ backgroundStatus }}
            <span v-if="lastLoadedAt"> · Загружено {{ loadedRowsCount }} · Таблица {{ lastLoadedAt }}</span>
          </p>
        </section>

        <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

        <section
          class="workspace-split"
          :class="{ 'workspace-split--with-detail': selectedLot }"
          :style="selectedLot ? { '--detail-pane-width': `${detailPaneWidth}px` } : undefined"
        >
          <section
            ref="gridSurfaceRef"
            class="grid-surface"
            :aria-busy="loading"
          >
            <AuctionWorkspace
              v-if="catalogRowModel"
              ref="gridRef"
              :loading="loading"
              :all-rows-length="allRows.length"
              :catalog-grid-has-loaded-once="catalogGridHasLoadedOnce"
              :loading-skeleton-template="loadingSkeletonTemplate"
              :loading-skeleton-columns="loadingSkeletonColumns"
              :loading-skeleton-rows="loadingSkeletonRows"
              :row-model="catalogRowModel"
              :columns="columns"
              :grid-column-widths="gridColumnWidths"
              :grid-state-persistence="gridStatePersistence"
              :is-grid-cell-editable="isGridCellEditable"
              :editable-grid-cell-style="editableGridCellStyle"
              :catalog-virtualization-options="catalogVirtualizationOptions"
              :advanced-filter-options="advancedFilterOptions"
              :quick-filter="quickFilter"
              :workspace-data-grid-theme="workspaceDataGridTheme"
              :column-menu-options="columnMenuOptions"
              :column-layout-options="columnLayoutOptions"
              :auction-grid-history-options="auctionGridHistoryOptions"
              @update:column-widths="persistGridColumnWidths"
            />
          </section>

          <aside
            v-if="selectedLot"
            class="side-pane side-pane--detail"
            aria-label="Детальная информация о лоте"
          >
            <button
              class="side-pane-resizer"
              type="button"
              aria-label="Изменить ширину панели"
              @pointerdown="startDetailResize"
            ></button>
            <header class="side-pane__header">
              <div>
                <span class="eyebrow">Лот {{ selectedLot.lotNumber || selectedLot.id }}</span>
                <h2>{{ detailTitle }}</h2>
              </div>
              <button class="icon-button" type="button" aria-label="Закрыть лот" @click="closeLotDetails">×</button>
            </header>

            <div class="detail-pane__body">
              <div class="detail-pane__score">
                <strong>{{ selectedLot.ratingScore }}</strong>
                <span>{{ selectedLot.ratingLevel }}</span>
                <span :class="['analysis-pill', `analysis-pill--${selectedLot.analysisColor || 'yellow'}`]">
                  {{ selectedLot.analysisLabel }}
                </span>
                <mark v-if="selectedLot.isNew">Новый</mark>
              </div>

              <section class="detail-section detail-section--actuality">
                <div class="detail-section__header">
                  <span class="eyebrow">Актуальность</span>
                  <span :class="['status-chip', `status-chip--${lifecycleStatusTone(selectedLot.lifecycleStatus)}`]">
                    {{ formatLifecycleStatus(selectedLot.lifecycleStatus) }}
                  </span>
                </div>
                <dl class="detail-list detail-list--dense detail-list--compact">
                  <template v-for="field in detailActualityFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section class="detail-section detail-section--media">
                <span class="eyebrow">Медиа</span>
                <div v-if="detailLoading" class="detail-muted">Загрузка</div>
                <div v-else-if="detailImages.length && activeDetailImage" class="detail-gallery">
                  <div class="detail-gallery__stage">
                    <button
                      v-if="detailImages.length > 1"
                      class="detail-gallery__nav detail-gallery__nav--prev"
                      type="button"
                      aria-label="Предыдущее фото"
                      @click="showPreviousDetailImage"
                    >
                      ‹
                    </button>
                    <img
                      :src="activeDetailImage.thumbnailUrl || activeDetailImage.url"
                      :alt="activeDetailImage.name || 'Изображение лота'"
                      loading="lazy"
                    />
                    <button
                      v-if="detailImages.length > 1"
                      class="detail-gallery__nav detail-gallery__nav--next"
                      type="button"
                      aria-label="Следующее фото"
                      @click="showNextDetailImage"
                    >
                      ›
                    </button>
                  </div>
                  <div v-if="detailImages.length > 1" class="detail-gallery__thumbs" aria-label="Фотографии лота">
                    <button
                      v-for="(image, index) in detailImages"
                      :key="image.url || image.name || `image-${index}`"
                      :class="['detail-gallery__thumb', { 'detail-gallery__thumb--active': index === activeDetailImageIndex }]"
                      type="button"
                      :aria-label="`Показать фото ${index + 1}`"
                      @click="selectDetailImage(index)"
                    >
                      <img :src="image.thumbnailUrl || image.url" :alt="image.name || `Фото ${index + 1}`" loading="lazy" />
                    </button>
                  </div>
                </div>
                <ul v-else-if="mediaDocuments.length" class="detail-files">
                  <li
                    v-for="(document, index) in mediaDocuments"
                    :key="document.external_id || document.name || `media-${index}`"
                  >
                    <a v-if="document.url" :href="document.url" target="_blank" rel="noreferrer">
                      {{ document.name || document.document_type || 'Медиафайл' }}
                    </a>
                    <span v-else>{{ document.name || document.document_type || 'Медиафайл' }}</span>
                    <small>{{ document.received_at || document.document_type || '' }}</small>
                  </li>
                </ul>
                <div v-else-if="lockedTbankrotImageCount" class="detail-muted">
                  TBankrot скрыл фото за тарифом: в HTML доступен только размытый placeholder.
                </div>
                <div v-else class="detail-muted">Медиа не найдены</div>
              </section>

              <section v-if="analysisReasonItems.length" class="detail-section">
                <span class="eyebrow">Анализ модели</span>
                <ul class="detail-bullet-list">
                  <li v-for="reason in analysisReasonItems" :key="reason">{{ reason }}</li>
                </ul>
              </section>

              <div v-if="detailLoading || detailLiveRefreshing || detailReanalyzing || detailStatus" class="detail-live-status" role="status" aria-live="polite">
                <span v-if="detailLoading || detailLiveRefreshing || detailReanalyzing" class="detail-live-status__spinner" aria-hidden="true"></span>
                <span>{{ detailStatus || 'Подгружаю live-данные с площадки' }}</span>
              </div>

              <section class="detail-section decision-report-panel">
                <div class="detail-section__header">
                  <span class="eyebrow">Решение</span>
                  <span v-if="selectedDecisionReport" class="decision-report-panel__level">
                    {{ formatDecisionLevel(selectedDecisionReport.decision_level) }}
                  </span>
                </div>
                <div v-if="decisionReportLoading" class="detail-muted">Загружаю отчет решения</div>
                <div v-else-if="decisionReportStatus === 'empty'" class="detail-muted">Снимок решения еще не создан</div>
                <div v-else-if="decisionReportStatus === 'error'" class="detail-muted">
                  {{ decisionReportError || 'Не удалось загрузить отчет решения' }}
                </div>
                <template v-else-if="selectedDecisionReport">
                  <dl class="detail-list detail-list--dense decision-report-panel__summary">
                    <template v-for="field in decisionReportSummaryFields" :key="field.label">
                      <dt>{{ field.label }}</dt>
                      <dd>{{ field.value }}</dd>
                    </template>
                  </dl>
                  <div v-if="decisionReportReasons.length" class="decision-report-panel__group">
                    <h3>Причины</h3>
                    <ul class="detail-bullet-list">
                      <li v-for="reason in decisionReportReasons" :key="reason.code">{{ reason.message }}</li>
                    </ul>
                  </div>
                  <div v-if="decisionReportRisks.length" class="decision-report-panel__group">
                    <h3>Риски</h3>
                    <ul class="detail-bullet-list">
                      <li v-for="risk in decisionReportRisks" :key="risk.code">
                        <strong>{{ risk.level }}</strong>
                        <span>{{ risk.message }}</span>
                      </li>
                    </ul>
                  </div>
                  <div v-if="decisionReportNextActions.length" class="decision-report-panel__group">
                    <h3>Следующие действия</h3>
                    <ul class="detail-bullet-list">
                      <li v-for="action in decisionReportNextActions" :key="`${action.action}-${action.label}`">
                        {{ action.label }}<span v-if="action.deadline"> · {{ action.deadline }}</span>
                      </li>
                    </ul>
                  </div>
                </template>
                <div v-else class="detail-muted">Отчет решения появится после локальной генерации снимка</div>
              </section>

              <section v-if="economyFields.length" class="detail-section">
                <span class="eyebrow">Экономика</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="field in economyFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="priceScheduleFields.length" class="detail-section">
                <span class="eyebrow">Снижение цены</span>
                <dl class="detail-list detail-list--dense detail-list--schedule">
                  <template v-for="field in priceScheduleFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="selectedWorkspace" class="detail-section">
                <span class="eyebrow">История изменений</span>
                <ul v-if="changeFields.length" class="change-list">
                  <li v-for="(change, index) in changeFields" :key="`${change.label}-${index}`">
                    <strong>{{ change.label }}</strong>
                    <span>{{ change.previous || 'Не было' }}</span>
                    <b aria-hidden="true">→</b>
                    <span>{{ change.current || 'Не указано' }}</span>
                  </li>
                </ul>
                <div v-else class="detail-muted">Изменений между последними снимками не найдено</div>
                <dl v-if="changeSummaryFields.length" class="detail-list detail-list--dense detail-list--compact">
                  <template v-for="field in changeSummaryFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="detailFields.length" class="detail-section detail-section--summary">
                <span class="eyebrow">Основные сведения</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="field in detailFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value || 'Не указано' }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="lotInfoFields.length" class="detail-section">
                <span class="eyebrow">Информация о лоте</span>
                <p v-if="detailCachedAt">Кэш обновлен: {{ detailCachedAt }}</p>
                <dl class="detail-list detail-list--dense">
                  <template v-for="field in lotInfoFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="lotTextFields.length" class="detail-section">
                <span class="eyebrow">Описание и условия</span>
                <div class="detail-text-fields">
                  <article v-for="field in lotTextFields" :key="field.label" class="detail-text-field">
                    <h3>{{ field.label }}</h3>
                    <p>{{ field.value }}</p>
                  </article>
                </div>
              </section>

              <section v-if="organizerFields.length" class="detail-section">
                <span class="eyebrow">Организатор торгов</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="field in organizerFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="auctionInfoFields.length" class="detail-section">
                <span class="eyebrow">Информация об аукционе</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="field in auctionInfoFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="debtorFields.length" class="detail-section">
                <span class="eyebrow">Информация о должнике</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="field in debtorFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="auctionLots.length" class="detail-section">
                <span class="eyebrow">Лоты аукциона</span>
                <div class="detail-table-wrapper">
                  <table class="detail-table">
                    <thead>
                      <tr>
                        <th>№</th>
                        <th>Лот</th>
                        <th>Цена</th>
                        <th>Статус</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="lot in auctionLots"
                        :key="`${lot.number || ''}-${lot.name || ''}`"
                        :class="{ 'detail-table__row--active': lot.number && lot.number === selectedLot.lotNumber }"
                      >
                        <td>{{ lot.number }}</td>
                        <td>{{ lot.name }}</td>
                        <td>{{ lot.initial_price }}</td>
                        <td>{{ lot.status }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section v-if="rawLotFields.length" class="detail-section">
                <span class="eyebrow">Все сведения лота</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="(field, index) in rawLotFields" :key="`lot-${field.label}-${index}`">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section v-if="rawAuctionFields.length" class="detail-section">
                <span class="eyebrow">Все сведения аукциона</span>
                <dl class="detail-list detail-list--dense">
                  <template v-for="(field, index) in rawAuctionFields" :key="`auction-${field.label}-${index}`">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
              </section>

              <section class="detail-section">
                <span class="eyebrow">Файлы</span>
                <div v-if="detailLoading" class="detail-muted">Загрузка</div>
                <ul v-else-if="fileDocuments.length" class="detail-files">
                  <li
                    v-for="(document, index) in fileDocuments"
                    :key="document.external_id || document.name || `document-${index}`"
                  >
                    <a v-if="document.url" :href="document.url" target="_blank" rel="noreferrer">
                      {{ document.name || document.document_type || 'Документ' }}
                    </a>
                    <span v-else>{{ document.name || document.document_type || 'Документ' }}</span>
                    <small>{{ [document.received_at, document.signature_status, document.document_type].filter(Boolean).join(' · ') }}</small>
                  </li>
                </ul>
                <div v-else class="detail-muted">Файлы не найдены</div>
              </section>
            </div>

            <footer class="side-pane__footer">
              <button
                v-if="selectedLot.lotId"
                class="secondary-button"
                type="button"
                :disabled="detailLiveRefreshing || detailReanalyzing"
                @click="refreshSelectedLotLiveDetails"
              >
                {{ detailLiveRefreshing ? 'В очереди' : 'Live' }}
              </button>
              <button
                v-if="selectedLot.lotId"
                class="secondary-button"
                type="button"
                :disabled="detailLiveRefreshing || detailReanalyzing"
                @click="reanalyzeSelectedLotDetails"
              >
                {{ detailReanalyzing ? 'Пересчет' : 'Локально' }}
              </button>
              <a v-if="detailLotUrl" class="secondary-button" :href="detailLotUrl" target="_blank" rel="noreferrer">
                Лот
              </a>
              <a v-if="detailAuctionUrl" class="primary-button" :href="detailAuctionUrl" target="_blank" rel="noreferrer">
                Аукцион
              </a>
            </footer>
          </aside>
        </section>
      </template>

      <section v-else-if="isHelpModule" class="help-workspace" aria-label="Помощь">
        <header class="auction-toolbar help-toolbar">
          <div class="toolbar-title">
            <button
              class="app-mobile-menu-button"
              type="button"
              aria-label="Открыть меню"
              :aria-expanded="mobileRailOpen"
              @click="toggleMobileRail"
            >
              <span></span>
              <span></span>
              <span></span>
            </button>
            <span class="eyebrow">Справка</span>
            <h1>Как работает система</h1>
          </div>
        </header>

        <article class="help-document" v-html="helpDocumentHtml"></article>
      </section>

      <SourceDiagnosticsView
        v-else-if="isDiagnosticsModule"
        :mobile-rail-open="mobileRailOpen"
        @toggle-mobile-rail="toggleMobileRail"
      />

      <ProcurementTenderGrid
        v-else
        :post-json="postProcurementServerGridJson"
        :get-json="getProcurementServerJson"
        :mobile-rail-open="mobileRailOpen"
        @toggle-mobile-rail="toggleMobileRail"
      />
    </section>

    <Teleport to="#affino-dialog-host">
      <transition name="dialog-layer">
        <div
          v-if="presetDialog.snapshot.value.isOpen"
          class="app-dialog-layer"
          @click.self="void presetDialog.close('backdrop')"
        >
          <div
            ref="presetDialogRef"
            class="app-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="preset-dialog-title"
            tabindex="-1"
          >
            <header class="app-dialog__header">
              <div>
                <span class="eyebrow">Подборки</span>
                <h2 id="preset-dialog-title">{{ presetDialogTitle }}</h2>
              </div>
              <button class="icon-button" type="button" aria-label="Закрыть окно" @click="void presetDialog.close('programmatic')">
                ×
              </button>
            </header>

            <div class="app-dialog__body app-dialog__body--scroll">
              <p class="app-dialog__text">{{ presetDialogDescription }}</p>

              <label v-if="presetDialogMode !== 'delete'" class="app-dialog__field">
                <span>Название подборки</span>
                <input
                  :ref="setPresetDialogInitialRef"
                  v-model="presetNameDraft"
                  type="text"
                  maxlength="160"
                  placeholder="Например, Легковые до 500k"
                  @keydown.enter.prevent="void submitPresetDialog()"
                />
              </label>

              <div v-else class="app-dialog__danger">
                <strong>{{ selectedPreset?.name }}</strong>
              </div>
            </div>

            <footer class="app-dialog__footer">
              <button class="secondary-button" type="button" @click="void presetDialog.close('programmatic')">Отмена</button>
              <button
                :ref="presetDialogMode === 'delete' ? setPresetDialogInitialRef : undefined"
                class="primary-button"
                :class="{ 'primary-button--danger': presetDialogMode === 'delete' }"
                type="button"
                @click="void submitPresetDialog()"
              >
                {{ presetDialogSubmitLabel }}
              </button>
            </footer>
          </div>
        </div>
      </transition>
    </Teleport>
  </main>
</template>
