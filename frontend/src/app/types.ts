import type { DataGridDataSource, DataGridDataSourceRowEntry, DataGridFilterSnapshot, DataGridSortState } from '@affino/datagrid-vue'
import type { DataSourceBackedRowModel } from '@affino/datagrid-vue'
import type { DataGridExposed } from '@affino/datagrid-vue-app'
import type { AuctionServerDatasource } from '@/datagrid/auctionServerDatasource'
import type { LotDecisionReport } from '@/types/decisionReport'

export type ApiColumn = {
  key: string
  title: string
  data_type: string
  width: number | null
}

export type ApiSource = {
  code: string
  title: string
  website: string
  enabled: boolean
}

export type AuctionPipelineSourceSyncStatus = {
  code: string
  title: string
  enabled: boolean
  last_sync_started_at: string | null
  last_sync_completed_at: string | null
  next_sync_not_before: string | null
  next_sync_not_after: string | null
  last_sync_error: string | null
}

export type ProcurementAttractiveness = {
  score: number
  level: string
  reasons: string[]
}

export type ProcurementLot = {
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

export type ProcurementLotListResponse = {
  items: ProcurementLot[]
  total: number
  page: number
  page_size: number
}

export type AuctionPipelineHealthResponse = {
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

export type ApiLotImage = {
  url: string
  thumbnail_url: string | null
  alt: string | null
  source: string | null
}

export type DetailImage = {
  url: string
  thumbnailUrl: string
  name: string | null
}

export type ApiPriceScheduleStep = {
  starts_at: string
  price: string
}

export type ApiLotRow = {
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

export type ApiDocument = {
  external_id: string | null
  received_at: string | null
  name: string | null
  url: string | null
  signature_status: string | null
  comment: string | null
  document_type: string | null
}

export type ApiField = {
  name: string
  value: string
}

export type ApiOrganizer = {
  name: string | null
  inn: string | null
  website: string | null
  contact_name: string | null
  phone: string | null
  fax: string | null
}

export type ApiDebtor = {
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

export type ApiAuctionSummary = {
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

export type ApiLotSummary = {
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

export type LotDetailResponse = {
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

export type LotWorkItem = {
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

export type LotEconomy = {
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

export type LotFieldChange = {
  label: string
  previous: string | null
  current: string | null
  change_type: string
}

export type LotChangeSummary = {
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

export type LotWorkspaceResponse = {
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

export type LotWorkspaceEnrichmentState = {
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

export type LotWorkspaceRefreshResponse = {
  status: 'queued' | 'rate_limited' | 'already_pending'
  queued: boolean
  next_allowed_at: string | null
  current_enrichment_state: LotWorkspaceEnrichmentState
}

export type AuctionDetailResponse = {
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

export type DetailField = {
  label: string
  value: string
}

export type WorkDraft = {
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

export type LotsResponse = {
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

export type CatalogColumnHistogramRequest = Parameters<NonNullable<DataGridDataSource<GridLotRow>['getColumnHistogram']>>[0]

export type LotHistogramPayload = {
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

export type GridChangeFeedResponse = {
  datasetVersion: number
  changes: Array<{
    type: 'row_updated' | 'row_inserted' | 'row_deleted' | 'invalidation'
    rowId: string | null
    payload: Record<string, unknown>
  }>
  hasMore: boolean
}

export type GridLotRow = {
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

export type RatingDimensionBreakdown = {
  key?: string
  label?: string
  score?: number
  reasons?: string[]
}

export type RatingCapBreakdown = {
  key?: string
  label?: string
  max_score?: number
  reason?: string
}

export type RatingBreakdown = {
  dimensions?: Record<string, RatingDimensionBreakdown>
  caps?: RatingCapBreakdown[]
}

export type GridApi = NonNullable<ReturnType<DataGridExposed<GridLotRow>['getApi']>>
export type GridSelectionSnapshot = ReturnType<GridApi['selection']['getSnapshot']>

export type CatalogDataSource = DataGridDataSource<GridLotRow>
export type CatalogAuctionServerDataSource = AuctionServerDatasource<ApiLotRow, GridLotRow> & {
  applyInvalidation?: (invalidation: unknown, options?: { datasetVersion?: unknown }) => void
}

export type CatalogRowModel = DataSourceBackedRowModel<GridLotRow> & {
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

export type AuctionWorkspaceExposed = {
  getApi: DataGridExposed<GridLotRow>['getApi']
  getRuntime: DataGridExposed<GridLotRow>['getRuntime']
  getSavedView: DataGridExposed<GridLotRow>['getSavedView']
  applySavedView: DataGridExposed<GridLotRow>['applySavedView']
  restoreFocusAnchor: DataGridExposed<GridLotRow>['restoreFocusAnchor']
  captureFocusAnchor: DataGridExposed<GridLotRow>['captureFocusAnchor']
}

export type GridHistoryStatusLike = {
  canUndo?: boolean
  canRedo?: boolean
  latestUndoOperationId?: string | null
  latestRedoOperationId?: string | null
  datasetVersion?: number | null
}

export type GridHistoryRowSnapshot<TApiRow> = {
  id?: string | number
  rowId?: string | number
  index?: number
  row?: TApiRow | GridLotRow | unknown
}

export type GridHistoryMutationResponse<TApiRow> = GridHistoryStatusLike & {
  operationId?: string | null
  action?: 'undo' | 'redo'
  rows?: GridHistoryRowSnapshot<TApiRow>[]
  updatedRows?: GridHistoryRowSnapshot<TApiRow>[]
  invalidation?: unknown
  rejected?: readonly unknown[]
}

export type HistoryStatusSource = {
  subscribeHistoryStatus?: (listener: (status: GridHistoryStatusLike) => void) => () => void
}

export type DatasetPeriod = 'week' | 'month' | 'year'

export type FilterPreset = {
  id: string
  name: string
  scope: 'auction' | 'procurement'
  filters: ServerQuickFiltersState
  grid_view: unknown | null
  is_favorite: boolean
  created_at: string | null
  updated_at: string | null
}

export type AnalysisConfigCategoryRule = {
  category: string
  keywords: string[]
}

export type AnalysisConfigLegalRiskRules = {
  high_keywords: string[]
  medium_keywords: string[]
  medium_categories: string[]
}

export type OwnerScoringProfile = {
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

export type ScoringDimensionWeights = {
  economics: string | number
  risk: string | number
  urgency: string | number
  data_quality: string | number
  operational_readiness: string | number
  owner_fit: string | number
  manual_intent: string | number
}

export type AnalysisConfigResponse = {
  id: string
  category_rules: AnalysisConfigCategoryRule[]
  exclusion_keywords: string[]
  legal_risk_rules: AnalysisConfigLegalRiskRules
  owner_profile: OwnerScoringProfile
  dimension_weights: ScoringDimensionWeights
  created_at: string
  updated_at: string
}

export type ServerQuickFiltersState = {
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

export type GridColumnWidthsState = Record<string, number | null>

export type GridWorkSnapshot = {
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

export type MobileInlineEditTarget = {
  rowId: string | number
  rowIndex: number
  columnIndex: number
  columnKey: string
}
