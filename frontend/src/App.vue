<script setup lang="ts">
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { useRoute } from 'vue-router'
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
  defineDataGridColumnMenu,
  defineDataGridColumns,
  type DataGridAppColumnFilterOptions,
  type DataGridAppFilterValueNormalizationContext,
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
import { createDialogFocusOrchestrator, useDialogController } from '@affino/dialog-vue'
import { ApiRequestError as ApiClientRequestError } from './api/http'
import { fetchLotDecisionReport } from './api/decisionReports'
import {
  createUserInterestProfile,
  createUserInterestProfileFromPreset,
  deleteUserInterestProfile,
  fetchUserInterestProfiles,
  refreshUserInterestProfileFromPreset,
  updateUserInterestProfile,
} from './api/userInterestProfiles'
import { createTelegramConnectToken } from './api/telegram'
import AuthLoginScreen from './components/AuthLoginScreen.vue'
import AnalysisSignalTooltip from './components/AnalysisSignalTooltip.vue'
import LotNameCell from './components/LotNameCell.vue'
import RatingInfoTooltip from './components/RatingInfoTooltip.vue'
import AuctionWorkspace from './components/AuctionWorkspace.vue'
import ProcurementTenderGrid from './components/ProcurementTenderGrid.vue'
import SourceDiagnosticsView from './components/SourceDiagnosticsView.vue'
import {
  createAuctionServerDatasource,
  type AuctionServerDatasource,
  type AuctionServerGridFilters,
  type AuctionServerGridSummary,
} from './datagrid/auctionServerDatasource'
import { AUCTION_GRID_EDITABLE_COLUMN_IDS } from './datagrid/auctionGridEdits'
import {
  catalogAdvancedFilterOptions,
  catalogQuickFilter,
  catalogRowModelPrefetchOptions,
  catalogVirtualizationOptions,
} from './datagrid/auctionGridUiConfig'
import { useAuthStore } from './stores/auth'
import { workspaceDataGridTheme } from './theme/dataGridTheme'
import type { ActionRecommendation, DecisionLevel, LotDecisionReport } from './types/decisionReport'
import type { LotScoringProfilePayload, UserInterestProfile } from './types/userInterestProfiles'
import howItWorksMarkdown from '../../docs/how-it-works.md?raw'

type ApiColumn = {
  key: string
  title: string
  data_type: string
  width: number | null
}

type ApiSource = {
  code: string
  title: string
  website: string
  enabled: boolean
}

type AuctionPipelineSourceSyncStatus = {
  code: string
  title: string
  enabled: boolean
  last_sync_started_at: string | null
  last_sync_completed_at: string | null
  next_sync_not_before: string | null
  next_sync_not_after: string | null
  last_sync_error: string | null
}

type ProcurementAttractiveness = {
  score: number
  level: string
  reasons: string[]
}

type ProcurementLot = {
  id: number
  source: string
  registry_number: string
  law: string | null
  title: string | null
  status: string | null
  customer_name: string | null
  procedure_type: string | null
  initial_price_value: string | number | null
  publication_at: string | null
  application_deadline_at: string | null
  notice_url: string | null
  is_new: boolean
  attractiveness: ProcurementAttractiveness
}

type ProcurementLotListResponse = {
  items: ProcurementLot[]
  total: number
  page: number
  page_size: number
}

type AuctionPipelineHealthResponse = {
  counters: {
    enrichment_requested: number
    enrichment_due_now: number
    enrichment_claimed_active: number
    enrichment_retry_waiting: number
    enrichment_failed_with_error: number
    enrichment_maxed_out: number
    scoring_stale_or_incomplete: number
    scored_current: number
  }
  sources: AuctionPipelineSourceSyncStatus[]
}

type ApiLotImage = {
  url: string
  thumbnail_url: string | null
  alt: string | null
  source: string | null
}

type DetailImage = {
  url: string
  thumbnailUrl: string
  name: string | null
}

type ApiPriceScheduleStep = {
  starts_at: string
  price: string
}

type ApiLotRow = {
  row_id: string
  source: string
  source_title: string
  auction_id: string | null
  auction_number: string | null
  auction_name: string | null
  auction_url: string | null
  publication_date: string | null
  lot_id: string | null
  lot_number: string | null
  lot_name: string | null
  lot_description: string | null
  lot_url: string | null
  category: string | null
  location: string | null
  location_region: string | null
  location_city: string | null
  location_address: string | null
  location_coordinates: string | null
  debtor_name: string | null
  model_category: string | null
  status: string | null
  initial_price: string | null
  initial_price_value: string | number | null
  current_price: string | null
  current_price_value: string | number | null
  minimum_price: string | null
  minimum_price_value: string | number | null
  price_schedule: ApiPriceScheduleStep[]
  images: ApiLotImage[]
  primary_image_url: string | null
  image_count: number
  organizer_name: string | null
  application_deadline: string | null
  auction_date: string | null
  market_value: string | number | null
  platform_fee: string | number | null
  delivery_cost: string | number | null
  dismantling_cost: string | number | null
  repair_cost: string | number | null
  storage_cost: string | number | null
  legal_cost: string | number | null
  other_costs: string | number | null
  target_profit: string | number | null
  total_expenses: string | number | null
  full_entry_cost: string | number | null
  potential_profit: string | number | null
  roi: string | number | null
  market_discount: string | number | null
  formula_max_purchase_price: string | number | null
  exclude_from_analysis: boolean
  exclusion_reason: string | null
  freshness: {
    is_new: boolean
    first_seen_at: string | null
    last_seen_at: string | null
    status_changed_at: string | null
  }
  rating: {
    score: number
    level: string
    reasons: string[]
    breakdown?: RatingBreakdown | null
  }
  analysis: {
    status: string
    color: string
    label: string
    category: string | null
    matched_keyword: string | null
    is_excluded: boolean
    exclusion_keyword: string | null
    legal_risk: string
    completeness: string
    has_documents: boolean
    has_photos: boolean
    hours_to_deadline: number | null
    reasons: string[]
  }
  work_decision_status: string | null
  lifecycle_status: string | null
  actuality_checked_at: string | null
}

type ApiDocument = {
  external_id: string | null
  received_at: string | null
  name: string | null
  url: string | null
  signature_status: string | null
  comment: string | null
  document_type: string | null
}

type ApiField = {
  name: string
  value: string
}

type ApiOrganizer = {
  name: string | null
  inn: string | null
  website: string | null
  contact_name: string | null
  phone: string | null
  fax: string | null
}

type ApiDebtor = {
  debtor_type: string | null
  name: string | null
  inn: string | null
  snils: string | null
  bankruptcy_case_number: string | null
  arbitration_court: string | null
  arbitration_manager: string | null
  managers_organization: string | null
  region: string | null
}

type ApiAuctionSummary = {
  external_id: string | null
  number: string | null
  name: string | null
  url: string | null
  publication_date: string | null
  participant_form: string | null
  price_offer_form: string | null
  auction_date: string | null
  application_start: string | null
  application_deadline: string | null
  winner_selection_order: string | null
  application_order: string | null
  repeat: string | null
  efrsb_message_number: string | null
}

type ApiLotSummary = {
  external_id: string | null
  number: string | null
  name: string | null
  url: string | null
  category: string | null
  location: string | null
  region: string | null
  city: string | null
  address: string | null
  coordinates: string | null
  classifier: string | null
  currency: string | null
  initial_price: string | null
  current_price: string | null
  minimum_price: string | null
  market_value: string | null
  status: string | null
  step_percent: string | null
  step_amount: string | null
  deposit_amount: string | null
  deposit_method: string | null
  deposit_payment_date: string | null
  deposit_return_date: string | null
  deposit_order: string | null
  applications_count: string | null
  description: string | null
  inspection_order: string | null
  price_schedule: ApiPriceScheduleStep[]
  images: ApiLotImage[]
  primary_image_url: string | null
}

type LotDetailResponse = {
  source: string
  url: string
  auction: ApiAuctionSummary
  lot: ApiLotSummary
  organizer: ApiOrganizer | null
  debtor: ApiDebtor | null
  documents: ApiDocument[]
  raw_fields: ApiField[]
  raw_tables: string[][]
}

type LotWorkItem = {
  id: number | null
  lot_record_id: number
  decision_status: string | null
  assignee: string | null
  comment: string | null
  inspection_at: string | null
  inspection_result: string | null
  final_decision: string | null
  investor: string | null
  deposit_status: string | null
  application_status: string | null
  exclude_from_analysis: boolean | null
  exclusion_reason: string | null
  category_override: string | null
  max_purchase_price: string | number | null
  market_value: string | number | null
  platform_fee: string | number | null
  delivery_cost: string | number | null
  dismantling_cost: string | number | null
  repair_cost: string | number | null
  storage_cost: string | number | null
  legal_cost: string | number | null
  other_costs: string | number | null
  target_profit: string | number | null
  analogs: Array<Record<string, unknown>>
  created_at: string | null
  updated_at: string | null
}

type LotEconomy = {
  current_price: string | number | null
  market_value: string | number | null
  total_expenses: string | number | null
  full_entry_cost: string | number | null
  potential_profit: string | number | null
  roi: string | number | null
  market_discount: string | number | null
  target_profit: string | number | null
  max_purchase_price: string | number | null
}

type LotFieldChange = {
  label: string
  previous: string | null
  current: string | null
  change_type: string
}

type LotChangeSummary = {
  observations_count: number
  detail_observations_count: number
  last_observed_at: string | null
  previous_observed_at: string | null
  last_detail_observed_at: string | null
  previous_detail_observed_at: string | null
  status_changed_at: string | null
  content_changed: boolean
  detail_changed: boolean
  fields: LotFieldChange[]
}

type LotWorkspaceResponse = {
  record_id: number
  row: ApiLotRow
  lot_detail: LotDetailResponse | null
  auction_detail: AuctionDetailResponse | null
  detail_cached_at: string | null
  work_item: LotWorkItem
  economy: LotEconomy
  changes: LotChangeSummary
  current_enrichment_state: LotWorkspaceEnrichmentState | null
}

type LotWorkspaceEnrichmentState = {
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

type LotWorkspaceRefreshResponse = {
  status: 'queued' | 'rate_limited' | 'already_pending'
  queued: boolean
  next_allowed_at: string | null
  current_enrichment_state: LotWorkspaceEnrichmentState
}

type AuctionDetailResponse = {
  source: string
  url: string
  auction: ApiAuctionSummary
  organizer: ApiOrganizer
  debtor: ApiDebtor
  lots: ApiLotSummary[]
  documents: ApiDocument[]
  raw_fields: ApiField[]
  raw_tables: string[][]
}

type DetailField = {
  label: string
  value: string
}

type WorkDraft = {
  decision_status: string
  assignee: string
  comment: string
  inspection_at: string
  inspection_result: string
  final_decision: string
  investor: string
  deposit_status: string
  application_status: string
  exclude_from_analysis: boolean
  exclusion_reason: string
  category_override: string
  market_value: string
  platform_fee: string
  delivery_cost: string
  dismantling_cost: string
  repair_cost: string
  storage_cost: string
  legal_cost: string
  other_costs: string
  target_profit: string
}

type LotsResponse = {
  columns: ApiColumn[]
  rows: ApiLotRow[]
  total: number
  pagination: {
    page: number
    page_size: number
    total: number
    total_pages: number
  }
  available_sources: ApiSource[]
}

type CatalogColumnHistogramRequest = Parameters<NonNullable<DataGridDataSource<GridLotRow>['getColumnHistogram']>>[0]

type LotHistogramPayload = {
  column_id: string
  options: Record<string, unknown>
  period: string
  source: string | null
  status: string | null
  analysis_color: string | null
  min_price: number | null
  max_price: number | null
  only_new: boolean
  shortlist: boolean
  min_rating: number | null
  sort_model: readonly DataGridSortState[]
  grid_filter: DataGridFilterSnapshot | null
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

type GridLotRow = {
  id: string
  rowRevision: number
  analysisStatus: string
  analysisColor: string
  analysisLabel: string
  analysisCategory: string
  analysisReasons: string[]
  source: string
  sourceTitle: string
  auctionId: string
  auctionNumber: string
  auctionName: string
  publicationDate: Date | null
  lotId: string
  lotNumber: string
  lotName: string
  lotDescription: string
  location: string
  locationRegion: string
  locationCity: string
  locationAddress: string
  locationCoordinates: string
  debtorName: string
  status: string
  initialPrice: number | null
  price: number | null
  minimumPrice: number | null
  marketValue: number | null
  priceSchedule: ApiPriceScheduleStep[]
  platformFee: number | null
  deliveryCost: number | null
  dismantlingCost: number | null
  repairCost: number | null
  storageCost: number | null
  legalCost: number | null
  otherCosts: number | null
  targetProfit: number | null
  totalExpenses: number | null
  fullEntryCost: number | null
  potentialProfit: number | null
  roiValue: number | null
  marketDiscount: number | null
  formulaMaxPurchasePrice: number | null
  excludeFromAnalysis: boolean
  exclusionReason: string
  organizer: string
  applicationDeadline: Date | null
  auctionDate: Date | null
  isNew: boolean
  firstSeenAt: Date | null
  lastSeenAt: Date | null
  lifecycleStatus: string
  actualityCheckedAt: Date | null
  ratingScore: number
  ratingLevel: string
  ratingReasons: string[]
  ratingBreakdown: RatingBreakdown | null
  workDecisionStatus: string
  lotUrl: string
  auctionUrl: string
  images: ApiLotImage[]
  primaryImageUrl: string
  imageCount: number
}

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

type RatingBreakdown = {
  dimensions?: Record<string, RatingDimensionBreakdown>
  caps?: RatingCapBreakdown[]
}
type GridApi = NonNullable<ReturnType<DataGridExposed<GridLotRow>['getApi']>>
type GridSelectionSnapshot = ReturnType<GridApi['selection']['getSnapshot']>

type CatalogDataSource = DataGridDataSource<GridLotRow>
type CatalogAuctionServerDataSource = AuctionServerDatasource<ApiLotRow, GridLotRow>
  & {
    applyInvalidation?: (invalidation: unknown, options?: { datasetVersion?: unknown }) => void
  }

type CatalogRowModel = DataSourceBackedRowModel<GridLotRow> & {
  patchRows?: (
    updates: readonly { rowId: string | number; data: Partial<GridLotRow> }[],
    options?: {
      recomputeSort?: boolean
      recomputeFilter?: boolean
      recomputeGroup?: boolean
      emit?: boolean
      signal?: AbortSignal | null
    },
  ) => void | Promise<void>
  dataSource: CatalogDataSource
}

type AuctionWorkspaceExposed = {
  getApi: DataGridExposed<GridLotRow>['getApi']
  getRuntime: DataGridExposed<GridLotRow>['getRuntime']
  getSavedView: DataGridExposed<GridLotRow>['getSavedView']
  applySavedView: DataGridExposed<GridLotRow>['applySavedView']
  restoreFocusAnchor: DataGridExposed<GridLotRow>['restoreFocusAnchor']
  captureFocusAnchor: DataGridExposed<GridLotRow>['captureFocusAnchor']
}

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
  row?: TApiRow | GridLotRow | unknown
}

type GridHistoryMutationResponse<TApiRow> = GridHistoryStatusLike & {
  operationId?: string | null
  action?: 'undo' | 'redo'
  rows?: GridHistoryRowSnapshot<TApiRow>[]
  updatedRows?: GridHistoryRowSnapshot<TApiRow>[]
  invalidation?: unknown
  rejected?: readonly unknown[]
}

type HistoryStatusSource = {
  subscribeHistoryStatus?: (listener: (status: GridHistoryStatusLike) => void) => () => void
}

type DatasetPeriod = 'week' | 'month' | 'year'

type FilterPreset = {
  id: string
  name: string
  filters: ServerQuickFiltersState
  grid_view: unknown | null
  is_favorite: boolean
  created_at: string | null
  updated_at: string | null
}

type AnalysisConfigCategoryRule = {
  category: string
  keywords: string[]
}

type AnalysisConfigLegalRiskRules = {
  high_keywords: string[]
  medium_keywords: string[]
  medium_categories: string[]
}

type OwnerScoringProfile = {
  target_regions: string[]
  target_categories: string[]
  min_budget: string | number | null
  max_budget: string | number | null
  minimum_roi: string | number | null
  minimum_market_discount: string | number | null
  excluded_terms: string[]
  discouraged_terms: string[]
  max_delivery_distance_km: string | number | null
  allow_dismantling: boolean
  legal_risk_tolerance: 'low' | 'medium' | 'high'
  require_documents: boolean
  require_photos: boolean
}

type ScoringDimensionWeights = {
  economics: string | number
  risk: string | number
  urgency: string | number
  data_quality: string | number
  operational_readiness: string | number
  owner_fit: string | number
  manual_intent: string | number
}

type AnalysisConfigResponse = {
  id: string
  category_rules: AnalysisConfigCategoryRule[]
  exclusion_keywords: string[]
  legal_risk_rules: AnalysisConfigLegalRiskRules
  owner_profile: OwnerScoringProfile
  dimension_weights: ScoringDimensionWeights
  created_at: string
  updated_at: string
}

type AnalysisConfigDraftRule = {
  id: number
  category: string
  keywordsText: string
}

type AnalysisConfigDraft = {
  categoryRules: AnalysisConfigDraftRule[]
  exclusionKeywordsText: string
  highRiskKeywordsText: string
  mediumRiskKeywordsText: string
  mediumRiskCategoriesText: string
}

type PresetDialogMode = 'create' | 'update' | 'delete'
type InterestProfileDraft = {
  name: string
  minRating: number
  telegramEnabled: boolean
  isActive: boolean
}

type ServerQuickFiltersState = {
  period: DatasetPeriod
  source: string
  analysisColor: string
  status: string
  minPrice: string
  maxPrice: string
  onlyNew: boolean
  shortlist: boolean
  minRating: number
  includeArchived: boolean
}

type GridColumnWidthsState = Record<string, number | null>

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
const userInterestProfiles = ref<UserInterestProfile[]>([])
const analysisConfig = ref<AnalysisConfigResponse | null>(null)
const auctionPipelineHealth = ref<AuctionPipelineHealthResponse | null>(null)
const selectedPresetId = ref('')
const presetDialogMode = ref<PresetDialogMode>('create')
const presetNameDraft = ref('')
const telegramPresetIdDraft = ref('')
const interestProfileDraft = reactive<InterestProfileDraft>({
  name: '',
  minRating: 0,
  telegramEnabled: true,
  isActive: true,
})
const mobileRailOpen = ref(false)
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
const GRID_STATE_PERSISTENCE_KEY = 'auction-grid-state-v1'
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
const detailPaneWidth = ref(readStoredDetailPaneWidth())
const gridRef = ref<AuctionWorkspaceExposed | null>(null)
const gridSurfaceRef = ref<HTMLElement | null>(null)
const gridColumnWidths = ref<GridColumnWidthsState>(readStoredGridColumnWidths())
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

const filters = reactive(readStoredServerFilters())

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

type GridWorkSnapshot = {
  marketValue: number | null
  platformFee: number | null
  deliveryCost: number | null
  dismantlingCost: number | null
  repairCost: number | null
  storageCost: number | null
  legalCost: number | null
  otherCosts: number | null
  targetProfit: number | null
  excludeFromAnalysis: boolean
  exclusionReason: string
}

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
const presetDialogTriggerRef = ref<HTMLElement | null>(null)
const presetDialogRef = ref<HTMLDivElement | null>(null)
const presetDialogInitialRef = ref<HTMLElement | null>(null)
const presetDialogFocus = createDialogFocusOrchestrator({
  dialog: () => presetDialogRef.value,
  initialFocus: () => presetDialogInitialRef.value,
  returnFocus: () => presetDialogTriggerRef.value,
})
const presetDialog = useDialogController({
  focusOrchestrator: presetDialogFocus,
})
const interestProfilesDialogTriggerRef = ref<HTMLElement | null>(null)
const interestProfilesDialogRef = ref<HTMLDivElement | null>(null)
const interestProfilesDialogInitialRef = ref<HTMLElement | null>(null)
const interestProfilesDialogFocus = createDialogFocusOrchestrator({
  dialog: () => interestProfilesDialogRef.value,
  initialFocus: () => interestProfilesDialogInitialRef.value,
  returnFocus: () => interestProfilesDialogTriggerRef.value,
})
const interestProfilesDialog = useDialogController({
  focusOrchestrator: interestProfilesDialogFocus,
})
const analysisConfigDialogTriggerRef = ref<HTMLElement | null>(null)
const analysisConfigDialogRef = ref<HTMLDivElement | null>(null)
const analysisConfigDialogInitialRef = ref<HTMLElement | null>(null)
const analysisConfigDialogFocus = createDialogFocusOrchestrator({
  dialog: () => analysisConfigDialogRef.value,
  initialFocus: () => analysisConfigDialogInitialRef.value,
  returnFocus: () => analysisConfigDialogTriggerRef.value,
})
const analysisConfigDialog = useDialogController({
  focusOrchestrator: analysisConfigDialogFocus,
})
let analysisConfigRuleSeed = 0

const loadingSkeletonColumns = [
  { key: 'ratingScore', label: 'Рейтинг', width: 96, placeholderWidth: '54%' },
  { key: 'analysisLabel', label: 'Сигнал', width: 176, placeholderWidth: '76%' },
  { key: 'analysisCategory', label: 'Категория', width: 168, placeholderWidth: '72%' },
  { key: 'isNew', label: 'Новый', width: 88, placeholderWidth: '42%' },
  { key: 'sourceTitle', label: 'Площадка', width: 120, placeholderWidth: '62%' },
  { key: 'auctionNumber', label: 'Аукцион', width: 120, placeholderWidth: '58%' },
  { key: 'publicationDate', label: 'Дата публикации', width: 160, placeholderWidth: '60%' },
  { key: 'lotNumber', label: 'Лот', width: 76, placeholderWidth: '46%' },
  { key: 'lotName', label: 'Наименование', width: 430, placeholderWidth: '88%' },
  { key: 'location', label: 'Локация', width: 220, placeholderWidth: '82%' },
  { key: 'initialPrice', label: 'Начальная цена', width: 150, placeholderWidth: '70%' },
  { key: 'price', label: 'Текущая цена', width: 150, placeholderWidth: '70%' },
  { key: 'minimumPrice', label: 'Мин. цена', width: 150, placeholderWidth: '64%' },
  { key: 'status', label: 'Статус', width: 170, placeholderWidth: '78%' },
  { key: 'organizer', label: 'Организатор', width: 240, placeholderWidth: '82%' },
  { key: 'applicationDeadline', label: 'Прием заявок до', width: 180, placeholderWidth: '68%' },
  { key: 'auctionDate', label: 'Дата торгов', width: 170, placeholderWidth: '66%' },
  { key: 'lastSeenAt', label: 'Последнее наблюдение', width: 190, placeholderWidth: '72%' },
  { key: 'lifecycleStatus', label: 'Актуальность', width: 148, placeholderWidth: '66%' },
]
const loadingSkeletonRows = computed(() => Array.from({ length: loadingSkeletonVisibleRows.value }, (_, index) => index))
const loadingSkeletonTemplate = loadingSkeletonColumns.map((column) => `${column.width}px`).join(' ')

function normalizePercentFilterValue(context: DataGridAppFilterValueNormalizationContext) {
  const value = context.value
  if (value === null || value === undefined || value === '') return value

  const parsed = Number(String(value).trim().replace(/\s+/g, '').replace('%', '').replace(',', '.'))
  if (!Number.isFinite(parsed)) return value
  return String(parsed / 100)
}

const predicateFilterOnly = { valueSet: false } satisfies DataGridAppColumnFilterOptions
const percentPredicateFilter = {
  valueSet: false,
  normalizeValue: normalizePercentFilterValue,
} satisfies DataGridAppColumnFilterOptions

const columns = defineDataGridColumns<GridLotRow>()([
  {
    key: 'ratingScore',
    label: 'Рейтинг',
    dataType: 'number',
    initialState: { width: 96 },
    presentation: { align: 'right', headerAlign: 'right' },
    capabilities: { sortable: true, filterable: true, aggregatable: true },
    filter: predicateFilterOnly,
  },
  {
    key: 'analysisLabel',
    label: 'Сигнал',
    initialState: { width: 176 },
    capabilities: { sortable: true, filterable: true },
    cellRenderer: ({ row }) => {
      if (!row) return ''

      const reasons = Array.isArray(row.analysisReasons) ? row.analysisReasons : []
      const pill = h(
        'span',
        {
          class: ['analysis-pill', `analysis-pill--${row.analysisColor || 'yellow'}`],
        },
        row.analysisLabel,
      )
      return reasons.length
        ? h(
            AnalysisSignalTooltip,
            {
              reasons,
            },
            {
              default: () => pill,
            },
          )
        : pill
    },
  },
  { key: 'analysisCategory', label: 'Категория', initialState: { width: 168 } },
  {
    key: 'isNew',
    label: 'Новый',
    dataType: 'boolean',
    initialState: { width: 88 },
    capabilities: { sortable: true, filterable: true },
  },
  { key: 'sourceTitle', label: 'Площадка', initialState: { width: 120 }, filter: predicateFilterOnly },
  { key: 'auctionNumber', label: 'Аукцион', initialState: { width: 120 }, filter: predicateFilterOnly },
  {
    key: 'publicationDate',
    label: 'Дата публикации',
    dataType: 'datetime',
    initialState: { width: 160 },
    presentation: {
      format: {
        dateTime: {
          locale: 'ru-RU',
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        },
      },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
  },
  { key: 'lotNumber', label: 'Лот', initialState: { width: 76 }, filter: predicateFilterOnly },
  {
    key: 'lotName',
    label: 'Наименование',
    initialState: { width: 430 },
    filter: predicateFilterOnly,
    cellInteraction: {
      click: true,
      keyboard: ['enter'],
      role: 'button',
      label: ({ row }) => (row ? `Открыть ${row.lotName}` : 'Открыть лот'),
      onInvoke: ({ row }) => {
        if (row) void openLotDetails(row)
      },
    },
    cellRenderer: ({ displayValue, row }) =>
      row
        ? h(LotNameCell, {
            row,
            label: String(displayValue || 'Без названия'),
            onOpen: (lot: unknown) => void openLotDetails(lot as GridLotRow),
          })
        : String(displayValue || 'Без названия'),
  },
  {
    key: 'location',
    label: 'Локация',
    initialState: { width: 220 },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
  },
  {
    key: 'initialPrice',
    label: 'Начальная цена',
    dataType: 'currency',
    initialState: { width: 150 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: {
        number: {
          locale: 'ru-RU',
          style: 'currency',
          currency: 'RUB',
          maximumFractionDigits: 2,
        },
      },
    },
    capabilities: { sortable: true, filterable: true, aggregatable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.initialPrice ?? null),
  },
  {
    key: 'price',
    label: 'Текущая цена',
    dataType: 'currency',
    initialState: { width: 150 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: {
        number: {
          locale: 'ru-RU',
          style: 'currency',
          currency: 'RUB',
          maximumFractionDigits: 2,
        },
      },
    },
    capabilities: { sortable: true, filterable: true, aggregatable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.price ?? null),
  },
  {
    key: 'minimumPrice',
    label: 'Мин. цена',
    dataType: 'currency',
    initialState: { width: 150 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: {
        number: {
          locale: 'ru-RU',
          style: 'currency',
          currency: 'RUB',
          maximumFractionDigits: 2,
        },
      },
    },
    capabilities: { sortable: true, filterable: true, aggregatable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.minimumPrice ?? null),
  },
  {
    key: 'marketValue',
    label: 'Рынок',
    dataType: 'currency',
    initialState: { width: 150 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.marketValue ?? null),
  },
  {
    key: 'platformFee',
    label: 'Комиссия ЭТП',
    dataType: 'currency',
    initialState: { width: 150 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.platformFee ?? null),
  },
  {
    key: 'deliveryCost',
    label: 'Доставка',
    dataType: 'currency',
    initialState: { width: 132 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.deliveryCost ?? null),
  },
  {
    key: 'dismantlingCost',
    label: 'Демонтаж',
    dataType: 'currency',
    initialState: { width: 138 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.dismantlingCost ?? null),
  },
  {
    key: 'repairCost',
    label: 'Ремонт',
    dataType: 'currency',
    initialState: { width: 132 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.repairCost ?? null),
  },
  {
    key: 'storageCost',
    label: 'Хранение',
    dataType: 'currency',
    initialState: { width: 138 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.storageCost ?? null),
  },
  {
    key: 'legalCost',
    label: 'Юрист',
    dataType: 'currency',
    initialState: { width: 124 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.legalCost ?? null),
  },
  {
    key: 'otherCosts',
    label: 'Прочие',
    dataType: 'currency',
    initialState: { width: 124 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.otherCosts ?? null),
  },
  {
    key: 'targetProfit',
    label: 'Целевая прибыль',
    dataType: 'currency',
    initialState: { width: 168 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.targetProfit ?? null),
  },
  {
    key: 'totalExpenses',
    label: 'Все расходы',
    dataType: 'currency',
    formula: 'platformFee + deliveryCost + dismantlingCost + repairCost + storageCost + legalCost + otherCosts',
    initialState: { width: 152 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.totalExpenses ?? null),
  },
  {
    key: 'fullEntryCost',
    label: 'Полная стоимость входа',
    dataType: 'currency',
    formula: 'price + totalExpenses',
    initialState: { width: 198 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.fullEntryCost ?? null),
  },
  {
    key: 'potentialProfit',
    label: 'Потенциальная прибыль',
    dataType: 'currency',
    formula: 'marketValue - fullEntryCost',
    initialState: { width: 188 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.potentialProfit ?? null),
  },
  {
    key: 'roiValue',
    label: 'ROI',
    dataType: 'number',
    formula: 'potentialProfit / fullEntryCost',
    initialState: { width: 100 },
    presentation: { align: 'right', headerAlign: 'right', format: { number: { locale: 'ru-RU', style: 'percent', maximumFractionDigits: 1 } } },
    capabilities: { sortable: true, filterable: true },
    filter: percentPredicateFilter,
    cellRenderer: ({ row }) => formatApiPercent(row?.roiValue),
  },
  {
    key: 'marketDiscount',
    label: 'Дисконт к рынку',
    dataType: 'number',
    formula: '1 - price / marketValue',
    initialState: { width: 146 },
    presentation: { align: 'right', headerAlign: 'right', format: { number: { locale: 'ru-RU', style: 'percent', maximumFractionDigits: 1 } } },
    capabilities: { sortable: true, filterable: true },
    filter: percentPredicateFilter,
    cellRenderer: ({ row }) => formatApiPercent(row?.marketDiscount),
  },
  {
    key: 'formulaMaxPurchasePrice',
    label: 'Макс. цена покупки',
    dataType: 'currency',
    formula: 'marketValue - totalExpenses - targetProfit',
    initialState: { width: 176 },
    presentation: {
      align: 'right',
      headerAlign: 'right',
      format: { number: { locale: 'ru-RU', style: 'currency', currency: 'RUB', maximumFractionDigits: 2 } },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
    cellRenderer: ({ row }) => formatCurrency(row?.formulaMaxPurchasePrice ?? null),
  },
  {
    key: 'excludeFromAnalysis',
    label: 'Исключить',
    dataType: 'boolean',
    initialState: { width: 112 },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
  },
  {
    key: 'exclusionReason',
    label: 'Причина исключения',
    initialState: { width: 188 },
    capabilities: { sortable: true, filterable: true, editable: true },
    filter: predicateFilterOnly,
  },
  { key: 'status', label: 'Статус', initialState: { width: 170 }, filter: predicateFilterOnly },
  { key: 'organizer', label: 'Организатор', initialState: { width: 240 }, filter: predicateFilterOnly },
  {
    key: 'applicationDeadline',
    label: 'Прием заявок до',
    dataType: 'datetime',
    initialState: { width: 180 },
    presentation: {
      format: {
        dateTime: {
          locale: 'ru-RU',
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        },
      },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
  },
  {
    key: 'auctionDate',
    label: 'Дата торгов',
    dataType: 'datetime',
    initialState: { width: 170 },
    presentation: {
      format: {
        dateTime: {
          locale: 'ru-RU',
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        },
      },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
  },
  {
    key: 'lastSeenAt',
    label: 'Последнее наблюдение',
    dataType: 'datetime',
    initialState: { width: 190 },
    presentation: {
      format: {
        dateTime: {
          locale: 'ru-RU',
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        },
      },
    },
    capabilities: { sortable: true, filterable: true },
    filter: predicateFilterOnly,
  },
  {
    key: 'lifecycleStatus',
    label: 'Актуальность',
    initialState: { width: 148 },
    capabilities: { sortable: true, filterable: true },
    cellRenderer: ({ row }) =>
      row
        ? h(
            'span',
            {
              class: ['status-chip', `status-chip--${lifecycleStatusTone(row.lifecycleStatus)}`],
              title: buildLifecycleStatusTooltip(row),
            },
            formatLifecycleStatus(row.lifecycleStatus),
          )
        : '',
  },
])

const columnMenuOptions = defineDataGridColumnMenu({
  trigger: 'button+contextmenu',
  items: ['sort', 'group', 'pin', 'filter'],
  labels: {
    sort: 'Сортировка',
    group: 'Группировка',
    pin: 'Закрепление',
    filter: 'Фильтр по значениям',
    valueSearchPlaceholder: 'Поиск значений',
    selectedValuesSummary: 'Выбрано {selected} из {total}',
  },
  actions: {
    sortAsc: { label: 'По возрастанию' },
    sortDesc: { label: 'По убыванию' },
    clearSort: { label: 'Сбросить сортировку' },
    toggleGroup: { label: 'Группировать по колонке' },
    pinMenu: { label: 'Закрепить колонку' },
    pinLeft: { label: 'Слева' },
    pinRight: { label: 'Справа' },
    unpin: { label: 'Не закреплять' },
    clearFilter: { label: 'Сбросить фильтр' },
    addCurrentSelectionToFilter: { label: 'Добавить выделение в фильтр' },
    selectAllValues: { label: 'Выбрать все' },
    clearAllValues: { label: 'Очистить выбор' },
    applyFilter: { label: 'Применить' },
    cancelFilter: { label: 'Отмена' },
  },
  columns: Object.fromEntries(
    columns
      .filter((column) => 'filter' in column && column.filter?.valueSet === false)
      .map((column) => [String(column.key), { hide: ['filter'] }]),
  ),
})

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
const gridStatePersistence = {
  key: GRID_STATE_PERSISTENCE_KEY,
  storage: 'local' as const,
  includeViewportPosition: true,
  restoreOnReady: true,
  debounceMs: 300,
  setOptions: {
    dataSource: {
      atomic: true,
      resetViewportRange: { start: 0, end: SERVER_ROW_MODEL_INITIAL_FETCH_SIZE - 1 },
    },
  } satisfies DataGridSetStateOptions,
}

const presetOptions = computed(() => [
  { label: 'Подборки', value: '' },
  ...presets.value.map((preset) => ({
    label: preset.is_favorite ? `${preset.name} *` : preset.name,
    value: preset.id,
  })),
])
const activeModule = computed(() => {
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

function renderHelpMarkdown(markdown: string): string {
  const html: string[] = []
  let listOpen = false
  let blockquoteOpen = false

  const closeList = () => {
    if (!listOpen) return
    html.push('</ul>')
    listOpen = false
  }
  const closeBlockquote = () => {
    if (!blockquoteOpen) return
    html.push('</blockquote>')
    blockquoteOpen = false
  }
  const closeBlocks = () => {
    closeList()
    closeBlockquote()
  }

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) {
      closeBlocks()
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      closeBlocks()
      const marker = heading[1] ?? ''
      const title = heading[2] ?? ''
      const level = marker.length
      html.push(`<h${level}>${renderInlineMarkdown(title)}</h${level}>`)
      continue
    }

    const listItem = /^-\s+(.+)$/.exec(line)
    if (listItem) {
      closeBlockquote()
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${renderInlineMarkdown(listItem[1] ?? '')}</li>`)
      continue
    }

    const quote = /^>\s?(.+)$/.exec(line)
    if (quote) {
      closeList()
      if (!blockquoteOpen) {
        html.push('<blockquote>')
        blockquoteOpen = true
      }
      html.push(`<p>${renderInlineMarkdown(quote[1] ?? '')}</p>`)
      continue
    }

    closeBlocks()
    html.push(`<p>${renderInlineMarkdown(line)}</p>`)
  }

  closeBlocks()
  return html.join('')
}

function renderInlineMarkdown(value: string): string {
  return escapeHtml(value).replace(/`([^`]+)`/g, '<code>$1</code>')
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
const selectedPreset = computed(() => presets.value.find((preset) => preset.id === selectedPresetId.value) ?? null)
const presetsMenuRef = ref<InstanceType<typeof UiMenu> | null>(null)
const accountMenuRef = ref<InstanceType<typeof UiMenu> | null>(null)
const presetsMenuOpen = computed(() => presetsMenuRef.value?.controller.state.value.open === true)
const accountMenuOpen = computed(() => accountMenuRef.value?.controller.state.value.open === true)
const activeInterestProfiles = computed(() => userInterestProfiles.value.filter((profile) => profile.is_active))
const interestProfileSummary = computed(() => {
  if (interestProfilesLoading.value) return 'Загрузка'
  const activeCount = activeInterestProfiles.value.length
  if (!userInterestProfiles.value.length) return 'Профили не заданы'
  return `${activeCount} активн. из ${userInterestProfiles.value.length}`
})
const presetDialogTitle = computed(() => {
  if (presetDialogMode.value === 'delete') return 'Удалить подборку'
  if (presetDialogMode.value === 'update') return 'Обновить подборку'
  return 'Сохранить подборку'
})
const presetDialogDescription = computed(() => {
  if (presetDialogMode.value === 'delete') {
    return `Подборка "${selectedPreset.value?.name ?? ''}" будет удалена без возможности восстановления.`
  }
  if (presetDialogMode.value === 'update') {
    return 'Обновим имя подборки и сохраним текущее состояние фильтров и таблицы.'
  }
  return 'Сохраним текущие фильтры и раскладку таблицы как новую пользовательскую подборку.'
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

const detailTitle = computed(() => selectedLotDetails.value?.lot.name || selectedLot.value?.lotName || 'Без названия')
const liveAuction = computed(() => selectedAuctionDetails.value?.auction ?? selectedLotDetails.value?.auction ?? null)
const liveLot = computed(() => selectedLotDetails.value?.lot ?? null)
const liveOrganizer = computed(() => selectedLotDetails.value?.organizer ?? selectedAuctionDetails.value?.organizer ?? null)
const liveDebtor = computed(() => selectedLotDetails.value?.debtor ?? selectedAuctionDetails.value?.debtor ?? null)
const detailLotUrl = computed(() => selectedLotDetails.value?.lot.url || selectedLotDetails.value?.url || selectedLot.value?.lotUrl || '')
const detailAuctionUrl = computed(() => liveAuction.value?.url || selectedAuctionDetails.value?.url || selectedLot.value?.auctionUrl || '')

const detailFields = computed<DetailField[]>(() => {
  if (!selectedLot.value) return []
  return makeFields([
    ['Аналитический сигнал', selectedLot.value.analysisLabel],
    ['Категория', liveLot.value?.category || selectedLot.value.analysisCategory],
    ['Наименование', selectedLot.value.lotName],
    ['Должник', selectedLot.value.debtorName],
    ['Локация', selectedLot.value.location],
    ['Регион', selectedLot.value.locationRegion],
    ['Город', selectedLot.value.locationCity],
    ['Адрес', selectedLot.value.locationAddress],
    ['Координаты', selectedLot.value.locationCoordinates],
    ['Ручное исключение', selectedLot.value.excludeFromAnalysis ? 'Да' : 'Нет'],
    ['Причина исключения', selectedLot.value.exclusionReason],
    ['Площадка', selectedLot.value.sourceTitle],
    ['Аукцион', liveAuction.value?.number || selectedLot.value.auctionNumber],
    ['Название аукциона', liveAuction.value?.name || selectedLot.value.auctionName],
    ['Публикация', liveAuction.value?.publication_date || formatDateTime(selectedLot.value.publicationDate)],
    ['Лот', liveLot.value?.number || selectedLot.value.lotNumber],
    ['ID лота', selectedLot.value.lotId],
    ['Статус', liveLot.value?.status || selectedLot.value.status],
    ['Начальная цена', liveLot.value?.initial_price || formatCurrency(selectedLot.value.initialPrice)],
    ['Текущая цена', liveLot.value?.current_price || formatCurrency(selectedLot.value.price)],
    ['Минимальная цена', liveLot.value?.minimum_price || formatCurrency(selectedLot.value.minimumPrice)],
    ['Организатор', liveOrganizer.value?.name || selectedLot.value.organizer],
    ['Заявки до', liveAuction.value?.application_deadline || formatDateTime(selectedLot.value.applicationDeadline)],
    ['Торги', liveAuction.value?.auction_date || formatDateTime(selectedLot.value.auctionDate)],
    ['Первое наблюдение', formatDateTime(selectedLot.value.firstSeenAt)],
    ['Последнее наблюдение', formatDateTime(selectedLot.value.lastSeenAt)],
  ])
})

const lotInfoFields = computed(() =>
  makeFields([
    ['Локация', liveLot.value?.location],
    ['Регион', liveLot.value?.region],
    ['Город', liveLot.value?.city],
    ['Адрес', liveLot.value?.address],
    ['Координаты', liveLot.value?.coordinates],
    ['Категория', liveLot.value?.category],
    ['Классификатор ЕФРСБ', liveLot.value?.classifier],
    ['Валюта цены по ОКВ', liveLot.value?.currency],
    ['Начальная цена', liveLot.value?.initial_price],
    ['Текущая цена', liveLot.value?.current_price],
    ['Минимальная цена', liveLot.value?.minimum_price],
    ['Шаг, % от начальной цены', liveLot.value?.step_percent],
    ['Шаг, руб.', liveLot.value?.step_amount],
    ['Размер задатка, руб.', liveLot.value?.deposit_amount],
    ['Способ расчета обеспечения', liveLot.value?.deposit_method],
    ['Дата внесения задатка', liveLot.value?.deposit_payment_date],
    ['Дата возврата задатка', liveLot.value?.deposit_return_date],
    ['Всего подано заявок', liveLot.value?.applications_count],
  ]),
)

const lotTextFields = computed(() =>
  makeFields([
    ['Описание имущества', liveLot.value?.description || selectedLot.value?.lotDescription],
    ['Порядок ознакомления', liveLot.value?.inspection_order],
    ['Порядок внесения и возврата задатка', liveLot.value?.deposit_order],
  ]),
)

const priceScheduleSteps = computed(() => {
  if (selectedLot.value?.priceSchedule?.length) return selectedLot.value.priceSchedule
  if (liveLot.value?.price_schedule?.length) return liveLot.value.price_schedule
  return []
})

const priceScheduleFields = computed(() =>
  priceScheduleSteps.value.slice(0, DETAIL_RENDER_PRICE_SCHEDULE_LIMIT).map((step, index) => ({
    label: `${index + 1}. ${step.starts_at}`,
    value: step.price,
  })),
)

const organizerFields = computed(() =>
  makeFields([
    ['Сокращенное наименование', liveOrganizer.value?.name],
    ['ИНН', liveOrganizer.value?.inn],
    ['Адрес сайта', liveOrganizer.value?.website],
    ['Контактное лицо', liveOrganizer.value?.contact_name],
    ['Телефон', liveOrganizer.value?.phone],
    ['Факс', liveOrganizer.value?.fax],
  ]),
)

const auctionInfoFields = computed(() =>
  makeFields([
    ['Наименование', liveAuction.value?.name],
    ['Форма торга по составу участников', liveAuction.value?.participant_form],
    ['Форма представления предложений о цене', liveAuction.value?.price_offer_form],
    ['Дата проведения', liveAuction.value?.auction_date],
    ['Дата начала представления заявок', liveAuction.value?.application_start],
    ['Дата окончания представления заявок', liveAuction.value?.application_deadline],
    ['Повторные торги', liveAuction.value?.repeat],
    ['Номер сообщения в ЕФРСБ', liveAuction.value?.efrsb_message_number],
    ['Порядок определения победителя', liveAuction.value?.winner_selection_order],
    ['Порядок представления заявок', liveAuction.value?.application_order],
  ]),
)

const debtorFields = computed(() =>
  makeFields([
    ['Тип должника', liveDebtor.value?.debtor_type],
    ['ФИО / наименование должника', liveDebtor.value?.name],
    ['ИНН', liveDebtor.value?.inn],
    ['СНИЛС', liveDebtor.value?.snils],
    ['Наименование арбитражного суда', liveDebtor.value?.arbitration_court],
    ['Номер дела о банкротстве', liveDebtor.value?.bankruptcy_case_number],
    ['Арбитражный управляющий', liveDebtor.value?.arbitration_manager],
    ['СРО арбитражных управляющих', liveDebtor.value?.managers_organization],
    ['Регион', liveDebtor.value?.region],
  ]),
)

const rawLotFields = computed(() => normalizeRawFields(selectedLotDetails.value?.raw_fields ?? []))
const rawAuctionFields = computed(() => normalizeRawFields(selectedAuctionDetails.value?.raw_fields ?? []))
const auctionLots = computed(() => selectedAuctionDetails.value?.lots ?? [])
const activeDetailImageIndex = ref(0)
const economyFields = computed(() =>
  makeFields([
    ['Текущая цена', formatApiMoney(selectedLot.value?.price ?? selectedWorkspace.value?.economy.current_price)],
    ['Рыночная стоимость', formatApiMoney(selectedLot.value?.marketValue ?? selectedWorkspace.value?.economy.market_value)],
    ['Все расходы', formatApiMoney(selectedLot.value?.totalExpenses ?? selectedWorkspace.value?.economy.total_expenses)],
    ['Целевая прибыль', formatApiMoney(selectedLot.value?.targetProfit ?? selectedWorkspace.value?.economy.target_profit)],
    ['Полная стоимость входа', formatApiMoney(selectedLot.value?.fullEntryCost ?? selectedWorkspace.value?.economy.full_entry_cost)],
    ['Потенциальная прибыль', formatApiMoney(selectedLot.value?.potentialProfit ?? selectedWorkspace.value?.economy.potential_profit)],
    ['ROI', formatApiPercent(selectedLot.value?.roiValue ?? selectedWorkspace.value?.economy.roi)],
    ['Дисконт к рынку', formatApiPercent(selectedLot.value?.marketDiscount ?? selectedWorkspace.value?.economy.market_discount)],
    ['Макс. цена покупки', formatApiMoney(selectedLot.value?.formulaMaxPurchasePrice ?? selectedWorkspace.value?.economy.max_purchase_price)],
  ]),
)
const decisionReportSummaryFields = computed(() => {
  const report = selectedDecisionReport.value
  if (!report) return []
  return makeFields([
    ['Решение', formatDecisionLevel(report.decision_level)],
    ['Рекомендация', formatActionRecommendation(report.recommendation)],
    ['Рейтинг', `${report.rating_score} / ${report.rating_level}`],
    ['Макс. цена покупки', formatApiMoney(report.economics?.max_buy_price)],
    ['Сгенерирован', formatDateTime(report.generated_at)],
  ])
})
const decisionReportReasons = computed(() => selectedDecisionReport.value?.reasons ?? [])
const decisionReportRisks = computed(() => selectedDecisionReport.value?.risks ?? [])
const decisionReportNextActions = computed(() => selectedDecisionReport.value?.next_actions ?? [])
const analysisReasonItems = computed(() =>
  (selectedLot.value?.analysisReasons ?? []).filter((reason) => !(detailImages.value.length && isNoPhotoReason(reason))),
)
const detailCachedAt = computed(() => formatDateTime(selectedWorkspace.value?.detail_cached_at ?? null))
const selectedSourceSyncStatus = computed(() => {
  const sourceCode = selectedLot.value?.source
  if (!sourceCode) return null
  return auctionPipelineHealth.value?.sources.find((source) => source.code === sourceCode) ?? null
})
const selectedCurrentEnrichmentState = computed(() => selectedWorkspace.value?.current_enrichment_state ?? null)
const detailActualityFields = computed(() =>
  makeFields([
    ['Статус актуальности', formatLifecycleStatus(selectedLot.value?.lifecycleStatus)],
    ['Проверка актуальности', formatDateTime(selectedLot.value?.actualityCheckedAt ?? null)],
    ['Последний кэш детали', detailCachedAt.value],
    ['Очередь enrichment', formatEnrichmentState(selectedCurrentEnrichmentState.value)],
    ['Следующий скан источника', formatSourceSyncWindow(selectedSourceSyncStatus.value)],
    ['Ошибка источника', selectedSourceSyncStatus.value?.last_sync_error],
  ]),
)
const ratingReasonItems = computed(() => selectedLot.value?.ratingReasons ?? [])
const ratingBreakdown = computed(() => selectedLot.value?.ratingBreakdown ?? null)
const changeFields = computed(() =>
  (selectedWorkspace.value?.changes.fields ?? []).slice(0, DETAIL_RENDER_CHANGE_FIELDS_LIMIT).map((field) => ({
    ...field,
    previous: field.previous ? truncateDetailText(field.previous) : field.previous,
    current: field.current ? truncateDetailText(field.current) : field.current,
  })),
)
const changeSummaryFields = computed(() =>
  makeFields([
    ['Наблюдений списка', selectedWorkspace.value?.changes.observations_count?.toString()],
    ['Наблюдений деталей', selectedWorkspace.value?.changes.detail_observations_count?.toString()],
    ['Последнее наблюдение', formatDateTime(selectedWorkspace.value?.changes.last_observed_at ?? null)],
    ['Предыдущее наблюдение', formatDateTime(selectedWorkspace.value?.changes.previous_observed_at ?? null)],
    ['Последние live-детали', formatDateTime(selectedWorkspace.value?.changes.last_detail_observed_at ?? null)],
    ['Предыдущие live-детали', formatDateTime(selectedWorkspace.value?.changes.previous_detail_observed_at ?? null)],
    ['Изменение статуса', formatDateTime(selectedWorkspace.value?.changes.status_changed_at ?? null)],
  ]),
)
const detailDocuments = computed(() =>
  uniqueDocuments([...(selectedLotDetails.value?.documents ?? []), ...(selectedAuctionDetails.value?.documents ?? [])]),
)
const detailImages = computed<DetailImage[]>(() => {
  const primaryImage = selectedLot.value?.primaryImageUrl
    ? [
        {
          url: selectedLot.value.primaryImageUrl,
          thumbnail_url: selectedLot.value.primaryImageUrl,
          alt: selectedLot.value.lotName,
          source: selectedLot.value.source,
        },
      ]
    : []
  const selectedRowImages = [...(selectedLot.value?.images ?? []), ...primaryImage]
  const liveDetailImages = liveLot.value?.images ?? []
  const documentImages = detailDocuments.value
    .filter((document) => belongsToSelectedLotMedia(document) && isImageDocument(document) && document.url)
    .map((document) => ({ url: document.url || '', thumbnailUrl: document.url || '', name: document.name }))
  const fallbackImages = [...liveDetailImages, ...selectedRowImages]
  const images = documentImages.length ? documentImages : fallbackImages
  return uniqueDetailImages(images).filter((image) => isRelevantDetailImage(image.url) && !isLockedTbankrotImageUrl(image.url))
})
const lockedTbankrotImageCount = computed(() => {
  const images = uniqueDetailImages([...(selectedLot.value?.images ?? []), ...(liveLot.value?.images ?? [])])
  return images.filter((image) => isLockedTbankrotImageUrl(image.url)).length
})
const mediaDocuments = computed(() =>
  detailDocuments.value.filter((document) => {
    const text = [document.name, document.document_type, document.comment].filter(Boolean).join(' ')
    return (
      belongsToSelectedLotMedia(document) &&
      !isImageDocument(document) &&
      (/фото|photo|изображ/i.test(text) || /\.(rar|zip|7z)(\?|$)/i.test(document.url || document.name || ''))
    )
  }),
)
const fileDocuments = computed(() => detailDocuments.value.filter((document) => !isImageDocument(document)))
const activeDetailImage = computed(() => detailImages.value[activeDetailImageIndex.value] ?? detailImages.value[0] ?? null)

watch(detailImages, (images) => {
  if (activeDetailImageIndex.value >= images.length) {
    activeDetailImageIndex.value = 0
  }
})

watch(() => selectedLot.value?.id, () => {
  activeDetailImageIndex.value = 0
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

function makeFields(entries: Array<[string, unknown]>): DetailField[] {
  return entries
    .map(([label, value]) => ({ label, value: truncateDetailText(normalizeTextValue(value)) }))
    .filter((field) => field.value && field.value !== 'Не задано')
}

function normalizeTextValue(value: unknown) {
  if (value === null || value === undefined) return ''
  if (value instanceof Date) return formatDateTime(value)
  return String(value).trim()
}

function normalizeRawFields(fields: ApiField[]): DetailField[] {
  const seen = new Set<string>()
  return fields
    .slice(0, DETAIL_RENDER_RAW_FIELDS_LIMIT)
    .map((field) => ({
      label: field.name.trim(),
      value: truncateDetailText(field.value.trim()),
    }))
    .filter((field) => {
      if (!field.label || !field.value) return false
      if (/^\d+$/.test(field.label)) return false
      if (field.label === '---' || field.label === '№') return false

      const key = `${field.label}\n${field.value}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

function uniqueDocuments(documents: ApiDocument[]) {
  const seen = new Set<string>()
  return documents.slice(0, DETAIL_RENDER_DOCUMENTS_LIMIT).filter((document) => {
    const key = document.external_id || document.url || `${document.name || ''}\n${document.received_at || ''}`
    if (!key.trim() || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function uniqueDetailImages(images: Array<ApiLotImage | DetailImage>): DetailImage[] {
  const seen = new Set<string>()
  return images
    .slice(0, DETAIL_RENDER_IMAGES_LIMIT)
    .map((image) => {
      const url = image.url
      const thumbnailUrl = 'thumbnailUrl' in image ? image.thumbnailUrl : image.thumbnail_url || image.url
      const name = 'name' in image ? image.name : image.alt
      return { url, thumbnailUrl, name }
    })
    .filter((image) => {
      if (!image.url || seen.has(image.url)) return false
      seen.add(image.url)
      return true
    })
}

function truncateDetailText(value: string, limit = DETAIL_RENDER_TEXT_LIMIT) {
  return value.length > limit ? `${value.slice(0, limit).trim()}...` : value
}

function isNoPhotoReason(reason: string) {
  return reason.trim().toLowerCase() === 'нет фото'
}

function isLockedTbankrotImageUrl(url: string) {
  return /\/img\/blur\/|\/blur_/i.test(url)
}

function isImageDocument(document: ApiDocument) {
  const documentType = (document.document_type || '').trim().toLowerCase()
  const text = [document.url, document.name, document.comment].filter(Boolean).join(' ')
  return documentType === 'photo' || /фото|photo|изображ/i.test(text) || /\.(png|jpe?g|gif|webp)(\?|$)/i.test(text)
}

function isRelevantDetailImage(url: string) {
  if (selectedLot.value?.source !== 'tbankrot') return true
  return /files\.tbankrot\.ru\//i.test(url) || /webapi\.torgi\.cdtrf\.ru\/doc\/public\/file/i.test(url)
}

function selectDetailImage(index: number) {
  activeDetailImageIndex.value = index
}

function showPreviousDetailImage() {
  if (detailImages.value.length < 2) return
  activeDetailImageIndex.value = (activeDetailImageIndex.value - 1 + detailImages.value.length) % detailImages.value.length
}

function showNextDetailImage() {
  if (detailImages.value.length < 2) return
  activeDetailImageIndex.value = (activeDetailImageIndex.value + 1) % detailImages.value.length
}

function belongsToSelectedLotMedia(document: ApiDocument) {
  const lotNumber = selectedLot.value?.lotNumber
  if (!lotNumber) return true

  const text = [document.name, document.document_type, document.comment].filter(Boolean).join(' ').toLowerCase()
  const explicitLotMatch = text.match(/(?:лот|lot)\s*0*(\d+)/i)
  return !explicitLotMatch || explicitLotMatch[1] === lotNumber.replace(/^0+/, '')
}

function clampDetailPaneWidth(value: number) {
  return Math.min(DETAIL_PANE_MAX_WIDTH, Math.max(DETAIL_PANE_MIN_WIDTH, value))
}

function readStoredDetailPaneWidth() {
  const stored = window.localStorage.getItem(DETAIL_PANE_WIDTH_STORAGE_KEY)
  const parsed = stored ? Number(stored) : DETAIL_PANE_DEFAULT_WIDTH
  return Number.isFinite(parsed) ? clampDetailPaneWidth(parsed) : DETAIL_PANE_DEFAULT_WIDTH
}

function saveDetailPaneWidth() {
  window.localStorage.setItem(DETAIL_PANE_WIDTH_STORAGE_KEY, String(Math.round(detailPaneWidth.value)))
}

function isDatasetPeriod(value: unknown): value is DatasetPeriod {
  return value === 'week' || value === 'month' || value === 'year'
}

function sanitizeServerFilters(value: Partial<ServerQuickFiltersState> | null | undefined): ServerQuickFiltersState {
  const hasPeriod = isDatasetPeriod(value?.period)
  const period: DatasetPeriod = hasPeriod ? (value.period as DatasetPeriod) : DEFAULT_SERVER_FILTERS.period
  const source = hasPeriod && typeof value?.source === 'string' && value.source.trim() === 'tbankrot' ? 'tbankrot' : DEFAULT_SERVER_FILTERS.source
  const analysisColor = typeof value?.analysisColor === 'string' ? value.analysisColor : DEFAULT_SERVER_FILTERS.analysisColor
  const status = typeof value?.status === 'string' ? value.status : DEFAULT_SERVER_FILTERS.status
  const minPrice = typeof value?.minPrice === 'string' ? value.minPrice : DEFAULT_SERVER_FILTERS.minPrice
  const maxPrice = typeof value?.maxPrice === 'string' ? value.maxPrice : DEFAULT_SERVER_FILTERS.maxPrice
  const onlyNew = value?.onlyNew === true
  const shortlist = value?.shortlist === true
  const minRating = Number.isFinite(value?.minRating)
    ? Math.min(100, Math.max(0, Number(value?.minRating)))
    : DEFAULT_SERVER_FILTERS.minRating
  const includeArchived = value?.includeArchived === true

  return {
    period,
    source,
    analysisColor,
    status,
    minPrice,
    maxPrice,
    onlyNew,
    shortlist,
    minRating,
    includeArchived,
  }
}

function readStoredServerFilters(): ServerQuickFiltersState {
  const stored = window.localStorage.getItem(SERVER_FILTERS_STORAGE_KEY)
  if (!stored) return { ...DEFAULT_SERVER_FILTERS }

  try {
    return sanitizeServerFilters(JSON.parse(stored) as Partial<ServerQuickFiltersState>)
  } catch {
    return { ...DEFAULT_SERVER_FILTERS }
  }
}

function persistServerFilters() {
  window.localStorage.setItem(SERVER_FILTERS_STORAGE_KEY, JSON.stringify(sanitizeServerFilters(filters)))
}

function sanitizeGridColumnWidths(value: unknown): GridColumnWidthsState {
  if (!value || typeof value !== 'object') return {}

  const widths: GridColumnWidthsState = {}
  for (const [key, width] of Object.entries(value as Record<string, unknown>)) {
    if (!key.trim()) continue
    widths[key] = Number.isFinite(width) ? Math.max(0, Math.trunc(width as number)) : null
  }
  return widths
}

function readStoredGridColumnWidths(): GridColumnWidthsState {
  const stored = window.localStorage.getItem(GRID_COLUMN_WIDTHS_STORAGE_KEY)
  if (!stored) return {}

  try {
    return sanitizeGridColumnWidths(JSON.parse(stored))
  } catch {
    return {}
  }
}

function setGridColumnWidths(widths: unknown, options: { persist?: boolean } = {}) {
  const nextWidths = sanitizeGridColumnWidths(widths)
  gridColumnWidths.value = nextWidths
  if (options.persist !== false) {
    window.localStorage.setItem(GRID_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(nextWidths))
  }
  return nextWidths
}

function sanitizeGridSavedView<TRow extends Record<string, unknown>>(
  savedView: DataGridSavedViewSnapshot<TRow>,
  options: { dropSort?: boolean } = {},
): DataGridSavedViewSnapshot<TRow> {
  const rowSnapshot = savedView.state.rows.snapshot
  const rowCount = Math.max(0, rowSnapshot.rowCount)

  return {
    ...savedView,
    state: {
      ...savedView.state,
      rows: {
        ...savedView.state.rows,
        snapshot: {
          ...rowSnapshot,
          sortModel: options.dropSort ? [] : rowSnapshot.sortModel,
          pagination: {
            ...rowSnapshot.pagination,
            enabled: false,
            pageSize: 0,
            currentPage: 0,
            pageCount: rowCount > 0 ? 1 : 0,
            totalRowCount: rowCount,
            startIndex: rowCount > 0 ? 0 : -1,
            endIndex: rowCount > 0 ? rowCount - 1 : -1,
          },
        },
      },
    },
  }
}

function resolveViewportRangeSize(range?: { start: number; end: number } | null) {
  return range && Number.isFinite(range.start) && Number.isFinite(range.end) ? Math.trunc(range.end - range.start + 1) : 0
}

function resolveCatalogServerViewportSize(preferredRange?: { start: number; end: number } | null) {
  const range = preferredRange ?? catalogRowModel.value?.getSnapshot().viewportRange
  const size = resolveViewportRangeSize(range)
  if (size > 1) {
    return Math.min(CATALOG_SERVER_FETCH_LIMIT, Math.max(SERVER_ROW_MODEL_INITIAL_FETCH_SIZE, size))
  }
  return SERVER_ROW_MODEL_INITIAL_FETCH_SIZE
}

function ensureCatalogServerViewport(preferredRange?: { start: number; end: number } | null) {
  const size = resolveCatalogServerViewportSize(preferredRange)
  const rowModel = catalogRowModel.value
  if (!rowModel) return false

  const nextRange = { start: 0, end: size - 1 }
  const currentSnapshot = rowModel.getSnapshot()
  const currentRange = currentSnapshot.viewportRange
  rowModel.setViewportRange(nextRange)
  const appliedRange = rowModel.getSnapshot().viewportRange
  return currentRange.start !== appliedRange.start || currentRange.end !== appliedRange.end
}

function buildCatalogServerViewportRange(preferredRange?: { start: number; end: number } | null) {
  const size = resolveCatalogServerViewportSize(preferredRange)
  return { start: 0, end: size - 1 }
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

function authHeaders() {
  if (!accessToken.value) {
    return new Headers()
  }

  return new Headers({
    Authorization: `Bearer ${accessToken.value}`,
  })
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

function apiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

function hasGridFilterModel(filterModel: DataGridFilterSnapshot | null | undefined) {
  if (!filterModel) return false
  const quickFilter = (filterModel as { quickFilter?: { query?: unknown } }).quickFilter
  return (
    hasMeaningfulColumnFilters(filterModel.columnFilters) ||
    hasMeaningfulAdvancedFilters(filterModel.advancedFilters) ||
    hasMeaningfulAdvancedExpression(filterModel.advancedExpression) ||
    (typeof quickFilter?.query === 'string' && quickFilter.query.trim().length > 0)
  )
}

function hasMeaningfulColumnFilters(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false

  for (const payload of Object.values(value as Record<string, unknown>)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const filter = payload as Record<string, unknown>
    if (filter.kind === 'valueSet') {
      const tokens = filter.tokens
      if (Array.isArray(tokens) && tokens.length > 0) return true
      continue
    }
    if (filter.kind === 'predicate') {
      if (isMeaningfulAdvancedClause(filter)) return true
    }
  }
  return false
}

function hasMeaningfulAdvancedFilters(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false

  for (const payload of Object.values(value as Record<string, unknown>)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const clauses = (payload as { clauses?: unknown }).clauses
    if (Array.isArray(clauses) && clauses.some(isMeaningfulAdvancedClause)) return true
  }
  return false
}

function isMeaningfulAdvancedClause(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const clause = value as Record<string, unknown>
  const operator = typeof clause.operator === 'string' ? clause.operator.trim() : ''
  if (!operator) return false
  if (['isNull', 'notNull', 'is-null', 'not-null', 'isEmpty', 'notEmpty', 'is-empty', 'not-empty'].includes(operator)) {
    return true
  }
  const clauseValue = clause.value
  return clauseValue !== null && clauseValue !== undefined && String(clauseValue).trim().length > 0
}

function hasMeaningfulAdvancedExpression(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false

  const expression = value as Record<string, unknown>
  if (expression.kind === 'condition') {
    return isMeaningfulAdvancedClause(expression)
  }
  if (expression.kind === 'group') {
    return Array.isArray(expression.children) && expression.children.some(hasMeaningfulAdvancedExpression)
  }
  if (expression.kind === 'not') {
    return hasMeaningfulAdvancedExpression(expression.child)
  }
  return false
}

function isAbortLikeError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

function isApiRequestStatus(error: unknown, status: number) {
  return error instanceof ApiRequestError && error.status === status
}

function buildAuctionServerGridFilters(): AuctionServerGridFilters {
  return {
    period: filters.period,
    source: null,
    status: null,
    analysis_color: null,
    min_price: null,
    max_price: null,
    only_new: false,
    shortlist: false,
    min_rating: null,
    include_archived: filters.includeArchived,
  }
}

function buildCatalogFilterModel(): DataGridFilterSnapshot | null {
  const conditions: Record<string, unknown>[] = []
  const minPrice = parseFilterNumber(filters.minPrice)
  const maxPrice = parseFilterNumber(filters.maxPrice)

  if (filters.source && filters.source !== 'all') {
    conditions.push({ kind: 'condition', key: 'source', operator: 'equals', value: filters.source })
  }
  if (filters.status) {
    conditions.push({ kind: 'condition', key: 'status', operator: 'equals', value: filters.status })
  }
  if (filters.analysisColor) {
    conditions.push({ kind: 'condition', key: 'analysisColor', operator: 'equals', value: filters.analysisColor })
  }
  if (minPrice !== null) {
    conditions.push({ kind: 'condition', key: 'price', operator: 'gte', value: minPrice })
  }
  if (maxPrice !== null) {
    conditions.push({ kind: 'condition', key: 'price', operator: 'lte', value: maxPrice })
  }
  if (filters.onlyNew) {
    conditions.push({ kind: 'condition', key: 'isNew', operator: 'equals', value: true })
  }
  if (filters.shortlist) {
    conditions.push({ kind: 'condition', key: '__shortlist', operator: 'equals', value: true })
  }
  if (filters.minRating > 0) {
    conditions.push({ kind: 'condition', key: 'ratingScore', operator: 'gte', value: filters.minRating })
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

function serializeCatalogFilterModel() {
  return JSON.stringify(buildCatalogFilterModel())
}

function serializeCatalogQueryScope() {
  return JSON.stringify({
    period: filters.period,
    includeArchived: filters.includeArchived,
  })
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
  const nextFilterSignature = serializeCatalogFilterModel()
  const nextQueryScopeSignature = serializeCatalogQueryScope()
  const filterChanged = nextFilterSignature !== catalogFilterSyncSignature
  const queryScopeChanged = nextQueryScopeSignature !== catalogQueryScopeSyncSignature
  if (!filterChanged && !queryScopeChanged) return
  catalogFilterSyncSignature = nextFilterSignature
  catalogQueryScopeSyncSignature = nextQueryScopeSignature
  if (filterChanged) {
    rowModel.setFilterModel(buildCatalogFilterModel())
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
    getFilters: buildAuctionServerGridFilters,
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
        const effectiveFilterModel = resolveCatalogPullFilterModel(request.filterModel, request.reason)
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

function resolveCatalogPullFilterModel(filterModel: DataGridFilterSnapshot | null | undefined, reason: string) {
  if (hasGridFilterModel(filterModel)) return filterModel ?? null
  if (reason === 'filter-change') return filterModel ?? null

  const snapshotFilterModel = catalogRowModel.value?.getSnapshot().filterModel ?? null
  return hasGridFilterModel(snapshotFilterModel) ? snapshotFilterModel : filterModel ?? null
}

function createCatalogRowModel(): CatalogRowModel {
  const rowModel = createDataSourceBackedRowModel({
    dataSource: createCatalogDataSource(),
    resolveRowId: resolveClientGridRowId,
    initialTotal: Math.min(CATALOG_TOTAL_ROW_LIMIT, Math.max(catalogTotal.value || 0, SERVER_ROW_MODEL_INITIAL_FETCH_SIZE)),
    initialFilterModel: buildCatalogFilterModel(),
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
  const size = resolveCatalogServerViewportSize(viewportRange)
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
  catalogFilterSyncSignature = serializeCatalogFilterModel()
  catalogQueryScopeSyncSignature = serializeCatalogQueryScope()
}

async function loadLots() {
  if (!isAuctionsModule.value || !isAuthenticated.value) return
  resetCatalogRowModel()
  savedGridWorkSnapshots.clear()
  await nextTick()
  ensureCatalogServerViewport({ start: 0, end: SERVER_ROW_MODEL_INITIAL_FETCH_SIZE - 1 })
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
    exclusionReason: row.exclusionReason.trim(),
  }
}

function serializeGridWorkState(row: GridLotRow) {
  return JSON.stringify(snapshotGridWorkState(row))
}

function rememberGridWorkSnapshot(row: GridLotRow) {
  savedGridWorkSnapshots.set(row.id, serializeGridWorkState(row))
}

function parseNumber(value: string | number | null) {
  if (value === null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function parseDateTime(value: string | null) {
  if (!value) return null
  const normalized = value.trim()
  const russianDateTime = normalized.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?/)
  if (russianDateTime) {
    const [, day, month, year, hour = '0', minute = '0', second = '0'] = russianDateTime
    return new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second))
  }

  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDateTime(value: Date | string | null) {
  if (!value) return ''
  if (value instanceof Date) return value.toLocaleString('ru-RU')

  const date = parseDateTime(value)
  return date ? date.toLocaleString('ru-RU') : value
}

function formatLifecycleStatus(value: string | null | undefined) {
  const status = (value || '').trim().toLowerCase()
  if (!status) return 'Неизвестно'
  if (status === 'active') return 'Активен'
  if (status === 'expired') return 'Истек'
  if (status === 'stale') return 'Устарел'
  if (status === 'archived') return 'Архив'
  return value || 'Неизвестно'
}

function lifecycleStatusTone(value: string | null | undefined) {
  const status = (value || '').trim().toLowerCase()
  if (status === 'active') return 'active'
  if (status === 'expired') return 'warning'
  if (status === 'stale') return 'warning'
  if (status === 'archived') return 'muted'
  return 'muted'
}

function buildLifecycleStatusTooltip(row: GridLotRow) {
  const details = [
    `Последнее наблюдение: ${formatDateTime(row.lastSeenAt) || 'нет данных'}`,
    `Проверка актуальности: ${formatDateTime(row.actualityCheckedAt) || 'нет данных'}`,
  ]
  return details.join('\n')
}

function formatEnrichmentState(state: LotWorkspaceEnrichmentState | null | undefined) {
  if (!state) return 'Не запрошено'
  if (state.claimed_at) {
    return `В работе${state.claimed_by ? ` · ${state.claimed_by}` : ''}`
  }
  if (state.requested_at) {
    return state.next_attempt_at ? `В очереди до ${formatDateTime(state.next_attempt_at)}` : 'В очереди'
  }
  return 'Не запрошено'
}

function formatSourceSyncWindow(source: AuctionPipelineSourceSyncStatus | null | undefined) {
  if (!source) return 'Нет данных'
  if (!source.next_sync_not_before && !source.next_sync_not_after) return 'Не запланировано'
  const windowStart = formatDateTime(source.next_sync_not_before)
  const windowEnd = formatDateTime(source.next_sync_not_after)
  if (windowStart && windowEnd) return `${windowStart} - ${windowEnd}`
  return windowStart || windowEnd || 'Не запланировано'
}

function formatCurrency(value: number | null) {
  if (value === null || Number.isNaN(value)) return 'Не указана'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    currencyDisplay: 'symbol',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatApiMoney(value: string | number | null | undefined) {
  const parsed = parseNumber(value ?? null)
  return parsed === null ? '' : formatCurrency(parsed)
}

function formatApiPercent(value: string | number | null | undefined) {
  const parsed = parseNumber(value ?? null)
  if (parsed === null) return ''
  return new Intl.NumberFormat('ru-RU', {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(parsed)
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

function formatDecisionLevel(value: DecisionLevel) {
  return {
    ignore: 'Игнорировать',
    watch: 'Наблюдать',
    inspect: 'Осмотреть',
    calculate: 'Посчитать',
    bid_candidate: 'Кандидат на торги',
  }[value]
}

function formatActionRecommendation(value: ActionRecommendation) {
  return {
    ignore: 'Игнорировать',
    monitor: 'Мониторить',
    request_docs: 'Запросить документы',
    inspect: 'Осмотреть лот',
    calculate_max_bid: 'Посчитать максимум',
    prepare_bid: 'Готовить заявку',
  }[value]
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resolvedUrl = apiUrl(url)
  const startedAt = performance.now()
  let response: Response
  try {
    response = await fetch(resolvedUrl, {
      ...init,
      headers: new Headers({
        ...Object.fromEntries(authHeaders().entries()),
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
    throw new ApiRequestError(`API вернул ${response.status}`, response.status, body)
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
    presets.value = sortPresets(await fetchJson<FilterPreset[]>('/api/v1/filter-presets'))
    if (selectedPresetId.value && !presets.value.some((preset) => preset.id === selectedPresetId.value)) {
      selectedPresetId.value = ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить подборки'
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
    filters: sanitizeServerFilters(filters),
    grid_view: gridRef.value?.getSavedView() ?? null,
    is_favorite: selectedPreset.value?.is_favorite ?? false,
  }
}

function buildInterestProfilePayloadFromFilters(name: string) {
  const profilePayload: LotScoringProfilePayload = {
    profile_identifier: null,
    target_regions: [],
    target_categories: selectedLot.value?.analysisCategory ? [selectedLot.value.analysisCategory] : [],
    budget_min: parseFilterNumber(filters.minPrice),
    budget_max: parseFilterNumber(filters.maxPrice),
    allowed_legal_risks: ['low', 'medium'],
    desired_keywords: splitInterestProfileTerms(filters.status),
    stop_words: [],
    strategy: 'balanced',
  }

  return {
    name: name.trim(),
    profile_payload: profilePayload,
    min_rating: Math.max(0, Math.min(100, Number(interestProfileDraft.minRating) || 0)),
    notification_priority_threshold: 'medium' as const,
    telegram_enabled: interestProfileDraft.telegramEnabled,
    is_active: interestProfileDraft.isActive,
  }
}

async function applyPresetById(presetId: string) {
  selectedPresetId.value = presetId
  const preset = presets.value.find((item) => item.id === presetId)
  if (!preset) return

  const nextFilters = sanitizeServerFilters(preset.filters)
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

function setPresetDialogInitialRef(element: Element | ComponentPublicInstance | null) {
  presetDialogInitialRef.value = element as HTMLElement | null
}

function setInterestProfilesDialogInitialRef(element: Element | ComponentPublicInstance | null) {
  interestProfilesDialogInitialRef.value = element as HTMLElement | null
}

function setAnalysisConfigDialogInitialRef(element: Element | ComponentPublicInstance | null) {
  analysisConfigDialogInitialRef.value = element as HTMLElement | null
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

function splitInterestProfileTerms(value: string) {
  if (!value.trim()) return []
  return splitAnalysisConfigLines(value)
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
  analysisConfigDialogTriggerRef.value = event?.currentTarget as HTMLElement | null
  analysisConfigError.value = ''
  if (analysisConfig.value) {
    applyAnalysisConfigDraft(analysisConfig.value)
  } else {
    resetAnalysisConfigDraft()
  }
  analysisConfigDialog.open('trigger')
  void loadAnalysisConfig()
}

function openInterestProfilesDialog(event?: Event) {
  interestProfilesDialogTriggerRef.value = event?.currentTarget as HTMLElement | null
  interestProfilesError.value = ''
  resetInterestProfileDraft()
  interestProfilesDialog.open('trigger')
  void loadUserInterestProfiles()
}

function toggleMobileRail() {
  mobileRailOpen.value = !mobileRailOpen.value
}

function resetInterestProfileDraft() {
  interestProfileDraft.name = defaultInterestProfileName()
  interestProfileDraft.minRating = filters.minRating > 0 ? filters.minRating : 80
  interestProfileDraft.telegramEnabled = true
  interestProfileDraft.isActive = true
  telegramPresetIdDraft.value = selectedPresetId.value || presets.value[0]?.id || ''
}

function defaultInterestProfileName() {
  const parts = []
  if (selectedLot.value?.analysisCategory) parts.push(selectedLot.value.analysisCategory)
  if (filters.minPrice.trim()) parts.push(`от ${filters.minPrice.trim()}`)
  if (filters.maxPrice.trim()) parts.push(`до ${filters.maxPrice.trim()}`)
  if (filters.minRating > 0) parts.push(`рейтинг ${filters.minRating}+`)
  return parts.length ? parts.join(', ') : 'Новый профиль интересов'
}

function interestProfileNote(profile: UserInterestProfile) {
  const payload = profile.profile_payload ?? {}
  const parts = []
  const categories = payload.target_categories ?? []
  const keywords = payload.desired_keywords ?? []
  if (categories.length) parts.push(categories.join(', '))
  if (keywords.length) parts.push(`слова: ${keywords.join(', ')}`)
  if (payload.budget_min || payload.budget_max) {
    parts.push(`бюджет ${payload.budget_min ?? '0'}-${payload.budget_max ?? '∞'}`)
  }
  if (profile.source_filter_preset_id) parts.push('из среза')
  parts.push(`рейтинг ${profile.min_rating}+`)
  return parts.join(' · ')
}

async function createInterestProfileFromCurrentFilters() {
  const name = interestProfileDraft.name.trim()
  if (!name) {
    interestProfilesError.value = 'Название профиля не должно быть пустым'
    return
  }

  interestProfilesSaving.value = true
  interestProfilesError.value = ''
  try {
    const profile = await createUserInterestProfile(buildInterestProfilePayloadFromFilters(name))
    userInterestProfiles.value = sortUserInterestProfiles([...userInterestProfiles.value, profile])
    resetInterestProfileDraft()
  } catch (error) {
    interestProfilesError.value = error instanceof Error ? error.message : 'Не удалось создать профиль интересов'
  } finally {
    interestProfilesSaving.value = false
  }
}

async function createInterestProfileFromSelectedPreset() {
  const preset = presets.value.find((item) => item.id === telegramPresetIdDraft.value)
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
      min_rating: filters.minRating > 0 ? filters.minRating : null,
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

function closeMobileRail() {
  mobileRailOpen.value = false
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
    await analysisConfigDialog.close('programmatic')
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
    errorMessage.value = 'Название подборки не должно быть пустым'
    return
  }

  if (presetDialogMode.value === 'update' && selectedPreset.value) {
    try {
      const preset = await fetchJson<FilterPreset>(`/api/v1/filter-presets/${selectedPreset.value.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPresetPayload(nextName)),
      })
      presets.value = sortPresets(presets.value.map((item) => (item.id === preset.id ? preset : item)))
      selectedPresetId.value = preset.id
      await syncInterestProfilesForPreset(preset.id)
      await presetDialog.close('programmatic')
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : 'Не удалось обновить подборку'
    }
    return
  }

  try {
    const preset = await fetchJson<FilterPreset>('/api/v1/filter-presets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPresetPayload(nextName)),
    })
    presets.value = sortPresets([...presets.value, preset])
    selectedPresetId.value = preset.id
    await presetDialog.close('programmatic')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось сохранить подборку'
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
    await fetchJson(`/api/v1/filter-presets/${selectedPreset.value.id}`, {
      method: 'DELETE',
    })
    presets.value = presets.value.filter((preset) => preset.id !== selectedPreset.value?.id)
    selectedPresetId.value = ''
    await presetDialog.close('programmatic')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось удалить подборку'
  }
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

type MobileInlineEditTarget = {
  rowId: string | number
  rowIndex: number
  columnIndex: number
  columnKey: string
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
  saveDetailPaneWidth()
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (analysisConfigDialog.snapshot.value.isOpen) {
    if (['Escape', 'Esc'].includes(event.key)) {
      event.preventDefault()
      event.stopPropagation()
      void analysisConfigDialog.close('escape-key')
    }
    return
  }
  if (interestProfilesDialog.snapshot.value.isOpen) {
    if (['Escape', 'Esc'].includes(event.key)) {
      event.preventDefault()
      event.stopPropagation()
      void interestProfilesDialog.close('escape-key')
    }
    return
  }
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
  persistServerFilters()
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

        <UiMenu ref="presetsMenuRef" placement="right" align="start" :gutter="10">
          <UiMenuTrigger as-child>
            <button
              class="app-rail__item app-rail__menu-trigger"
              :class="{ 'app-rail__item--active': presetsMenuOpen }"
              type="button"
              aria-haspopup="menu"
            >
              <span class="app-rail__item-icon" aria-hidden="true">≡</span>
              <span class="app-rail__item-label">Срезы</span>
            </button>
          </UiMenuTrigger>

          <UiMenuContent class="app-rail__menu-content app-rail__menu-content--presets">
            <UiMenuLabel>Срезы каталога</UiMenuLabel>
            <UiMenuItem @select="() => applyPresetById('')">
              <span class="app-rail__menu-title">Каталог</span>
              <span class="app-rail__menu-note">Все лоты</span>
            </UiMenuItem>
            <UiMenuSeparator />
            <UiMenuItem
              v-for="preset in presets"
              :key="preset.id"
              @select="() => applyPresetById(preset.id)"
            >
              <span class="app-rail__menu-title">{{ preset.is_favorite ? `${preset.name} *` : preset.name }}</span>
              <span class="app-rail__menu-note">{{ preset.is_favorite ? 'Избранный срез' : 'Сохраненный срез' }}</span>
            </UiMenuItem>
            <UiMenuSeparator />
            <UiMenuItem @select="() => openCreatePresetDialog()">Сохранить</UiMenuItem>
            <UiMenuItem :disabled="!selectedPreset" @select="() => openUpdatePresetDialog()">Обновить</UiMenuItem>
            <UiMenuItem :disabled="!selectedPreset" @select="() => openDeletePresetDialog()">Удалить</UiMenuItem>
          </UiMenuContent>
        </UiMenu>

        <button class="app-rail__item" type="button" @click="openAnalysisConfigDialog">
          <span class="app-rail__item-icon" aria-hidden="true">⚙</span>
          <span class="app-rail__item-label">Анализ</span>
        </button>

        <button class="app-rail__item" type="button" @click="openInterestProfilesDialog">
          <span class="app-rail__item-icon" aria-hidden="true">I</span>
          <span class="app-rail__item-label">Интересы</span>
        </button>

        <div class="app-rail__separator" aria-hidden="true"></div>
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
      <template v-if="isAuctionsModule">
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
          <button
            v-if="mobileInlineEditTarget"
            class="auction-toolbar__edit-button"
            type="button"
            @click="openMobileInlineEdit"
          >
            Редактировать ячейку
          </button>
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
                <RatingInfoTooltip
                  :reasons="ratingReasonItems"
                  :dimensions="ratingBreakdown?.dimensions ?? null"
                  :caps="ratingBreakdown?.caps ?? null"
                />
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

      <SourceDiagnosticsView v-else-if="isDiagnosticsModule" />

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

    <Teleport to="#affino-dialog-host">
      <transition name="dialog-layer">
        <div
          v-if="interestProfilesDialog.snapshot.value.isOpen"
          class="app-dialog-layer"
          @click.self="void interestProfilesDialog.close('backdrop')"
        >
          <div
            ref="interestProfilesDialogRef"
            class="app-dialog app-dialog--wide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="interest-profiles-dialog-title"
            tabindex="-1"
          >
            <header class="app-dialog__header">
              <div>
                <span class="eyebrow">Персональные сигналы</span>
                <h2 id="interest-profiles-dialog-title">Профили интересов</h2>
              </div>
              <button
                class="icon-button"
                type="button"
                aria-label="Закрыть окно"
                @click="void interestProfilesDialog.close('programmatic')"
              >
                ×
              </button>
            </header>

            <div class="app-dialog__body app-dialog__body--scroll">
              <p class="app-dialog__text">
                Профиль интересов управляет тем, какие рейтинговые лоты попадут в персональные Telegram-уведомления.
                Срез таблицы остается только UI-фильтром.
              </p>

              <div v-if="interestProfilesError" class="error-banner">{{ interestProfilesError }}</div>

              <section class="interest-profile-panel interest-profile-panel--telegram" aria-label="Подключить Telegram-бота">
                <div class="interest-profile-panel__header">
                  <div>
                    <h3>Подключить Telegram-бота</h3>
                    <p>
                      Нажмите «Открыть бота» и запустите его по одноразовой ссылке. Бот сам отправит команду
                      подключения, а приложение сохранит Chat ID автоматически.
                    </p>
                    <p v-if="telegramConnectUrl" class="interest-profile-connect-note">
                      Ссылка создана до {{ formatDateTime(telegramConnectExpiresAt) }}.
                    </p>
                  </div>
                  <button
                    class="primary-button"
                    type="button"
                    :disabled="telegramConnectLoading"
                    @click="void connectTelegramBot()"
                  >
                    {{ telegramConnectLoading ? 'Создаем...' : 'Открыть бота' }}
                  </button>
                </div>
              </section>

              <section class="interest-profile-panel" aria-label="Создать профиль из текущих фильтров">
                <div class="interest-profile-panel__header">
                  <div>
                    <h3>Создать из текущих фильтров</h3>
                    <p>{{ interestProfileSummary }}</p>
                  </div>
                  <button
                    class="secondary-button"
                    type="button"
                    :disabled="interestProfilesSaving"
                    @click="resetInterestProfileDraft"
                  >
                    Обновить черновик
                  </button>
                </div>

                <div class="app-dialog__grid">
                  <label class="app-dialog__field">
                    <span>Название</span>
                    <input
                      :ref="setInterestProfilesDialogInitialRef"
                      v-model="interestProfileDraft.name"
                      type="text"
                      maxlength="160"
                      placeholder="Например, BMW от 2 млн"
                    />
                  </label>
                  <label class="app-dialog__field">
                    <span>Минимальный рейтинг</span>
                    <input v-model.number="interestProfileDraft.minRating" type="number" min="0" max="100" />
                  </label>
                  <label class="app-dialog__check">
                    <input v-model="interestProfileDraft.telegramEnabled" type="checkbox" />
                    <span>Telegram включен</span>
                  </label>
                  <label class="app-dialog__check">
                    <input v-model="interestProfileDraft.isActive" type="checkbox" />
                    <span>Профиль активен</span>
                  </label>
                </div>

                <button
                  class="primary-button"
                  type="button"
                  :disabled="interestProfilesSaving"
                  @click="void createInterestProfileFromCurrentFilters()"
                >
                  Создать профиль
                </button>
              </section>

              <section class="interest-profile-panel" aria-label="Подключить сохраненный срез к Telegram">
                <div class="interest-profile-panel__header">
                  <div>
                    <h3>Подключить срез к Telegram</h3>
                    <p>Выберите сохраненный срез. Backend превратит его фильтры в профиль интересов.</p>
                  </div>
                  <button
                    class="secondary-button"
                    type="button"
                    :disabled="presetsLoading"
                    @click="void loadPresets()"
                  >
                    Обновить срезы
                  </button>
                </div>

                <div class="interest-profile-preset-row">
                  <label class="app-dialog__field">
                    <span>Срез для Telegram</span>
                    <select v-model="telegramPresetIdDraft" :disabled="!presets.length || interestProfilesSaving">
                      <option value="">Выберите срез</option>
                      <option v-for="preset in presets" :key="preset.id" :value="preset.id">
                        {{ preset.name }}
                      </option>
                    </select>
                  </label>
                  <button
                    class="primary-button"
                    type="button"
                    :disabled="!telegramPresetIdDraft || interestProfilesSaving"
                    @click="void createInterestProfileFromSelectedPreset()"
                  >
                    Подключить
                  </button>
                </div>
              </section>

              <section class="interest-profile-list" aria-label="Список профилей интересов">
                <div v-if="interestProfilesLoading" class="app-dialog__text">Загружаем профили...</div>
                <article v-else-if="!userInterestProfiles.length" class="interest-profile-card interest-profile-card--empty">
                  <h3>Профилей пока нет</h3>
                  <p>Создайте первый профиль из текущих фильтров каталога.</p>
                </article>
                <template v-else>
                  <article
                    v-for="profile in userInterestProfiles"
                    :key="profile.id"
                    class="interest-profile-card"
                  >
                    <div>
                      <h3>{{ profile.name }}</h3>
                      <p>{{ interestProfileNote(profile) }}</p>
                    </div>
                    <div class="interest-profile-card__actions">
                      <button class="secondary-button" type="button" @click="void toggleInterestProfileActive(profile)">
                        {{ profile.is_active ? 'Отключить' : 'Включить' }}
                      </button>
                      <button class="secondary-button" type="button" @click="void toggleInterestProfileTelegram(profile)">
                        {{ profile.telegram_enabled ? 'Telegram вкл.' : 'Telegram выкл.' }}
                      </button>
                      <button
                        class="secondary-button"
                        type="button"
                        :disabled="!profile.source_filter_preset_id"
                        @click="void refreshInterestProfileFromPreset(profile)"
                      >
                        Обновить из среза
                      </button>
                      <button class="secondary-button secondary-button--danger" type="button" @click="void removeInterestProfile(profile)">
                        Удалить
                      </button>
                    </div>
                  </article>
                </template>
              </section>
            </div>

            <footer class="app-dialog__footer">
              <button class="secondary-button" type="button" @click="void interestProfilesDialog.close('programmatic')">
                Закрыть
              </button>
            </footer>
          </div>
        </div>
      </transition>
    </Teleport>

    <Teleport to="#affino-dialog-host">
      <transition name="dialog-layer">
        <div
          v-if="analysisConfigDialog.snapshot.value.isOpen"
          class="app-dialog-layer"
          @click.self="void analysisConfigDialog.close('backdrop')"
        >
          <div
            ref="analysisConfigDialogRef"
            class="app-dialog app-dialog--wide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="analysis-config-dialog-title"
            tabindex="-1"
          >
            <header class="app-dialog__header">
              <div>
                <span class="eyebrow">Анализ</span>
                <h2 id="analysis-config-dialog-title">Правила категорий и риска</h2>
              </div>
              <button
                :ref="analysisConfigLoading ? setAnalysisConfigDialogInitialRef : undefined"
                class="icon-button"
                type="button"
                aria-label="Закрыть окно"
                @click="void analysisConfigDialog.close('programmatic')"
              >
                ×
              </button>
            </header>

            <div class="app-dialog__body app-dialog__body--scroll">
              <p class="app-dialog__text">
                Здесь редактируются категории, исключения и правила юридического риска без изменения backend-кода.
              </p>
              <p v-if="analysisConfigUpdatedAt" class="app-dialog__meta">Последнее обновление: {{ analysisConfigUpdatedAt }}</p>
              <p v-if="analysisConfigError" class="error-banner error-banner--inline">{{ analysisConfigError }}</p>

              <div v-if="analysisConfigLoading" class="detail-muted">Загружаю актуальный конфиг анализа</div>
              <template v-else>
                <section class="analysis-config-section">
                  <div class="analysis-config-section__header">
                    <div>
                      <span class="eyebrow">Категории</span>
                      <p class="analysis-config-section__hint">Порядок важен: категория назначается по первому совпавшему правилу.</p>
                    </div>
                    <button class="secondary-button" type="button" @click="addAnalysisConfigCategoryRule">Добавить категорию</button>
                  </div>

                  <div v-if="analysisConfigDraft.categoryRules.length" class="analysis-config-editor">
                    <article
                      v-for="(rule, index) in analysisConfigDraft.categoryRules"
                      :key="rule.id"
                      class="analysis-config-rule"
                    >
                      <div class="analysis-config-rule__row">
                        <label class="app-dialog__field">
                          <span>Категория</span>
                          <input
                            :ref="index === 0 ? setAnalysisConfigDialogInitialRef : undefined"
                            v-model="rule.category"
                            type="text"
                            maxlength="160"
                            placeholder="Например, Спецтехника"
                          />
                        </label>
                        <button
                          class="icon-button analysis-config-rule__remove"
                          type="button"
                          aria-label="Удалить категорию"
                          @click="removeAnalysisConfigCategoryRule(rule.id)"
                        >
                          ×
                        </button>
                      </div>
                      <label class="app-dialog__field">
                        <span>Ключевые слова</span>
                        <textarea
                          v-model="rule.keywordsText"
                          rows="5"
                          placeholder="Одно ключевое слово или фраза на строку"
                        ></textarea>
                      </label>
                    </article>
                  </div>
                  <div v-else class="detail-muted">Категории пока не заданы. Добавь хотя бы одно правило.</div>
                </section>

                <section class="analysis-config-section analysis-config-section--grid">
                  <label class="app-dialog__field">
                    <span>Исключения</span>
                    <textarea
                      :ref="analysisConfigDraft.categoryRules.length === 0 ? setAnalysisConfigDialogInitialRef : undefined"
                      v-model="analysisConfigDraft.exclusionKeywordsText"
                      rows="7"
                      placeholder="Слова или фразы, по которым лот исключается из анализа"
                    ></textarea>
                  </label>
                  <label class="app-dialog__field">
                    <span>Высокий юридический риск</span>
                    <textarea
                      v-model="analysisConfigDraft.highRiskKeywordsText"
                      rows="7"
                      placeholder="Маркер высокого риска, одно значение на строку"
                    ></textarea>
                  </label>
                  <label class="app-dialog__field">
                    <span>Средний юридический риск</span>
                    <textarea
                      v-model="analysisConfigDraft.mediumRiskKeywordsText"
                      rows="7"
                      placeholder="Маркер среднего риска, одно значение на строку"
                    ></textarea>
                  </label>
                  <label class="app-dialog__field">
                    <span>Категории среднего риска</span>
                    <textarea
                      v-model="analysisConfigDraft.mediumRiskCategoriesText"
                      rows="7"
                      placeholder="Например, Земля и базы"
                    ></textarea>
                  </label>
                </section>
              </template>
            </div>

            <footer class="app-dialog__footer">
              <button class="secondary-button" type="button" @click="void analysisConfigDialog.close('programmatic')">Отмена</button>
              <button class="primary-button" type="button" :disabled="analysisConfigLoading || analysisConfigSaving" @click="void submitAnalysisConfigDialog()">
                {{ analysisConfigSaving ? 'Сохраняю' : 'Сохранить конфиг' }}
              </button>
            </footer>
          </div>
        </div>
      </transition>
    </Teleport>
  </main>
</template>
