<script setup lang="ts">
import { computed, defineComponent, h, nextTick, onMounted, onUnmounted, reactive, ref, watch, type PropType } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { storeToRefs } from 'pinia'
import {
  DataGrid,
  type DataGridAppToolbarModule,
  type DataGridAppClientRowModelOptions,
  type DataGridAppColumnInput,
  type DataGridExposed,
  type DataGridSavedViewSnapshot,
  readDataGridSavedViewFromStorage,
  writeDataGridSavedViewToStorage,
} from '@affino/datagrid-vue-app'
import { createDialogFocusOrchestrator, useDialogController } from '@affino/dialog-vue'
import AuthLoginScreen from './components/AuthLoginScreen.vue'
import AnalysisSignalTooltip from './components/AnalysisSignalTooltip.vue'
import AffinoCombobox from './components/AffinoCombobox.vue'
import LotNameCell from './components/LotNameCell.vue'
import RatingInfoTooltip from './components/RatingInfoTooltip.vue'
import { useAuthStore } from './stores/auth'
import { workspaceDataGridTheme } from './theme/dataGridTheme'

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
  ratingScore: number
  ratingLevel: string
  ratingReasons: string[]
  workDecisionStatus: string
  lotUrl: string
  auctionUrl: string
  images: ApiLotImage[]
  primaryImageUrl: string
  imageCount: number
}
type GridApi = NonNullable<ReturnType<DataGridExposed<GridLotRow>['getApi']>>
type GridSelectionSnapshot = ReturnType<GridApi['selection']['getSnapshot']>
type GridSelectionPoint = NonNullable<NonNullable<GridSelectionSnapshot>['activeCell']>

type GridFocusAnchor = {
  selectionSnapshot: GridSelectionSnapshot
  activeCell: GridSelectionPoint | null
  logicalRowId: string | null
  rowId: string | number | null
  columnIndex: number | null
  columnKey: string | null
  element: HTMLElement | null
}

type FilterOption = {
  label: string
  value: string
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

type AnalysisConfigResponse = {
  id: string
  category_rules: AnalysisConfigCategoryRule[]
  exclusion_keywords: string[]
  legal_risk_rules: AnalysisConfigLegalRiskRules
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

type ServerQuickFiltersState = {
  period: DatasetPeriod
  source: string
  analysisColor: string
  query: string
  status: string
  minPrice: string
  maxPrice: string
  onlyNew: boolean
  shortlist: boolean
  minRating: number
}

const allRows = ref<GridLotRow[]>([])
const sources = ref<ApiSource[]>([])
const presets = ref<FilterPreset[]>([])
const analysisConfig = ref<AnalysisConfigResponse | null>(null)
const selectedPresetId = ref('')
const presetDialogMode = ref<PresetDialogMode>('create')
const presetNameDraft = ref('')
const loading = ref(false)
const presetsLoading = ref(false)
const analysisConfigLoading = ref(false)
const analysisConfigSaving = ref(false)
const analysisConfigError = ref('')
const errorMessage = ref('')
const lastLoadedAt = ref<string | null>(null)
const backgroundStatus = ref('Ожидаем фоновое обновление')
const selectedLot = ref<GridLotRow | null>(null)
const selectedLotDetails = ref<LotDetailResponse | null>(null)
const selectedAuctionDetails = ref<AuctionDetailResponse | null>(null)
const selectedWorkspace = ref<LotWorkspaceResponse | null>(null)
const detailLoading = ref(false)
const projectedRowsForSummary = ref<GridLotRow[]>([])
const gridSummaryReady = ref(false)
const DETAIL_PANE_WIDTH_STORAGE_KEY = 'auction-detail-pane-width'
const GRID_SAVED_VIEW_STORAGE_KEY = 'auction-grid-saved-view-v2'
const SERVER_FILTERS_STORAGE_KEY = 'auction-server-filters'
const LOTS_DATASET_SIZE = 10_000
const DETAIL_PANE_DEFAULT_WIDTH = 720
const DETAIL_PANE_MIN_WIDTH = 420
const DETAIL_PANE_MAX_WIDTH = 980
const detailPaneWidth = ref(readStoredDetailPaneWidth())
const gridRef = ref<DataGridExposed<GridLotRow> | null>(null)
const gridSurfaceRef = ref<HTMLElement | null>(null)
const gridSavedViewRestored = ref(false)
const gridRowRevision = ref(0)
let resizeStartX = 0
let resizeStartWidth = 0
let detailRequestId = 0
let detailGridFocusAnchor: GridFocusAnchor | null = null
const queuedRowUpdates = new Map<string, ApiLotRow>()
let rowUpdateFrame: number | null = null
let deferredLotsReloadTimer: ReturnType<typeof window.setTimeout> | null = null
let gridSummaryFrame: number | null = null

const DEFAULT_SERVER_FILTERS: ServerQuickFiltersState = {
  period: 'month',
  source: 'tbankrot',
  analysisColor: '',
  query: '',
  status: '',
  minPrice: '',
  maxPrice: '',
  onlyNew: false,
  shortlist: false,
  minRating: 0,
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

const EDITABLE_GRID_COLUMN_KEYS = new Set([
  'marketValue',
  'platformFee',
  'deliveryCost',
  'dismantlingCost',
  'repairCost',
  'storageCost',
  'legalCost',
  'otherCosts',
  'targetProfit',
  'excludeFromAnalysis',
  'exclusionReason',
])

const EDITABLE_GRID_NUMERIC_KEYS = [
  'marketValue',
  'platformFee',
  'deliveryCost',
  'dismantlingCost',
  'repairCost',
  'storageCost',
  'legalCost',
  'otherCosts',
  'targetProfit',
] as const

const ZERO_DEFAULT_GRID_NUMERIC_KEYS = [
  'platformFee',
  'deliveryCost',
  'dismantlingCost',
  'repairCost',
  'storageCost',
  'legalCost',
  'otherCosts',
  'targetProfit',
] as const

const ZERO_DEFAULT_GRID_NUMERIC_KEY_SET = new Set<string>(ZERO_DEFAULT_GRID_NUMERIC_KEYS)

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
const pendingGridSaveTimers = new Map<string, ReturnType<typeof window.setTimeout>>()
const optimisticGridRows = new Map<string, GridLotRow>()

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

const QuickFiltersToolbar = defineComponent({
  name: 'QuickFiltersToolbar',
  props: {
    periodValue: {
      type: String as PropType<DatasetPeriod>,
      required: true,
    },
    sourceValue: {
      type: String,
      required: true,
    },
    analysisValue: {
      type: String,
      required: true,
    },
    statusValue: {
      type: String,
      required: true,
    },
    queryValue: {
      type: String,
      required: true,
    },
    minPriceValue: {
      type: String,
      required: true,
    },
    maxPriceValue: {
      type: String,
      required: true,
    },
    minRatingValue: {
      type: Number,
      required: true,
    },
    onlyNew: {
      type: Boolean,
      required: true,
    },
    shortlist: {
      type: Boolean,
      required: true,
    },
    activeFilterCount: {
      type: Number,
      required: true,
    },
    sourceOptions: {
      type: Array as PropType<FilterOption[]>,
      required: true,
    },
    analysisOptions: {
      type: Array as PropType<FilterOption[]>,
      required: true,
    },
    statusOptions: {
      type: Array as PropType<FilterOption[]>,
      required: true,
    },
    periodOptions: {
      type: Array as PropType<FilterOption[]>,
      required: true,
    },
    onPeriodChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onSourceChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onAnalysisChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onStatusChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onQueryChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onMinPriceChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onMaxPriceChange: {
      type: Function as PropType<(value: string) => void>,
      required: true,
    },
    onMinRatingChange: {
      type: Function as PropType<(value: number) => void>,
      required: true,
    },
    onOnlyNewChange: {
      type: Function as PropType<(value: boolean) => void>,
      required: true,
    },
    onShortlistChange: {
      type: Function as PropType<(value: boolean) => void>,
      required: true,
    },
    onReset: {
      type: Function as PropType<() => void>,
      required: true,
    },
  },
  setup(props) {
    return () =>
      h('section', { class: 'quick-filters-bar', 'aria-label': 'Быстрые фильтры каталога' }, [
        h('input', {
          class: 'quick-filters-bar__input quick-filters-bar__input--search',
          type: 'search',
          value: props.queryValue,
          placeholder: 'Поиск: название, организатор, номер',
          title: 'Поиск по каталогу',
          onInput: (event: Event) => props.onQueryChange((event.target as HTMLInputElement).value),
        }),
        h(AffinoCombobox, {
          id: 'toolbar-period-filter',
          modelValue: props.periodValue,
          options: props.periodOptions,
          placeholder: 'Период',
          title: 'Период данных',
          class: 'quick-filters-bar__select quick-filters-bar__select--period',
          'onUpdate:modelValue': props.onPeriodChange,
        }),
        h(AffinoCombobox, {
          id: 'toolbar-source-filter',
          modelValue: props.sourceValue,
          options: props.sourceOptions,
          placeholder: 'Источник',
          title: 'Источник',
          class: 'quick-filters-bar__select quick-filters-bar__select--source',
          'onUpdate:modelValue': props.onSourceChange,
        }),
        h(AffinoCombobox, {
          id: 'toolbar-analysis-filter',
          modelValue: props.analysisValue,
          options: props.analysisOptions,
          placeholder: 'Сигнал',
          title: 'Аналитический сигнал',
          class: 'quick-filters-bar__select quick-filters-bar__select--status',
          'onUpdate:modelValue': props.onAnalysisChange,
        }),
        h(AffinoCombobox, {
          id: 'toolbar-status-filter',
          modelValue: props.statusValue,
          options: props.statusOptions,
          placeholder: 'Статус',
          title: 'Статус',
          class: 'quick-filters-bar__select quick-filters-bar__select--status',
          'onUpdate:modelValue': props.onStatusChange,
        }),
        h('input', {
          class: 'quick-filters-bar__input quick-filters-bar__input--narrow',
          type: 'number',
          min: '0',
          step: '1000',
          value: props.minPriceValue,
          placeholder: 'Цена от',
          title: 'Минимальная цена',
          onInput: (event: Event) => props.onMinPriceChange((event.target as HTMLInputElement).value),
        }),
        h('input', {
          class: 'quick-filters-bar__input quick-filters-bar__input--narrow',
          type: 'number',
          min: '0',
          step: '1000',
          value: props.maxPriceValue,
          placeholder: 'Цена до',
          title: 'Максимальная цена',
          onInput: (event: Event) => props.onMaxPriceChange((event.target as HTMLInputElement).value),
        }),
        h('input', {
          class: 'quick-filters-bar__input quick-filters-bar__input--rating',
          type: 'number',
          min: '0',
          max: '100',
          step: '5',
          value: String(props.minRatingValue),
          placeholder: 'Рейтинг',
          title: 'Минимальный рейтинг',
          onInput: (event: Event) => props.onMinRatingChange(Number((event.target as HTMLInputElement).value) || 0),
        }),
        h('label', { class: 'quick-filters-bar__toggle' }, [
          h('input', {
            type: 'checkbox',
            checked: props.onlyNew,
            onChange: (event: Event) => props.onOnlyNewChange((event.target as HTMLInputElement).checked),
          }),
          h('span', 'Новые'),
        ]),
        h('label', { class: 'quick-filters-bar__toggle' }, [
          h('input', {
            type: 'checkbox',
            checked: props.shortlist,
            onChange: (event: Event) => props.onShortlistChange((event.target as HTMLInputElement).checked),
          }),
          h('span', 'Шорт-лист'),
        ]),
        h('div', { class: 'quick-filters-bar__actions' }, [
          props.activeFilterCount > 0
            ? h(
                'button',
                {
                  type: 'button',
                  class: 'secondary-button',
                  onClick: () => props.onReset(),
                },
                'Сбросить',
              )
            : null,
        ]),
      ])
  },
})

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
]
const loadingSkeletonRows = Array.from({ length: 16 }, (_, index) => index)
const loadingSkeletonTemplate = loadingSkeletonColumns.map((column) => `${column.width}px`).join(' ')

const typedColumns: DataGridAppColumnInput<GridLotRow>[] = [
  {
    key: 'ratingScore',
    label: 'Рейтинг',
    dataType: 'number',
    initialState: { width: 96 },
    presentation: { align: 'right', headerAlign: 'right' },
    capabilities: { sortable: true, filterable: true, aggregatable: true },
  },
  {
    key: 'analysisLabel',
    label: 'Сигнал',
    initialState: { width: 176 },
    capabilities: { sortable: true, filterable: true },
    cellRenderer: ({ row }) =>
      row
        ? row.analysisReasons.length
          ? h(
              AnalysisSignalTooltip,
              {
                reasons: row.analysisReasons,
              },
              {
                default: () =>
                  h(
                    'span',
                    {
                      class: ['analysis-pill', `analysis-pill--${row.analysisColor || 'yellow'}`],
                    },
                    row.analysisLabel,
                  ),
              },
            )
          : h(
              'span',
              {
                class: ['analysis-pill', `analysis-pill--${row.analysisColor || 'yellow'}`],
              },
              row.analysisLabel,
            )
        : '',
  },
  { key: 'analysisCategory', label: 'Категория', initialState: { width: 168 } },
  {
    key: 'isNew',
    label: 'Новый',
    dataType: 'boolean',
    initialState: { width: 88 },
    capabilities: { sortable: true, filterable: true },
  },
  { key: 'sourceTitle', label: 'Площадка', initialState: { width: 120 } },
  { key: 'auctionNumber', label: 'Аукцион', initialState: { width: 120 } },
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
  },
  { key: 'lotNumber', label: 'Лот', initialState: { width: 76 } },
  {
    key: 'lotName',
    label: 'Наименование',
    initialState: { width: 430 },
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
    cellRenderer: ({ row }) => formatCurrency(row?.formulaMaxPurchasePrice ?? null),
  },
  {
    key: 'excludeFromAnalysis',
    label: 'Исключить',
    dataType: 'boolean',
    initialState: { width: 112 },
    capabilities: { sortable: true, filterable: true, editable: true },
  },
  {
    key: 'exclusionReason',
    label: 'Причина исключения',
    initialState: { width: 188 },
    capabilities: { sortable: true, filterable: true, editable: true },
  },
  { key: 'status', label: 'Статус', initialState: { width: 170 } },
  { key: 'organizer', label: 'Организатор', initialState: { width: 240 } },
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
  },
]

const columns = typedColumns as unknown as DataGridAppColumnInput[]

function resolveClientGridRowId(row: Pick<GridLotRow, 'id'>) {
  return row.id
}

const clientRowModelOptions = {
  resolveRowId: resolveClientGridRowId,
} satisfies DataGridAppClientRowModelOptions<GridLotRow>

const publicClientRowModelOptions = clientRowModelOptions as DataGridAppClientRowModelOptions<unknown>
const isGridCellEditable = ({ column }: { column: { key: string } }) => EDITABLE_GRID_COLUMN_KEYS.has(column.key)
const columnLayoutOptions = { buttonLabel: 'Колонки' }
const advancedFilterOptions = { buttonLabel: 'Расширенный фильтр' }

const toolbarModules = computed<readonly DataGridAppToolbarModule[]>(() => [
  {
    key: 'quick-filters',
    component: QuickFiltersToolbar,
    props: {
      periodValue: filters.period,
      sourceValue: filters.source,
      analysisValue: filters.analysisColor,
      statusValue: filters.status,
      queryValue: filters.query,
      minPriceValue: filters.minPrice,
      maxPriceValue: filters.maxPrice,
      minRatingValue: filters.minRating,
      onlyNew: filters.onlyNew,
      shortlist: filters.shortlist,
      activeFilterCount: activeFilterCount.value,
      sourceOptions: sourceOptions.value,
      analysisOptions: analysisOptions,
      statusOptions: statusOptions.value,
      periodOptions: periodOptions,
      onPeriodChange: (value: string) => {
        const nextPeriod = isDatasetPeriod(value) ? value : DEFAULT_SERVER_FILTERS.period
        if (filters.period === nextPeriod) return
        filters.period = nextPeriod
        void loadLots()
      },
      onSourceChange: (value: string) => {
        filters.source = value
      },
      onAnalysisChange: (value: string) => {
        filters.analysisColor = value
      },
      onStatusChange: (value: string) => {
        filters.status = value
      },
      onQueryChange: (value: string) => {
        filters.query = value
      },
      onMinPriceChange: (value: string) => {
        filters.minPrice = value
      },
      onMaxPriceChange: (value: string) => {
        filters.maxPrice = value
      },
      onMinRatingChange: (value: number) => {
        filters.minRating = Math.min(100, Math.max(0, value))
      },
      onOnlyNewChange: (value: boolean) => {
        filters.onlyNew = value
      },
      onShortlistChange: (value: boolean) => {
        filters.shortlist = value
      },
      onReset: resetFilters,
    },
  },
])

const periodOptions: FilterOption[] = [
  { label: 'Неделя', value: 'week' },
  { label: 'Месяц', value: 'month' },
  { label: 'Год', value: 'year' },
]

const sourceOptions = computed(() => sources.value.map((source) => ({ label: source.title, value: source.code })))

const analysisOptions: FilterOption[] = [
  { label: 'Любой сигнал', value: '' },
  { label: 'Зеленый: интересный лот', value: 'green' },
  { label: 'Желтый: считать детальнее', value: 'yellow' },
  { label: 'Оранжевый: срочно', value: 'orange' },
  { label: 'Красный: слабый интерес / юрист', value: 'red' },
  { label: 'Серый: неполные данные / исключение', value: 'gray' },
]

const presetOptions = computed(() => [
  { label: 'Подборки', value: '' },
  ...presets.value.map((preset) => ({
    label: preset.is_favorite ? `${preset.name} *` : preset.name,
    value: preset.id,
  })),
])
const selectedPreset = computed(() => presets.value.find((preset) => preset.id === selectedPresetId.value) ?? null)
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

const statusOptions = computed(() => {
  return [
    { label: 'Любой', value: '' },
    ...[...new Set(allRows.value.map((row) => row.status).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right, 'ru'))
      .map((status) => ({ label: status, value: status })),
  ]
})

const rows = computed(() => allRows.value.filter(matchesQuickFilters))
const summaryRows = computed(() => (gridSummaryReady.value ? projectedRowsForSummary.value : rows.value))
const totalRows = computed(() => summaryRows.value.length)
const loadedRowsCount = computed(() => allRows.value.length)
const openApplicationsCount = computed(() =>
  summaryRows.value.filter((row) => row.status.toLowerCase().includes('прием') || row.status.toLowerCase().includes('приём'))
    .length,
)
const newCount = computed(() => summaryRows.value.filter((row) => row.isNew).length)
const highRatingCount = computed(() => summaryRows.value.filter((row) => row.ratingScore >= 75).length)
const activeFilterCount = computed(() => {
  return [
    filters.source !== DEFAULT_SERVER_FILTERS.source,
    filters.analysisColor,
    filters.query,
    filters.status,
    filters.minPrice,
    filters.maxPrice,
    filters.onlyNew,
    filters.shortlist,
    filters.minRating > 0,
  ].filter(Boolean).length
})

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

const priceScheduleFields = computed(() =>
  (selectedLot.value?.priceSchedule ?? []).map((step, index) => ({
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
const analysisReasonItems = computed(() =>
  (selectedLot.value?.analysisReasons ?? []).filter((reason) => !(detailImages.value.length && isNoPhotoReason(reason))),
)
const detailCachedAt = computed(() => formatDateTime(selectedWorkspace.value?.detail_cached_at ?? null))
const ratingReasonItems = computed(() => selectedLot.value?.ratingReasons ?? [])
const changeFields = computed(() => selectedWorkspace.value?.changes.fields ?? [])
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
  const fallbackImages = selectedLot.value?.source === 'tbankrot' ? selectedRowImages : [...selectedRowImages, ...liveDetailImages]
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

function makeFields(entries: Array<[string, unknown]>): DetailField[] {
  return entries
    .map(([label, value]) => ({ label, value: normalizeTextValue(value) }))
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
    .map((field) => ({
      label: field.name.trim(),
      value: field.value.trim(),
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
  return documents.filter((document) => {
    const key = document.external_id || document.url || `${document.name || ''}\n${document.received_at || ''}`
    if (!key.trim() || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function uniqueDetailImages(images: Array<ApiLotImage | DetailImage>): DetailImage[] {
  const seen = new Set<string>()
  return images
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
  const query = typeof value?.query === 'string' ? value.query : DEFAULT_SERVER_FILTERS.query
  const status = typeof value?.status === 'string' ? value.status : DEFAULT_SERVER_FILTERS.status
  const minPrice = typeof value?.minPrice === 'string' ? value.minPrice : DEFAULT_SERVER_FILTERS.minPrice
  const maxPrice = typeof value?.maxPrice === 'string' ? value.maxPrice : DEFAULT_SERVER_FILTERS.maxPrice
  const onlyNew = value?.onlyNew === true
  const shortlist = value?.shortlist === true
  const minRating = Number.isFinite(value?.minRating)
    ? Math.min(100, Math.max(0, Number(value?.minRating)))
    : DEFAULT_SERVER_FILTERS.minRating

  return {
    period,
    source,
    analysisColor,
    query,
    status,
    minPrice,
    maxPrice,
    onlyNew,
    shortlist,
    minRating,
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

function withoutGridSort<TRow extends Record<string, unknown>>(
  savedView: DataGridSavedViewSnapshot<TRow>,
): DataGridSavedViewSnapshot<TRow> {
  const rowSnapshot = savedView.state.rows.snapshot
  if (!rowSnapshot.sortModel.length) return savedView

  return {
    ...savedView,
    state: {
      ...savedView.state,
      rows: {
        ...savedView.state.rows,
        snapshot: {
          ...rowSnapshot,
          sortModel: [],
        },
      },
    },
  }
}

function clearGridSortModel() {
  const api = gridRef.value?.getApi()
  if (!api) return
  const sortModel = api.rows.getSnapshot().sortModel
  if (sortModel.length) {
    api.rows.setSortModel([])
  }
}

function readStoredGridSavedView() {
  if (!gridRef.value) return null

  const savedView = readDataGridSavedViewFromStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, (state, options) =>
    gridRef.value?.migrateState(state, options) ?? null,
  )
  return savedView ? withoutGridSort(savedView) : null
}

function restoreGridSavedView() {
  if (gridSavedViewRestored.value || !gridRef.value) return

  gridSavedViewRestored.value = true
  const savedView = readStoredGridSavedView()
  if (savedView) {
    try {
      gridRef.value.applySavedView(savedView)
      clearGridSortModel()
      writeDataGridSavedViewToStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, savedView)
    } catch {
      window.localStorage.removeItem(GRID_SAVED_VIEW_STORAGE_KEY)
    }
  }
  scheduleGridSummaryRefresh()
}

function persistGridSavedView() {
  if (!gridSavedViewRestored.value) return

  clearGridSortModel()
  const savedView = gridRef.value?.getSavedView()
  if (!savedView) return

  writeDataGridSavedViewToStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, withoutGridSort(savedView))
  scheduleGridSummaryRefresh()
}

function writeGridSavedView(view: unknown | null) {
  if (!gridRef.value || !view) return
  const migratedView = view as NonNullable<ReturnType<NonNullable<typeof gridRef.value>['getSavedView']>>
  const stableView = withoutGridSort(migratedView)
  gridRef.value.applySavedView(stableView)
  clearGridSortModel()
  writeDataGridSavedViewToStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, stableView)
  scheduleGridSummaryRefresh()
}

async function ensureGridSavedViewRestored() {
  if (gridSavedViewRestored.value) return

  await nextTick()
  restoreGridSavedView()
}

function authHeaders() {
  if (!accessToken.value) {
    return new Headers()
  }

  return new Headers({
    Authorization: `Bearer ${accessToken.value}`,
  })
}

function buildLotsUrl() {
  const params = new URLSearchParams({
    period: filters.period,
    source: filters.source,
    page: '1',
    page_size: String(LOTS_DATASET_SIZE),
    persisted: 'true',
  })

  return `/api/v1/auctions/lots?${params.toString()}`
}

async function loadLots() {
  if (!isAuthenticated.value) return

  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(buildLotsUrl(), {
      headers: authHeaders(),
    })
    if (response.status === 401) {
      authStore.logout()
      throw new Error('Сессия истекла. Войдите снова.')
    }
    if (!response.ok) {
      throw new Error(`API вернул ${response.status}`)
    }

    const data = (await response.json()) as LotsResponse
    const nextRevision = gridRowRevision.value + 1
    const mappedRows = data.rows.map((row) => mapApiRow(row, nextRevision))
    sources.value = data.available_sources
    gridRowRevision.value = nextRevision
    allRows.value = mappedRows
    savedGridWorkSnapshots.clear()
    mappedRows.forEach(rememberGridWorkSnapshot)
    lastLoadedAt.value = new Date().toLocaleString('ru-RU')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить лоты'
  } finally {
    loading.value = false
    await ensureGridSavedViewRestored()
    scheduleGridSummaryRefresh()
  }
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

  const query = filters.query.trim().toLowerCase()
  if (query) {
    const haystack = [
      row.lotName,
      row.location,
      row.locationRegion,
      row.locationCity,
      row.locationAddress,
      row.locationCoordinates,
      row.debtorName,
      row.auctionNumber,
      row.auctionName,
      row.lotNumber,
      row.lotDescription,
      row.organizer,
      row.status,
      row.sourceTitle,
      row.analysisLabel,
      row.analysisCategory,
      row.exclusionReason,
    ]
      .join(' ')
      .toLowerCase()
    if (!haystack.includes(query)) return false
  }

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
    analysisReasons: row.analysis.reasons,
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
    ratingScore: row.rating.score,
    ratingLevel: row.rating.level,
    ratingReasons: row.rating.reasons,
    workDecisionStatus: row.work_decision_status ?? '',
    lotUrl: row.lot_url ?? '',
    auctionUrl: row.auction_url ?? '',
    images: row.images ?? [],
    primaryImageUrl: row.primary_image_url ?? '',
    imageCount: row.image_count ?? row.images?.length ?? 0,
  })
}

function applyWorkspaceRow(row: ApiLotRow) {
  applyWorkspaceRows([row])
}

function applyWorkspaceRows(rows: ApiLotRow[], options: { clearOptimistic?: boolean } = {}) {
  if (!rows.length) return
  const mappedUpdates: GridLotRow[] = []

  for (const update of rows) {
    if (!options.clearOptimistic && optimisticGridRows.has(update.row_id)) continue

    const existing = allRows.value.find((row) => row.id === update.row_id)
    const nextRevision = existing?.rowRevision ?? gridRowRevision.value + 1
    if (!existing) {
      gridRowRevision.value = Math.max(gridRowRevision.value, nextRevision)
    }

    const mapped = mapApiRow(update, nextRevision)
    if (!existing && !matchesQuickFilters(mapped)) continue

    if (existing) {
      Object.assign(existing, mapped, { rowRevision: existing.rowRevision })
      mappedUpdates.push(existing)
    } else {
      allRows.value.push(mapped)
      mappedUpdates.push(mapped)
    }
  }

  if (!mappedUpdates.length) return
  patchGridRowsInDataGrid(mappedUpdates)
  scheduleGridSummaryRefresh()

  for (const mapped of mappedUpdates) {
    if (options.clearOptimistic) {
      optimisticGridRows.delete(mapped.id)
    }
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
}

function getLatestGridRow(rowId: string) {
  return optimisticGridRows.get(rowId) ?? allRows.value.find((row) => row.id === rowId) ?? null
}

function patchGridRowsInDataGrid(rows: readonly GridLotRow[]) {
  const api = gridRef.value?.getApi()
  if (!api?.rows.hasPatchSupport() || !rows.length) return

  api.rows.applyEdits(
    rows.map((row) => ({
      rowId: resolveClientGridRowId(row),
      data: row,
    })),
    { emit: false, reapply: false },
  )
}

function readProjectedRowsFromGrid() {
  const api = gridRef.value?.getApi()
  if (!api) return rows.value

  const count = api.rows.getCount()
  if (count <= 0) return []

  return api.rows.getRange({ start: 0, end: count }).flatMap((node) => {
    const row = node.data as GridLotRow | undefined
    return row && typeof row.id === 'string' ? [row] : []
  })
}

function refreshGridSummaryRows() {
  projectedRowsForSummary.value = readProjectedRowsFromGrid()
  gridSummaryReady.value = true
}

function scheduleGridSummaryRefresh() {
  if (gridSummaryFrame !== null) {
    window.cancelAnimationFrame(gridSummaryFrame)
  }
  gridSummaryFrame = window.requestAnimationFrame(() => {
    gridSummaryFrame = null
    refreshGridSummaryRows()
  })
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

function scheduleLotsReload() {
  if (deferredLotsReloadTimer !== null) {
    window.clearTimeout(deferredLotsReloadTimer)
  }
  deferredLotsReloadTimer = window.setTimeout(() => {
    deferredLotsReloadTimer = null
    void loadLots()
  }, 1200)
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

function buildGridWorkPayload(row: GridLotRow) {
  return {
    market_value: row.marketValue,
    platform_fee: row.platformFee,
    delivery_cost: row.deliveryCost,
    dismantling_cost: row.dismantlingCost,
    repair_cost: row.repairCost,
    storage_cost: row.storageCost,
    legal_cost: row.legalCost,
    other_costs: row.otherCosts,
    target_profit: row.targetProfit,
    exclude_from_analysis: row.excludeFromAnalysis,
    exclusion_reason: row.exclusionReason.trim() || null,
  }
}

function normalizeGridRowPatch(row: Partial<GridLotRow>) {
  const normalized: Partial<GridLotRow> = { ...row }
  for (const key of EDITABLE_GRID_NUMERIC_KEYS) {
    if (key in normalized) {
      const parsed = parseNumber((normalized[key] as string | number | null | undefined) ?? null)
      normalized[key] = (ZERO_DEFAULT_GRID_NUMERIC_KEY_SET.has(key)
        ? parsed ?? 0
        : parsed) as GridLotRow[typeof key]
    }
  }
  if ('excludeFromAnalysis' in normalized) {
    normalized.excludeFromAnalysis = Boolean(normalized.excludeFromAnalysis)
  }
  if ('exclusionReason' in normalized) {
    normalized.exclusionReason = typeof normalized.exclusionReason === 'string' ? normalized.exclusionReason : ''
  }
  return normalized
}

function extractActiveGridRowPatch(focusAnchor: GridFocusAnchor | null) {
  const api = gridRef.value?.getApi()
  const activeCell = focusAnchor?.activeCell ?? getActiveGridCellFromSnapshot(api?.selection.getSnapshot() ?? null)
  if (!api || !activeCell) return null

  const node = api.rows.get(activeCell.rowIndex)
  const row = normalizeGridRowPatch(node?.data as Partial<GridLotRow>)
  return typeof row.id === 'string' ? row : null
}

function handleGridCellChange() {
  const focusAnchor = captureGridFocusAnchor(null, true)
  const rowPatch = extractActiveGridRowPatch(focusAnchor)
  if (!rowPatch?.id) return

  const existingRow = getLatestGridRow(rowPatch.id)
  if (!existingRow) return

  const previousSnapshot = savedGridWorkSnapshots.get(existingRow.id)
  const nextRow = recomputeGridEconomyFields({
    ...existingRow,
    ...rowPatch,
    rowRevision: existingRow.rowRevision,
  })
  const snapshot = serializeGridWorkState(nextRow)

  optimisticGridRows.set(nextRow.id, nextRow)
  patchGridRowsInDataGrid([nextRow])

  if (selectedLot.value?.id === nextRow.id) {
    selectedLot.value = nextRow
  }

  if (previousSnapshot !== snapshot) {
    queueGridRowSave(nextRow.id)
    void restoreGridFocus(focusAnchor)
  }
}

function queueGridRowSave(rowId: string) {
  const existingTimer = pendingGridSaveTimers.get(rowId)
  if (existingTimer) {
    clearTimeout(existingTimer)
  }
  const timer = window.setTimeout(() => {
    pendingGridSaveTimers.delete(rowId)
    void saveGridRow(rowId)
  }, 450)
  pendingGridSaveTimers.set(rowId, timer)
}

async function saveGridRow(rowId: string) {
  const row = getLatestGridRow(rowId)
  if (!row?.lotId) return
  const requestSnapshot = serializeGridWorkState(row)
  const saveStartFocusAnchor = captureGridFocusAnchor(row.id, document.activeElement === document.body)
  try {
    backgroundStatus.value = `Сохраняю экономику лота ${row.lotNumber || row.id}`
    const params = new URLSearchParams()
    if (row.auctionId) params.set('auction_id', row.auctionId)
    const workspace = await fetchJson<LotWorkspaceResponse>(
      `/api/v1/auctions/${row.source}/lots/${encodeURIComponent(row.lotId)}/workspace?${params.toString()}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildGridWorkPayload(row)),
      },
    )
    if (selectedLot.value?.id === rowId) {
      selectedWorkspace.value = workspace
      hydrateWorkDraft(workspace.work_item)
    }
    const focusAnchor = captureGridFocusAnchor(null, document.activeElement === document.body) ?? saveStartFocusAnchor
    const currentOptimisticRow = optimisticGridRows.get(rowId)
    const hasNewerOptimisticEdit = Boolean(
      currentOptimisticRow && serializeGridWorkState(currentOptimisticRow) !== requestSnapshot,
    )
    if (!hasNewerOptimisticEdit) {
      applyWorkspaceRows([workspace.row], { clearOptimistic: true })
      void restoreGridFocus(focusAnchor)
    }
    backgroundStatus.value = `Экономика обновлена: ${row.lotNumber || row.id}`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось сохранить изменения из таблицы'
  }
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

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: new Headers({
      ...Object.fromEntries(authHeaders().entries()),
      ...Object.fromEntries(new Headers(init?.headers ?? {}).entries()),
    }),
  })
  if (response.status === 401) {
    authStore.logout()
    throw new Error('Сессия истекла. Войдите снова.')
  }
  if (!response.ok) {
    throw new Error(`API вернул ${response.status}`)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
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

function buildPresetPayload(name?: string) {
  return {
    name: (name ?? selectedPreset.value?.name ?? '').trim(),
    filters: sanitizeServerFilters(filters),
    grid_view: gridRef.value?.getSavedView() ?? null,
    is_favorite: selectedPreset.value?.is_favorite ?? false,
  }
}

async function applyPresetById(presetId: string) {
  selectedPresetId.value = presetId
  const preset = presets.value.find((item) => item.id === presetId)
  if (!preset) return

  const nextFilters = sanitizeServerFilters(preset.filters)
  const shouldReload = filters.period !== nextFilters.period
  Object.assign(filters, nextFilters)
  if (shouldReload) {
    await loadLots()
  }
  await nextTick()
  writeGridSavedView(preset.grid_view)
}

function sortPresets(items: FilterPreset[]) {
  return [...items].sort((left, right) => {
    if (left.is_favorite !== right.is_favorite) {
      return left.is_favorite ? -1 : 1
    }
    return left.name.localeCompare(right.name, 'ru')
  })
}

function setPresetDialogInitialRef(element: Element | ComponentPublicInstance | null) {
  presetDialogInitialRef.value = element as HTMLElement | null
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

function normalizeDraftNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return ''
  const parsed = parseNumber(value)
  return parsed === null ? '' : String(parsed)
}

function getGridRootElement() {
  return gridSurfaceRef.value?.querySelector<HTMLElement>('.affino-datagrid-app-root') ?? null
}

function escapeGridSelectorValue(value: string) {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(value)
  }
  return value.replace(/["\\]/g, '\\$&')
}

function getActiveGridCellFromSnapshot(selectionSnapshot: GridSelectionSnapshot) {
  const activeRange = selectionSnapshot?.ranges[selectionSnapshot.activeRangeIndex] ?? selectionSnapshot?.ranges[0]
  return selectionSnapshot?.activeCell ?? activeRange?.focus ?? activeRange?.anchor ?? null
}

function resolveLogicalGridRowId(runtimeRowId: string | number | null) {
  if (runtimeRowId === null) return null
  const runtimeKey = String(runtimeRowId)
  return allRows.value.find((row) => resolveClientGridRowId(row) === runtimeKey)?.id ?? null
}

function resolveCurrentRuntimeGridRowId(logicalRowId: string | null) {
  if (!logicalRowId) return null
  const row = allRows.value.find((item) => item.id === logicalRowId)
  return row ? resolveClientGridRowId(row) : null
}

function captureGridFocusAnchor(fallbackLogicalRowId: string | null = null, allowSelectionFallback = false) {
  const api = gridRef.value?.getApi()
  const selectionSnapshot = api?.selection.hasSupport() ? api.selection.getSnapshot() : null
  const activeCell = getActiveGridCellFromSnapshot(selectionSnapshot)
  const gridRoot = getGridRootElement()
  const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const gridElement = activeElement && gridRoot?.contains(activeElement) ? activeElement : null
  const cellElement = gridElement?.closest<HTMLElement>('.grid-cell[data-row-id]') ?? null
  const shouldUseSelectionFallback = allowSelectionFallback || activeElement === document.body

  if (!gridElement && !cellElement && !shouldUseSelectionFallback) return null

  const runtimeRowId = normalizeGridRowId(activeCell?.rowId ?? cellElement?.dataset.rowId ?? null)
  const logicalRowId = fallbackLogicalRowId ?? resolveLogicalGridRowId(runtimeRowId)

  return {
    selectionSnapshot,
    activeCell,
    logicalRowId,
    rowId: runtimeRowId ?? resolveCurrentRuntimeGridRowId(logicalRowId),
    columnIndex: activeCell?.colIndex ?? parseOptionalInteger(cellElement?.dataset.columnIndex),
    columnKey: cellElement?.dataset.columnKey ?? null,
    element: cellElement ?? gridElement,
  }
}

function captureDetailGridFocusAnchor(row: GridLotRow) {
  detailGridFocusAnchor = captureGridFocusAnchor(row.id, true)
}

function normalizeGridRowId(value: unknown): string | number | null {
  if (typeof value === 'string' || typeof value === 'number') return value
  if (value === null || value === undefined) return null
  return String(value)
}

function parseOptionalInteger(value: string | undefined) {
  if (!value) return null
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : null
}

function remapGridSelectionSnapshot(anchor: GridFocusAnchor) {
  const snapshot = anchor.selectionSnapshot
  const nextRowId = resolveCurrentRuntimeGridRowId(anchor.logicalRowId)
  if (!snapshot || !nextRowId || nextRowId === anchor.rowId) return snapshot

  const replacePoint = (point: GridSelectionPoint): GridSelectionPoint =>
    point.rowId === anchor.rowId ? { ...point, rowId: nextRowId } : point

  return {
    ...snapshot,
    activeCell: snapshot.activeCell ? replacePoint(snapshot.activeCell) : snapshot.activeCell,
    ranges: snapshot.ranges.map((range) => ({
      ...range,
      anchor: replacePoint(range.anchor),
      focus: replacePoint(range.focus),
      startRowId: range.startRowId === anchor.rowId ? nextRowId : range.startRowId,
      endRowId: range.endRowId === anchor.rowId ? nextRowId : range.endRowId,
    })),
  }
}

function findGridFocusTarget(anchor: GridFocusAnchor, gridRoot: HTMLElement) {
  if (anchor.element?.isConnected && gridRoot.contains(anchor.element)) {
    return anchor.element
  }

  const currentRuntimeRowId = resolveCurrentRuntimeGridRowId(anchor.logicalRowId)
  const rowId = currentRuntimeRowId ?? (anchor.rowId === null ? null : String(anchor.rowId))
  const rowSelector = rowId ? `[data-row-id="${escapeGridSelectorValue(rowId)}"]` : ''
  const selectors: string[] = []

  if (rowSelector && anchor.columnKey) {
    selectors.push(`.grid-cell${rowSelector}[data-column-key="${escapeGridSelectorValue(anchor.columnKey)}"]`)
  }
  if (rowSelector && anchor.columnIndex !== null) {
    selectors.push(`.grid-cell${rowSelector}[data-column-index="${anchor.columnIndex}"]`)
  }
  if (rowSelector) {
    selectors.push(`.grid-cell.grid-cell--selection-anchor${rowSelector}`, `.grid-cell${rowSelector}`)
  }
  selectors.push('.grid-cell.grid-cell--selection-anchor', '.grid-cell[tabindex="0"]')

  for (const selector of selectors) {
    const element = gridRoot.querySelector<HTMLElement>(selector)
    if (element) return element
  }

  return null
}

function focusGridElement(element: HTMLElement) {
  if (!element.hasAttribute('tabindex')) {
    element.tabIndex = -1
  }
  element.focus({ preventScroll: true })
}

async function restoreGridFocus(anchor: GridFocusAnchor | null) {
  if (!anchor) return

  await nextTick()
  window.requestAnimationFrame(() => {
    const api = gridRef.value?.getApi()
    const selectionSnapshot = remapGridSelectionSnapshot(anchor)
    if (selectionSnapshot && api?.selection.hasSupport()) {
      try {
        api.selection.setSnapshot(selectionSnapshot)
      } catch {
        // The row may have left the current filtered/sorted viewport before focus is restored.
      }
    }

    window.requestAnimationFrame(() => {
      const gridRoot = getGridRootElement()
      if (!gridRoot) return

      const target = findGridFocusTarget(anchor, gridRoot) ?? gridRoot
      focusGridElement(target)
    })
  })
}

async function restoreDetailGridFocus() {
  const anchor = detailGridFocusAnchor
  detailGridFocusAnchor = null
  await restoreGridFocus(anchor)
}

async function openLotDetails(row: GridLotRow) {
  captureDetailGridFocusAnchor(row)
  selectedLot.value = row
  selectedLotDetails.value = null
  selectedAuctionDetails.value = null
  selectedWorkspace.value = null
  resetWorkDraft()
  errorMessage.value = ''

  if (!row.lotId) return

  detailLoading.value = true
  const requestId = ++detailRequestId
  try {
    const params = new URLSearchParams()
    if (row.auctionId) params.set('auction_id', row.auctionId)
    const workspace = await fetchJson<LotWorkspaceResponse>(
      `/api/v1/auctions/${row.source}/lots/${encodeURIComponent(row.lotId)}/workspace?${params.toString()}`,
    )

    if (requestId !== detailRequestId) return

    selectedWorkspace.value = workspace
    selectedLotDetails.value = workspace.lot_detail
    selectedAuctionDetails.value = workspace.auction_detail
    applyWorkspaceRow(workspace.row)
    hydrateWorkDraft(workspace.work_item)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить рабочую карточку лота'
  } finally {
    if (requestId === detailRequestId) {
      detailLoading.value = false
    }
  }
}

function closeLotDetails() {
  detailRequestId += 1
  selectedLot.value = null
  selectedLotDetails.value = null
  selectedAuctionDetails.value = null
  selectedWorkspace.value = null
  resetWorkDraft()
  void restoreDetailGridFocus()
}

function resetCatalogState() {
  allRows.value = []
  projectedRowsForSummary.value = []
  gridSummaryReady.value = false
  presets.value = []
  selectedPresetId.value = ''
  selectedLot.value = null
  selectedLotDetails.value = null
  selectedAuctionDetails.value = null
  selectedWorkspace.value = null
  errorMessage.value = ''
  lastLoadedAt.value = null
  detailLoading.value = false
  backgroundStatus.value = 'Ожидаем фоновое обновление'
  resetWorkDraft()
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

function resetFilters() {
  const shouldReload = filters.period !== DEFAULT_SERVER_FILTERS.period
  Object.assign(filters, DEFAULT_SERVER_FILTERS)
  if (shouldReload) {
    void loadLots()
  }
}

function subscribeToAuctionEvents() {
  const events = new EventSource('/api/v1/auctions/events')

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
    scheduleLotsReload()
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
  if (auctionEvents || !isAuthenticated.value) return
  auctionEvents = subscribeToAuctionEvents()
}

function stopAuctionEvents() {
  auctionEvents?.close()
  auctionEvents = null
}

watch(filters, () => {
  persistServerFilters()
  gridSummaryReady.value = false
  scheduleGridSummaryRefresh()
}, { deep: true })

watch(isAuthenticated, (authenticated) => {
  if (authenticated) {
    void loadLots()
    void loadPresets()
    startAuctionEvents()
    return
  }

  stopAuctionEvents()
  resetCatalogState()
})

onMounted(() => {
  if (isAuthenticated.value) {
    void loadLots()
    void loadPresets()
    startAuctionEvents()
  }
  document.addEventListener('keydown', handleGlobalKeydown, true)
})
onUnmounted(() => {
  stopDetailResize()
  document.removeEventListener('keydown', handleGlobalKeydown, true)
  stopAuctionEvents()
  if (rowUpdateFrame !== null) {
    window.cancelAnimationFrame(rowUpdateFrame)
    rowUpdateFrame = null
  }
  if (deferredLotsReloadTimer !== null) {
    window.clearTimeout(deferredLotsReloadTimer)
    deferredLotsReloadTimer = null
  }
  if (gridSummaryFrame !== null) {
    window.cancelAnimationFrame(gridSummaryFrame)
    gridSummaryFrame = null
  }
  queuedRowUpdates.clear()
  pendingGridSaveTimers.forEach((timer) => clearTimeout(timer))
  pendingGridSaveTimers.clear()
})
</script>

<template>
  <AuthLoginScreen v-if="isRestoring || !isAuthenticated" />
  <main v-else class="auction-shell">
    <section class="auction-toolbar" aria-label="Фильтры каталога лотов">
      <div class="toolbar-title">
        <span class="eyebrow">Каталог банкротных торгов</span>
        <h1>Лоты для отбора</h1>
      </div>
      <div class="toolbar-actions">
        <div class="preset-toolbar">
          <button class="secondary-button" type="button" @click="openAnalysisConfigDialog">Настроить анализ</button>
          <AffinoCombobox
            id="preset-selector"
            class="preset-toolbar__select"
            :model-value="selectedPresetId"
            :options="presetOptions"
            placeholder="Подборки"
            @update:model-value="applyPresetById"
          />
          <button class="secondary-button" type="button" :disabled="presetsLoading" @click="openCreatePresetDialog">
            Сохранить срез
          </button>
          <button class="secondary-button" type="button" :disabled="!selectedPreset" @click="openUpdatePresetDialog">
            Обновить
          </button>
          <button class="secondary-button" type="button" :disabled="!selectedPreset" @click="openDeletePresetDialog">
            Удалить
          </button>
        </div>
        <span v-if="currentUser" class="user-chip">{{ currentUser.full_name }}</span>
        <button class="secondary-button" type="button" @click="authStore.logout">Выйти</button>
      </div>
    </section>

    <section class="summary-strip" aria-label="Сводка каталога">
      <div>
        <span>Найдено</span>
        <strong>{{ totalRows }}</strong>
      </div>
      <div>
        <span>Новые</span>
        <strong>{{ newCount }}</strong>
      </div>
      <div>
        <span>Приём заявок</span>
        <strong>{{ openApplicationsCount }}</strong>
      </div>
      <div>
        <span>Рейтинг 75+</span>
        <strong>{{ highRatingCount }}</strong>
      </div>
      <p>
        {{ backgroundStatus }}
        <span v-if="lastLoadedAt"> · Загружено {{ loadedRowsCount }} · Таблица {{ lastLoadedAt }}</span>
      </p>
    </section>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <section ref="gridSurfaceRef" class="grid-surface" :aria-busy="loading">
      <div v-if="loading && allRows.length === 0" class="loading-state" role="status" aria-live="polite">
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
      <div v-else-if="loading" class="loading-state loading-state--overlay" role="status" aria-live="polite">
        <span class="loading-state__chip">Обновляю данные каталога</span>
      </div>
      <DataGrid
        v-if="!loading || allRows.length > 0"
        ref="gridRef"
        :rows="rows"
        :columns="columns"
        :base-row-height="26"
        :client-row-model-options="publicClientRowModelOptions"
        :toolbar-modules="toolbarModules"
        :theme="workspaceDataGridTheme"
        :is-cell-editable="isGridCellEditable"
        virtualization
        :advanced-filter="advancedFilterOptions"
        :column-layout="columnLayoutOptions"
        layout-mode="fill"
        :row-selection="false"
        :chrome="{ toolbarPlacement: 'integrated', density: 'compact', toolbarGap: 0, workspaceGap: 8 }"
        :history="{ controls: false }"
        @cell-change="handleGridCellChange"
        @update:state="persistGridSavedView"
      />
    </section>

    <aside
      v-if="selectedLot"
      class="side-pane side-pane--detail"
      :style="{ width: `${detailPaneWidth}px` }"
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
          <RatingInfoTooltip :reasons="ratingReasonItems" />
          <span :class="['analysis-pill', `analysis-pill--${selectedLot.analysisColor || 'yellow'}`]">
            {{ selectedLot.analysisLabel }}
          </span>
          <mark v-if="selectedLot.isNew">Новый</mark>
        </div>

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

        <div v-if="detailLoading" class="detail-live-status" role="status" aria-live="polite">
          <span class="detail-live-status__spinner" aria-hidden="true"></span>
          <span>Подгружаю live-данные с площадки</span>
        </div>

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
        <a v-if="detailLotUrl" class="secondary-button" :href="detailLotUrl" target="_blank" rel="noreferrer">
          Лот
        </a>
        <a v-if="detailAuctionUrl" class="primary-button" :href="detailAuctionUrl" target="_blank" rel="noreferrer">
          Аукцион
        </a>
      </footer>
    </aside>

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

            <div class="app-dialog__body">
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
