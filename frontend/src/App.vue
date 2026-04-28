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
  readDataGridSavedViewFromStorage,
  writeDataGridSavedViewToStorage,
} from '@affino/datagrid-vue-app'
import { createDialogFocusOrchestrator, useDialogController } from '@affino/dialog-vue'
import AuthLoginScreen from './components/AuthLoginScreen.vue'
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
  lot_url: string | null
  category: string | null
  status: string | null
  initial_price: string | null
  initial_price_value: string | number | null
  organizer_name: string | null
  application_deadline: string | null
  auction_date: string | null
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
  classifier: string | null
  currency: string | null
  initial_price: string | null
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
}

type LotDetailResponse = {
  source: string
  url: string
  auction: ApiAuctionSummary
  lot: ApiLotSummary
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
  max_purchase_price: string | number | null
  market_value: string | number | null
  platform_fee: string | number | null
  delivery_cost: string | number | null
  dismantling_cost: string | number | null
  repair_cost: string | number | null
  storage_cost: string | number | null
  legal_cost: string | number | null
  other_costs: string | number | null
  analogs: Array<Record<string, unknown>>
  created_at: string | null
  updated_at: string | null
}

type LotEconomy = {
  current_price: string | number | null
  market_value: string | number | null
  full_entry_cost: string | number | null
  potential_profit: string | number | null
  roi: string | number | null
  market_discount: string | number | null
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
  max_purchase_price: string
  market_value: string
  platform_fee: string
  delivery_cost: string
  dismantling_cost: string
  repair_cost: string
  storage_cost: string
  legal_cost: string
  other_costs: string
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
  source: string
  sourceTitle: string
  auctionId: string
  auctionNumber: string
  publicationDate: Date | null
  lotId: string
  lotNumber: string
  lotName: string
  status: string
  price: number | null
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

type PresetDialogMode = 'create' | 'update' | 'delete'

type ServerQuickFiltersState = {
  period: DatasetPeriod
  source: string
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
const selectedPresetId = ref('')
const presetDialogMode = ref<PresetDialogMode>('create')
const presetNameDraft = ref('')
const loading = ref(false)
const presetsLoading = ref(false)
const errorMessage = ref('')
const lastLoadedAt = ref<string | null>(null)
const backgroundStatus = ref('Ожидаем фоновое обновление')
const selectedLot = ref<GridLotRow | null>(null)
const selectedLotDetails = ref<LotDetailResponse | null>(null)
const selectedAuctionDetails = ref<AuctionDetailResponse | null>(null)
const selectedWorkspace = ref<LotWorkspaceResponse | null>(null)
const detailLoading = ref(false)
const workSaving = ref(false)
const DETAIL_PANE_WIDTH_STORAGE_KEY = 'auction-detail-pane-width'
const GRID_SAVED_VIEW_STORAGE_KEY = 'auction-grid-saved-view-v2'
const SERVER_FILTERS_STORAGE_KEY = 'auction-server-filters'
const LOTS_DATASET_SIZE = 10_000
const DETAIL_PANE_DEFAULT_WIDTH = 720
const DETAIL_PANE_MIN_WIDTH = 420
const DETAIL_PANE_MAX_WIDTH = 980
const detailPaneWidth = ref(readStoredDetailPaneWidth())
const gridRef = ref<DataGridExposed<GridLotRow> | null>(null)
const gridSavedViewRestored = ref(false)
const gridRowRevision = ref(0)
let resizeStartX = 0
let resizeStartWidth = 0
let detailRequestId = 0

const DEFAULT_SERVER_FILTERS: ServerQuickFiltersState = {
  period: 'month',
  source: 'all',
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
  max_purchase_price: '',
  market_value: '',
  platform_fee: '',
  delivery_cost: '',
  dismantling_cost: '',
  repair_cost: '',
  storage_cost: '',
  legal_cost: '',
  other_costs: '',
})

const workDraft = reactive<WorkDraft>(emptyWorkDraft())
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
    onApply: {
      type: Function as PropType<() => void>,
      required: true,
    },
    onReset: {
      type: Function as PropType<() => void>,
      required: true,
    },
  },
  setup(props) {
    const applyFilters = () => props.onApply()

    return () =>
      h('section', { class: 'quick-filters-bar', 'aria-label': 'Быстрые фильтры каталога' }, [
        h('input', {
          class: 'quick-filters-bar__input quick-filters-bar__input--search',
          type: 'search',
          value: props.queryValue,
          placeholder: 'Поиск: название, организатор, номер',
          title: 'Поиск по каталогу',
          onInput: (event: Event) => props.onQueryChange((event.target as HTMLInputElement).value),
          onKeydown: (event: KeyboardEvent) => {
            if (event.key === 'Enter') applyFilters()
          },
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
          onKeydown: (event: KeyboardEvent) => {
            if (event.key === 'Enter') applyFilters()
          },
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
          onKeydown: (event: KeyboardEvent) => {
            if (event.key === 'Enter') applyFilters()
          },
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
          onKeydown: (event: KeyboardEvent) => {
            if (event.key === 'Enter') applyFilters()
          },
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
          h(
            'button',
            {
              type: 'button',
              class: 'secondary-button quick-filters-bar__icon-action',
              'aria-label': 'Сбросить быстрый отбор',
              title: 'Сбросить быстрый отбор',
              onClick: () => props.onReset(),
            },
            '↺',
          ),
          h(
            'button',
            {
              type: 'button',
              class: 'primary-button quick-filters-bar__icon-action',
              'aria-label': 'Применить быстрый отбор',
              title: 'Применить быстрый отбор',
              onClick: applyFilters,
            },
            '✓',
          ),
        ]),
      ])
  },
})

const loadingSkeletonColumns = [
  { key: 'ratingScore', label: 'Рейтинг', width: 96, placeholderWidth: '54%' },
  { key: 'isNew', label: 'Новый', width: 88, placeholderWidth: '42%' },
  { key: 'sourceTitle', label: 'Площадка', width: 120, placeholderWidth: '62%' },
  { key: 'auctionNumber', label: 'Аукцион', width: 120, placeholderWidth: '58%' },
  { key: 'publicationDate', label: 'Дата публикации', width: 160, placeholderWidth: '60%' },
  { key: 'lotNumber', label: 'Лот', width: 76, placeholderWidth: '46%' },
  { key: 'lotName', label: 'Наименование', width: 430, placeholderWidth: '88%' },
  { key: 'price', label: 'Цена', width: 150, placeholderWidth: '70%' },
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
    key: 'price',
    label: 'Цена',
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

const clientRowModelOptions = {
  resolveRowId: (row) => `${row.id}:${row.rowRevision}`,
} satisfies DataGridAppClientRowModelOptions<GridLotRow>

const publicClientRowModelOptions = clientRowModelOptions as DataGridAppClientRowModelOptions<unknown>
const isGridCellEditable = () => false
const columnLayoutOptions = { buttonLabel: 'Колонки' }
const advancedFilterOptions = { buttonLabel: 'Расширенный фильтр' }

const toolbarModules = computed<readonly DataGridAppToolbarModule[]>(() => [
  {
    key: 'quick-filters',
    component: QuickFiltersToolbar,
    props: {
      periodValue: filters.period,
      sourceValue: filters.source,
      statusValue: filters.status,
      queryValue: filters.query,
      minPriceValue: filters.minPrice,
      maxPriceValue: filters.maxPrice,
      minRatingValue: filters.minRating,
      onlyNew: filters.onlyNew,
      shortlist: filters.shortlist,
      activeFilterCount: activeFilterCount.value,
      sourceOptions: sourceOptions.value,
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
      onApply: applyQuickFilters,
      onReset: resetFilters,
    },
  },
])

const periodOptions: FilterOption[] = [
  { label: 'Неделя', value: 'week' },
  { label: 'Месяц', value: 'month' },
  { label: 'Год', value: 'year' },
]

const sourceOptions = computed(() => [
  { label: 'Все площадки', value: 'all' },
  ...sources.value.map((source) => ({ label: source.title, value: source.code })),
])

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

const statusOptions = computed(() => {
  return [
    { label: 'Любой', value: '' },
    ...[...new Set(allRows.value.map((row) => row.status).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right, 'ru'))
      .map((status) => ({ label: status, value: status })),
  ]
})

const rows = computed(() => allRows.value.filter(matchesQuickFilters))
const totalRows = computed(() => rows.value.length)
const loadedRowsCount = computed(() => allRows.value.length)
const activeCount = computed(() =>
  rows.value.filter((row) => row.status.toLowerCase().includes('прием') || row.status.toLowerCase().includes('приём'))
    .length,
)
const newCount = computed(() => rows.value.filter((row) => row.isNew).length)
const highRatingCount = computed(() => rows.value.filter((row) => row.ratingScore >= 75).length)
const activeFilterCount = computed(() => {
  return [
    filters.source !== DEFAULT_SERVER_FILTERS.source,
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
const liveOrganizer = computed(() => selectedAuctionDetails.value?.organizer ?? null)
const liveDebtor = computed(() => selectedAuctionDetails.value?.debtor ?? null)
const detailLotUrl = computed(() => selectedLotDetails.value?.lot.url || selectedLotDetails.value?.url || selectedLot.value?.lotUrl || '')
const detailAuctionUrl = computed(() => liveAuction.value?.url || selectedAuctionDetails.value?.url || selectedLot.value?.auctionUrl || '')

const detailFields = computed<DetailField[]>(() => {
  if (!selectedLot.value) return []
  return makeFields([
    ['Площадка', selectedLot.value.sourceTitle],
    ['Аукцион', liveAuction.value?.number || selectedLot.value.auctionNumber],
    ['Публикация', liveAuction.value?.publication_date || formatDateTime(selectedLot.value.publicationDate)],
    ['Лот', liveLot.value?.number || selectedLot.value.lotNumber],
    ['Статус', liveLot.value?.status || selectedLot.value.status],
    ['Цена', liveLot.value?.initial_price || formatCurrency(selectedLot.value.price)],
    ['Организатор', liveOrganizer.value?.name || selectedLot.value.organizer],
    ['Заявки до', liveAuction.value?.application_deadline || formatDateTime(selectedLot.value.applicationDeadline)],
    ['Торги', liveAuction.value?.auction_date || formatDateTime(selectedLot.value.auctionDate)],
    ['Первое наблюдение', formatDateTime(selectedLot.value.firstSeenAt)],
    ['Последнее наблюдение', formatDateTime(selectedLot.value.lastSeenAt)],
  ])
})

const lotInfoFields = computed(() =>
  makeFields([
    ['Категория', liveLot.value?.category],
    ['Классификатор ЕФРСБ', liveLot.value?.classifier],
    ['Валюта цены по ОКВ', liveLot.value?.currency],
    ['Начальная цена', liveLot.value?.initial_price],
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
    ['Описание имущества', liveLot.value?.description],
    ['Порядок ознакомления', liveLot.value?.inspection_order],
    ['Порядок внесения и возврата задатка', liveLot.value?.deposit_order],
  ]),
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
const economyFields = computed(() =>
  makeFields([
    ['Текущая цена', formatApiMoney(selectedWorkspace.value?.economy.current_price)],
    ['Рыночная стоимость', formatApiMoney(selectedWorkspace.value?.economy.market_value)],
    ['Полная стоимость входа', formatApiMoney(selectedWorkspace.value?.economy.full_entry_cost)],
    ['Потенциальная прибыль', formatApiMoney(selectedWorkspace.value?.economy.potential_profit)],
    ['ROI', formatApiPercent(selectedWorkspace.value?.economy.roi)],
    ['Дисконт к рынку', formatApiPercent(selectedWorkspace.value?.economy.market_discount)],
    ['Макс. цена покупки', formatApiMoney(selectedWorkspace.value?.economy.max_purchase_price)],
  ]),
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
const detailImages = computed(() =>
  detailDocuments.value.filter(
    (document) => belongsToSelectedLotMedia(document) && document.url && /\.(png|jpe?g|gif|webp)(\?|$)/i.test(document.url),
  ),
)
const mediaDocuments = computed(() =>
  detailDocuments.value.filter((document) => {
    const text = [document.name, document.document_type, document.comment].filter(Boolean).join(' ')
    return (
      belongsToSelectedLotMedia(document) &&
      (/фото|photo|изображ/i.test(text) || /\.(rar|zip|7z)(\?|$)/i.test(document.url || document.name || ''))
    )
  }),
)

function makeFields(entries: Array<[string, string | null | undefined]>): DetailField[] {
  return entries
    .map(([label, value]) => ({ label, value: normalizeTextValue(value) }))
    .filter((field) => field.value && field.value !== 'Не задано')
}

function normalizeTextValue(value: string | null | undefined) {
  return typeof value === 'string' ? value.trim() : ''
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
  const source =
    hasPeriod && typeof value?.source === 'string' && value.source.trim()
      ? value.source
      : DEFAULT_SERVER_FILTERS.source
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

function readStoredGridSavedView() {
  if (!gridRef.value) return null

  return readDataGridSavedViewFromStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, (state, options) =>
    gridRef.value?.migrateState(state, options) ?? null,
  )
}

function restoreGridSavedView() {
  if (gridSavedViewRestored.value || !gridRef.value) return

  gridSavedViewRestored.value = true
  const savedView = readStoredGridSavedView()
  if (savedView) {
    try {
      gridRef.value.applySavedView(savedView)
    } catch {
      window.localStorage.removeItem(GRID_SAVED_VIEW_STORAGE_KEY)
    }
  }
}

function persistGridSavedView() {
  if (!gridSavedViewRestored.value) return

  const savedView = gridRef.value?.getSavedView()
  if (!savedView) return

  writeDataGridSavedViewToStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, savedView)
}

function writeGridSavedView(view: unknown | null) {
  if (!gridRef.value || !view) return
  const migratedView = view as NonNullable<ReturnType<NonNullable<typeof gridRef.value>['getSavedView']>>
  gridRef.value.applySavedView(migratedView)
  writeDataGridSavedViewToStorage(window.localStorage, GRID_SAVED_VIEW_STORAGE_KEY, migratedView)
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
    lastLoadedAt.value = new Date().toLocaleString('ru-RU')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить лоты'
  } finally {
    loading.value = false
    await ensureGridSavedViewRestored()
  }
}

function matchesQuickFilters(row: GridLotRow) {
  if (filters.source !== 'all' && row.source !== filters.source) return false
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
    const haystack = [row.lotName, row.auctionNumber, row.lotNumber, row.organizer, row.status, row.sourceTitle]
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
  return {
    id: row.row_id,
    rowRevision,
    source: row.source,
    sourceTitle: row.source_title,
    auctionId: row.auction_id ?? '',
    auctionNumber: row.auction_number ?? '',
    publicationDate: parseDateTime(row.publication_date),
    lotId: row.lot_id ?? '',
    lotNumber: row.lot_number ?? '',
    lotName: row.lot_name ?? '',
    status: row.status ?? '',
    price: parseNumber(row.initial_price_value),
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
  }
}

function applyWorkspaceRow(row: ApiLotRow) {
  const index = allRows.value.findIndex((existing) => existing.id === row.row_id)
  const existingRow = index >= 0 ? allRows.value[index] : null
  const nextRevision = existingRow ? existingRow.rowRevision + 1 : gridRowRevision.value + 1
  gridRowRevision.value = Math.max(gridRowRevision.value, nextRevision)
  const mapped = mapApiRow(row, nextRevision)
  selectedLot.value = mapped
  if (index >= 0) {
    allRows.value = allRows.value.map((existing) => (existing.id === mapped.id ? mapped : existing))
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
  const russianDateTime = normalized.match(
    /^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?/,
  )
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

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
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

  Object.assign(filters, sanitizeServerFilters(preset.filters))
  await loadLots()
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

  for (const key of Object.keys(workDraft) as Array<keyof WorkDraft>) {
    const value = workItem[key as keyof LotWorkItem]
    workDraft[key] = value === null || value === undefined ? '' : String(value)
  }
}

function buildWorkPayload() {
  return Object.fromEntries(
    Object.entries(workDraft).map(([key, value]) => [key, value.trim() ? value.trim() : null]),
  )
}

async function openLotDetails(row: GridLotRow) {
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
}

function resetCatalogState() {
  allRows.value = []
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

async function saveWorkItem() {
  if (!selectedLot.value?.lotId) return

  workSaving.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (selectedLot.value.auctionId) params.set('auction_id', selectedLot.value.auctionId)
    const workspace = await fetchJson<LotWorkspaceResponse>(
      `/api/v1/auctions/${selectedLot.value.source}/lots/${encodeURIComponent(selectedLot.value.lotId)}/workspace?${params.toString()}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildWorkPayload()),
      },
    )
    selectedWorkspace.value = workspace
    applyWorkspaceRow(workspace.row)
    hydrateWorkDraft(workspace.work_item)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось сохранить рабочие поля'
  } finally {
    workSaving.value = false
  }
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

function applyQuickFilters() {
  persistServerFilters()
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
    void loadLots()
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
        <span>Активные</span>
        <strong>{{ activeCount }}</strong>
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

    <section class="grid-surface" :aria-busy="loading">
      <div v-if="loading" class="loading-state" role="status" aria-live="polite">
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
        v-else
        ref="gridRef"
        :rows="rows"
        :columns="columns"
        :client-row-model-options="publicClientRowModelOptions"
        :toolbar-modules="toolbarModules"
        :theme="workspaceDataGridTheme"
        :is-cell-editable="isGridCellEditable"
        virtualization
        :advanced-filter="advancedFilterOptions"
        :column-layout="columnLayoutOptions"
        layout-mode="fill"
        :chrome="{ toolbarPlacement: 'integrated', density: 'compact', toolbarGap: 0, workspaceGap: 8 }"
        :history="{ controls: false }"
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
          <mark v-if="selectedLot.isNew">Новый</mark>
        </div>

        <div v-if="detailLoading" class="detail-live-status" role="status" aria-live="polite">
          <span class="detail-live-status__spinner" aria-hidden="true"></span>
          <span>Подгружаю live-данные с площадки</span>
        </div>

        <section class="detail-section detail-section--work">
          <div class="detail-section__header">
            <span class="eyebrow">Работа по лоту</span>
            <button class="secondary-button" type="button" :disabled="workSaving" @click="saveWorkItem">
              {{ workSaving ? 'Сохраняю' : 'Сохранить' }}
            </button>
          </div>
          <div class="work-grid">
            <label>
              <span>Решение</span>
              <select v-model="workDraft.decision_status">
                <option value="">Не выбрано</option>
                <option value="watch">Смотреть</option>
                <option value="calculate">Считать</option>
                <option value="inspection">Осмотр</option>
                <option value="bid">Заявка</option>
                <option value="reject">Отказ</option>
              </select>
            </label>
            <label>
              <span>Ответственный</span>
              <input v-model="workDraft.assignee" type="text" />
            </label>
            <label>
              <span>Рынок</span>
              <input v-model="workDraft.market_value" type="number" min="0" step="1000" />
            </label>
            <label>
              <span>Макс. покупка</span>
              <input v-model="workDraft.max_purchase_price" type="number" min="0" step="1000" />
            </label>
            <label>
              <span>Доставка</span>
              <input v-model="workDraft.delivery_cost" type="number" min="0" step="1000" />
            </label>
            <label>
              <span>Ремонт</span>
              <input v-model="workDraft.repair_cost" type="number" min="0" step="1000" />
            </label>
            <label class="work-grid__wide">
              <span>Комментарий</span>
              <textarea v-model="workDraft.comment" rows="3"></textarea>
            </label>
          </div>
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

        <dl class="detail-list">
          <template v-for="field in detailFields" :key="field.label">
            <dt>{{ field.label }}</dt>
            <dd>{{ field.value || 'Не указано' }}</dd>
          </template>
        </dl>

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
          <dl class="detail-list detail-list--dense">
            <template v-for="field in lotTextFields" :key="field.label">
              <dt>{{ field.label }}</dt>
              <dd>{{ field.value }}</dd>
            </template>
          </dl>
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

        <section class="detail-section detail-section--media">
          <span class="eyebrow">Медиа</span>
          <div v-if="detailLoading" class="detail-muted">Загрузка</div>
          <div v-else-if="detailImages.length" class="detail-images">
            <a
              v-for="(image, index) in detailImages"
              :key="image.url || image.name || `image-${index}`"
              :href="image.url || '#'"
              target="_blank"
              rel="noreferrer"
            >
              <img :src="image.url || ''" :alt="image.name || 'Изображение лота'" />
            </a>
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
          <div v-else class="detail-muted">Медиа не найдены</div>
        </section>

        <section class="detail-section">
          <span class="eyebrow">Файлы</span>
          <div v-if="detailLoading" class="detail-muted">Загрузка</div>
          <ul v-else-if="detailDocuments.length" class="detail-files">
            <li
              v-for="(document, index) in detailDocuments"
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
  </main>
</template>
