<script setup lang="ts">
import { computed, h, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataGrid,
  defineDataGridCellClassResolver,
  defineDataGridColumns,
  defineDataGridStructuralRowActionHandler,
  type DataGridCellEditEvent,
  type DataGridCellClassResolver,
  type DataGridExposed,
  type DataGridHistoryProp,
  type DataGridStatePersistenceProp,
  type DataGridStructuralRowActionContext,
  type DataGridStructuralRowActionHandler,
} from '@affino/datagrid-vue-app'
import { useTabsController } from '@affino/tabs-vue'
import {
  fetchAnalysisConfig,
  updateAnalysisConfig,
  type AnalysisConfigSource,
} from '@/api/analysisConfig'
import type {
  AnalysisConfigResponse,
  OwnerScoringProfile,
  ScoringDimensionWeights,
} from '@/app/types'
import { workspaceDataGridTheme } from '@/theme/dataGridTheme'

defineProps<{
  bindings?: unknown
}>()

type AnalysisConfigDraftRule = {
  id: string
  rowId: string
  priority: number
  category: string
  keywords: string
}

type AnalysisConfigDictionaryGroup = 'exclude' | 'high' | 'medium' | 'category'

type AnalysisConfigDictionaryRow = {
  id: string
  rowId: string
  risk_group: AnalysisConfigDictionaryGroup
  term: string
}

type AnalysisConfigEditorSection = 'categories' | 'dictionaries'

type AnalysisConfigDraft = {
  categoryRules: AnalysisConfigDraftRule[]
  dictionaryRows: AnalysisConfigDictionaryRow[]
}

type AnalysisTabState = {
  config: AnalysisConfigResponse | null
  draft: AnalysisConfigDraft
  savedDraftSignature: string
  loaded: boolean
  loading: boolean
  saving: boolean
  error: string
}

type GridChangeEvent<TRow> = {
  snapshot?: {
    rowCount?: number
    groupBy?: unknown
  }
  patch?: {
    rowId: string | number
    data: Partial<TRow>
  }
}

const sourceHints: Record<AnalysisConfigSource, string> = {
  auction: 'Категории, исключения и юридический риск для банкротных торгов.',
  procurement: 'Категории и стоп-слова для закупок.',
}

const sourceTabLabels: Record<AnalysisConfigSource, string> = {
  auction: 'Аукционы',
  procurement: 'Тендеры',
}

const ACTIVE_SOURCE_STORAGE_KEY = 'analysis-config-active-source-v1'
const ACTIVE_EDITOR_SECTION_STORAGE_KEY_PREFIX = 'analysis-config-active-section-v1'

const route = useRoute()
const router = useRouter()
const initialSource = route.query.source === undefined ? readStoredSource() : parseSource(route.query.source)
const tabs = useTabsController<AnalysisConfigSource>(initialSource)
const activeSource = computed(() => tabs.state.value.value ?? initialSource)
let ruleSeed = 0

const states = reactive<Record<AnalysisConfigSource, AnalysisTabState>>({
  auction: createState(),
  procurement: createState(),
})

const activeEditorSections = reactive<Record<AnalysisConfigSource, AnalysisConfigEditorSection>>({
  auction: readStoredEditorSection('auction'),
  procurement: readStoredEditorSection('procurement'),
})

const activeState = computed(() => states[activeSource.value])
const activeEditorSection = computed(() => activeEditorSections[activeSource.value])
const isAuctionTab = computed(() => activeSource.value === 'auction')
const activeUpdatedAt = computed(() => activeState.value.config?.updated_at ?? null)
const activeLoading = computed(() => activeState.value.loading)
const activeSaving = computed(() => activeState.value.saving)
const activeError = computed(() => activeState.value.error)
const activeDescription = computed(() => sourceHints[activeSource.value])
const activeDirty = computed(() => serializeDraft(activeState.value.draft) !== activeState.value.savedDraftSignature)
const duplicateCategoryCount = computed(() => countDuplicateValues(activeState.value.draft.categoryRules.map((rule) => rule.category)))
const duplicateDictionaryTermCount = computed(() =>
  countDuplicateValues(activeState.value.draft.dictionaryRows.map((row) => `${row.risk_group}:${row.term}`)),
)
const hasPriorityConflicts = computed(() => hasDuplicatePriorities(activeState.value.draft.categoryRules))

const categoryGridRef = ref<DataGridExposed<AnalysisConfigDraftRule> | null>(null)
const dictionaryGridRef = ref<DataGridExposed<AnalysisConfigDictionaryRow> | null>(null)
let preserveCategoryPriorityOnNextGridChange = false

const gridHistory = {
  enabled: true,
  shortcuts: 'grid',
  controls: 'toolbar',
} satisfies DataGridHistoryProp

const categoryGridStatePersistence = computed(() => createGridStatePersistence(activeSource.value, 'categories'))
const dictionaryGridStatePersistence = computed(() => createGridStatePersistence(activeSource.value, 'dictionaries'))

const categoryCellClass = defineDataGridCellClassResolver<AnalysisConfigDraftRule>()((row, _rowIndex, column) => {
  const rowData = row.data as Partial<AnalysisConfigDraftRule> | undefined
  if (column.key === 'category' && isDuplicateCategory(rowData?.category, activeState.value.draft.categoryRules)) {
    return 'analysis-config-grid-cell--warning'
  }
  if (column.key === 'priority' && hasPriorityConflict(rowData?.priority, activeState.value.draft.categoryRules)) {
    return 'analysis-config-grid-cell--warning'
  }
  return null
})

const dictionaryCellClass = defineDataGridCellClassResolver<AnalysisConfigDictionaryRow>()((row, _rowIndex, column) => {
  const rowData = row.data as Partial<AnalysisConfigDictionaryRow> | undefined
  if (column.key === 'term' && isDuplicateDictionaryTerm(rowData, activeState.value.draft.dictionaryRows)) {
    return 'analysis-config-grid-cell--warning'
  }
  return null
})

const categoryColumns = defineDataGridColumns<AnalysisConfigDraftRule>()([
  {
    key: 'priority',
    label: 'Приоритет',
    dataType: 'number',
    initialState: { width: 96 },
    presentation: { align: 'right', headerAlign: 'right', format: { number: { locale: 'ru-RU', maximumFractionDigits: 0 } } },
    capabilities: { sortable: false, filterable: false, editable: true },
  },
  {
    key: 'category',
    label: 'Категория',
    initialState: { width: 220 },
    flex: 0.8,
    capabilities: { sortable: false, filterable: true, editable: true },
  },
  {
    key: 'keywords',
    label: 'Ключевые слова',
    initialState: { width: 520 },
    flex: 1.4,
    capabilities: { sortable: false, filterable: true, editable: true },
    cellRenderer: ({ row, displayValue }) => renderDelimitedCell(row?.keywords ?? displayValue),
  },
])

const dictionaryGroupLabels: Record<AnalysisConfigDictionaryGroup, string> = {
  exclude: 'Исключение',
  high: 'Высокий риск',
  medium: 'Средний риск',
  category: 'Категория риска',
}

const dictionaryGroupOptions = (Object.entries(dictionaryGroupLabels) as Array<[AnalysisConfigDictionaryGroup, string]>).map(
  ([value, label]) => ({ value, label }),
)

const dictionaryColumns = defineDataGridColumns<AnalysisConfigDictionaryRow>()([
  {
    key: 'risk_group',
    label: 'Группа',
    initialState: { width: 132 },
    presentation: { options: dictionaryGroupOptions },
    capabilities: { sortable: false, filterable: true, editable: true },
    cellRenderer: ({ row, displayValue }) => renderDictionaryGroupLabel(row?.risk_group ?? displayValue),
    groupCellRenderer: ({ group, rowNode }) =>
      renderDictionaryGroupHeader(group.value, group.childrenCount, rowNode.state.expanded, group.toggle),
  },
  {
    key: 'term',
    label: 'Термин / фраза',
    initialState: { width: 340 },
    flex: 1,
    capabilities: { sortable: false, filterable: true, editable: true },
  },
])

function createState(): AnalysisTabState {
  return {
    config: null,
    draft: createEmptyDraft(),
    savedDraftSignature: serializeDraft(createEmptyDraft()),
    loaded: false,
    loading: false,
    saving: false,
    error: '',
  }
}

function createEmptyDraft(): AnalysisConfigDraft {
  return {
    categoryRules: [],
    dictionaryRows: [],
  }
}

function createDraftRule(category = '', keywords: string[] = [], priority = 1): AnalysisConfigDraftRule {
  const id = createRowId('category')
  return {
    id,
    rowId: id,
    priority,
    category,
    keywords: keywords.join('; '),
  }
}

function createDictionaryRow(risk_group: AnalysisConfigDictionaryGroup = 'exclude', term = ''): AnalysisConfigDictionaryRow {
  const id = createRowId('dictionary')
  return {
    id,
    rowId: id,
    risk_group,
    term,
  }
}

function createRowId(prefix: string) {
  ruleSeed += 1
  return `${prefix}-${ruleSeed}`
}

function createGridStatePersistence(
  source: AnalysisConfigSource,
  section: AnalysisConfigEditorSection,
): DataGridStatePersistenceProp {
  return {
    key: `analysis-config-grid-state-v1:${source}:${section}`,
    storage: 'local',
    includeViewportPosition: false,
    restoreOnReady: true,
    debounceMs: 250,
  }
}

function applyConfigToDraft(source: AnalysisConfigSource, config: AnalysisConfigResponse) {
  const draft = states[source].draft
  draft.categoryRules = config.category_rules.map((rule, index) => createDraftRule(rule.category, rule.keywords, index + 1))
  draft.dictionaryRows = [
    ...config.exclusion_keywords.map((term) => createDictionaryRow('exclude', term)),
    ...config.legal_risk_rules.high_keywords.map((term) => createDictionaryRow('high', term)),
    ...config.legal_risk_rules.medium_keywords.map((term) => createDictionaryRow('medium', term)),
    ...config.legal_risk_rules.medium_categories.map((term) => createDictionaryRow('category', term)),
  ]
  states[source].savedDraftSignature = serializeDraft(draft)
}

function splitLines(value: unknown) {
  const seen = new Set<string>()
  return String(value ?? '')
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter((item) => {
      const normalized = item.toLowerCase()
      if (!normalized || seen.has(normalized)) return false
      seen.add(normalized)
      return true
    })
}

function buildPayload(source: AnalysisConfigSource) {
  const state = states[source]
  const config = state.config
  const dictionary = normalizeDictionaryRows(state.draft.dictionaryRows)
  return {
    category_rules: normalizeCategoryRules(state.draft.categoryRules)
      .map((rule) => ({
        category: rule.category.trim(),
        keywords: splitLines(rule.keywords),
      }))
      .filter((rule) => rule.category),
    exclusion_keywords: dictionary.exclude,
    legal_risk_rules: {
      high_keywords: dictionary.high,
      medium_keywords: dictionary.medium,
      medium_categories: dictionary.category,
    },
    owner_profile: config?.owner_profile ?? defaultOwnerProfile(),
    dimension_weights: config?.dimension_weights ?? defaultDimensionWeights(),
  }
}

function defaultOwnerProfile(): OwnerScoringProfile {
  return {
    target_regions: [],
    target_categories: [],
    min_budget: null,
    max_budget: null,
    minimum_roi: null,
    minimum_market_discount: null,
    excluded_terms: [],
    discouraged_terms: [],
    max_delivery_distance_km: null,
    allow_dismantling: true,
    legal_risk_tolerance: 'medium',
    require_documents: false,
    require_photos: false,
  }
}

function defaultDimensionWeights(): ScoringDimensionWeights {
  return {
    economics: 1,
    risk: 1,
    urgency: 1,
    data_quality: 1,
    operational_readiness: 1,
    owner_fit: 1,
    manual_intent: 1,
  }
}

function parseSource(value: unknown): AnalysisConfigSource {
  return value === 'procurement' ? 'procurement' : 'auction'
}

function parseEditorSection(value: unknown): AnalysisConfigEditorSection {
  return value === 'dictionaries' ? 'dictionaries' : 'categories'
}

function readStoredSource(): AnalysisConfigSource {
  return parseSource(readLocalStorageValue(ACTIVE_SOURCE_STORAGE_KEY))
}

function readStoredEditorSection(source: AnalysisConfigSource): AnalysisConfigEditorSection {
  return parseEditorSection(readLocalStorageValue(getEditorSectionStorageKey(source)))
}

function persistActiveSource(source: AnalysisConfigSource) {
  writeLocalStorageValue(ACTIVE_SOURCE_STORAGE_KEY, source)
}

function persistEditorSection(source: AnalysisConfigSource, section: AnalysisConfigEditorSection) {
  writeLocalStorageValue(getEditorSectionStorageKey(source), section)
}

function getEditorSectionStorageKey(source: AnalysisConfigSource) {
  return `${ACTIVE_EDITOR_SECTION_STORAGE_KEY_PREFIX}:${source}`
}

function readLocalStorageValue(key: string) {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeLocalStorageValue(key: string, value: string) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // localStorage can be unavailable in private modes; tab state is non-critical.
  }
}

async function syncRoute(source: AnalysisConfigSource) {
  if (parseSource(route.query.source) === source) return
  await router.replace({ query: { ...route.query, source } })
}

async function loadSourceConfig(source: AnalysisConfigSource, force = false) {
  const state = states[source]
  if (state.loading || (state.loaded && !force)) return
  state.loading = true
  state.error = ''
  try {
    const config = await fetchAnalysisConfig(source)
    state.config = config
    applyConfigToDraft(source, config)
    state.loaded = true
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Не удалось загрузить конфиг анализа.'
  } finally {
    state.loading = false
  }
}

async function saveSourceConfig(source: AnalysisConfigSource) {
  const state = states[source]
  syncRowsFromGrid('category')
  syncRowsFromGrid('dictionary')
  state.saving = true
  state.error = ''
  try {
    const config = await updateAnalysisConfig(source, buildPayload(source))
    state.config = config
    applyConfigToDraft(source, config)
    state.loaded = true
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Не удалось сохранить конфиг анализа.'
  } finally {
    state.saving = false
  }
}

function normalizeVisiblePriorities(rows: AnalysisConfigDraftRule[]) {
  return rows.map((row, index) => ({ ...coerceCategoryRule(row, index), priority: index + 1 }))
}

function normalizeCategoryRules(rows: AnalysisConfigDraftRule[]) {
  return [...rows]
    .map((rule, index) => coerceCategoryRule(rule, index))
    .filter((rule) => String(rule.category ?? '').trim() || splitLines(rule.keywords).length > 0)
    .sort((left, right) => normalizePriority(left.priority) - normalizePriority(right.priority))
    .map((rule, index) => ({ ...rule, priority: index + 1 }))
}

function normalizeDictionaryRows(rows: AnalysisConfigDictionaryRow[]) {
  const result: Record<AnalysisConfigDictionaryGroup, string[]> = {
    exclude: [],
    high: [],
    medium: [],
    category: [],
  }

  for (const row of rows) {
    const group = parseDictionaryGroup(row.risk_group)
    result[group].push(...splitLines(row.term))
  }

  return {
    exclude: dedupeValues(result.exclude),
    high: dedupeValues(result.high),
    medium: dedupeValues(result.medium),
    category: dedupeValues(result.category),
  }
}

function normalizePriority(value: unknown) {
  const priority = Number(value)
  return Number.isFinite(priority) && priority > 0 ? priority : Number.MAX_SAFE_INTEGER
}

function coerceCategoryRule(row: Partial<AnalysisConfigDraftRule> | undefined, index = 0): AnalysisConfigDraftRule {
  const id = String(row?.id ?? row?.rowId ?? createRowId('category'))
  const priority = normalizePriority(row?.priority)
  return {
    id,
    rowId: String(row?.rowId ?? id),
    priority: priority === Number.MAX_SAFE_INTEGER ? index + 1 : priority,
    category: String(row?.category ?? ''),
    keywords: String(row?.keywords ?? ''),
  }
}

function coerceDictionaryRow(row: Partial<AnalysisConfigDictionaryRow> | undefined): AnalysisConfigDictionaryRow {
  const id = String(row?.id ?? row?.rowId ?? createRowId('dictionary'))
  return {
    id,
    rowId: String(row?.rowId ?? id),
    risk_group: parseDictionaryGroup(row?.risk_group),
    term: String(row?.term ?? ''),
  }
}

function dedupeValues(values: string[]) {
  const seen = new Set<string>()
  return values.filter((value) => {
    const key = String(value ?? '').trim().toLowerCase()
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function serializeDraft(draft: AnalysisConfigDraft) {
  return JSON.stringify({
    categoryRules: normalizeCategoryRules(draft.categoryRules).map((rule) => ({
      category: String(rule.category ?? '').trim(),
      keywords: splitLines(rule.keywords),
    })),
    dictionary: normalizeDictionaryRows(draft.dictionaryRows),
  })
}

function serializeCategoryRows(rows: AnalysisConfigDraftRule[]) {
  return JSON.stringify(rows.map((row, index) => {
    const normalized = coerceCategoryRule(row, index)
    return {
      id: normalized.id,
      rowId: normalized.rowId,
      priority: normalized.priority,
      category: normalized.category,
      keywords: normalized.keywords,
    }
  }))
}

function serializeDictionaryRows(rows: AnalysisConfigDictionaryRow[]) {
  return JSON.stringify(rows.map((row) => {
    const normalized = coerceDictionaryRow(row)
    return {
      id: normalized.id,
      rowId: normalized.rowId,
      risk_group: normalized.risk_group,
      term: normalized.term,
    }
  }))
}

function countDuplicateValues(values: unknown[]) {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const value of values) {
    const key = String(value ?? '').trim().toLowerCase()
    if (!key) continue
    if (seen.has(key)) duplicates.add(key)
    seen.add(key)
  }
  return duplicates.size
}

function hasDuplicatePriorities(rows: AnalysisConfigDraftRule[]) {
  return countDuplicateValues(rows.map((row) => String(normalizePriority(row.priority))).filter((value) => value !== String(Number.MAX_SAFE_INTEGER))) > 0
}

function hasPriorityConflict(priority: unknown, rows: AnalysisConfigDraftRule[]) {
  const normalized = normalizePriority(priority)
  if (normalized === Number.MAX_SAFE_INTEGER) return false
  return rows.filter((row) => normalizePriority(row.priority) === normalized).length > 1
}

function isDuplicateCategory(category: unknown, rows: AnalysisConfigDraftRule[]) {
  const normalized = String(category ?? '').trim().toLowerCase()
  if (!normalized) return false
  return rows.filter((row) => String(row.category ?? '').trim().toLowerCase() === normalized).length > 1
}

function isDuplicateDictionaryTerm(row: Partial<AnalysisConfigDictionaryRow> | undefined, rows: AnalysisConfigDictionaryRow[]) {
  const normalized = String(row?.term ?? '').trim().toLowerCase()
  if (!normalized) return false
  const group = parseDictionaryGroup(row?.risk_group)
  return rows.filter((candidate) => candidate.risk_group === group && String(candidate.term ?? '').trim().toLowerCase() === normalized).length > 1
}

function parseDictionaryGroup(value: unknown): AnalysisConfigDictionaryGroup {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (['high', 'high_keywords', 'высокий риск', 'высокий', 'юридический высокий'].includes(normalized)) return 'high'
  if (['medium', 'medium_keywords', 'средний риск', 'средний', 'юридический средний'].includes(normalized)) return 'medium'
  if (['category', 'medium_categories', 'категория риска', 'категории риска', 'категория'].includes(normalized)) return 'category'
  return 'exclude'
}

function renderDictionaryGroupLabel(value: unknown) {
  return dictionaryGroupLabels[parseDictionaryGroup(value)]
}

function renderDictionaryGroupHeader(value: unknown, count: number, expanded: boolean, toggle: () => void) {
  const toggleGroup = (event: Event) => {
    event.preventDefault()
    event.stopPropagation()
    toggle()
  }
  const handleKeydown = (event: KeyboardEvent) => {
    if (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar') return
    toggleGroup(event)
  }

  return h(
    'span',
    {
      class: 'analysis-config-group-label',
      role: 'button',
      tabindex: 0,
      'aria-expanded': String(expanded),
      onClick: toggleGroup,
      onKeydown: handleKeydown,
    },
    [
      h('span', { class: 'analysis-config-group-label__caret', 'aria-hidden': 'true' }, expanded ? '▾' : '▸'),
      h('span', { class: 'analysis-config-group-label__title' }, renderDictionaryGroupLabel(value)),
      h('span', { class: 'analysis-config-group-label__count' }, String(count)),
    ],
  )
}

function renderDelimitedCell(value: unknown) {
  const parts = splitLines(String(value ?? ''))
  if (!parts.length) return ''
  return h(
    'span',
    { class: 'analysis-config-keyword-preview' },
    parts.map((part) => h('span', { class: 'analysis-config-keyword-preview__chip' }, part)),
  )
}

function syncRowsFromGrid(
  kind: 'category' | 'dictionary',
  event?: GridChangeEvent<AnalysisConfigDraftRule | AnalysisConfigDictionaryRow>,
  options: { normalizePriorities?: boolean } = {},
) {
  const state = activeState.value
  const refValue = kind === 'category' ? categoryGridRef.value : dictionaryGridRef.value
  const api = refValue?.getApi()

  if (!api) {
    applyGridPatch(kind, event)
    return
  }

  const snapshot = event?.snapshot ?? api.rows.getSnapshot()
  if (isGroupedGridSnapshot(snapshot)) {
    applyGridPatch(kind, event)
    return
  }

  const rowCount = api.rows.getCount()
  const rows = rowCount > 0
    ? api.rows.getRange({ start: 0, end: rowCount - 1 }).map((row) => row.data)
    : []

  if (kind === 'category') {
    const categoryRows = (rows as Partial<AnalysisConfigDraftRule>[]).map((row, index) => coerceCategoryRule(row, index))
    const nextRows = options.normalizePriorities ? normalizeVisiblePriorities(categoryRows) : categoryRows
    if (serializeCategoryRows(state.draft.categoryRules) !== serializeCategoryRows(nextRows)) {
      state.draft.categoryRules = nextRows
    }
    return
  }

  const dictionaryRows = (rows as Partial<AnalysisConfigDictionaryRow>[]).map((row) => coerceDictionaryRow(row))
  if (serializeDictionaryRows(state.draft.dictionaryRows) !== serializeDictionaryRows(dictionaryRows)) {
    state.draft.dictionaryRows = dictionaryRows
  }
}

function isGroupedGridSnapshot(snapshot: GridChangeEvent<unknown>['snapshot'] | undefined) {
  const groupBy = snapshot?.groupBy
  if (!groupBy) return false
  if (Array.isArray(groupBy)) return groupBy.length > 0
  if (typeof groupBy === 'object') {
    const fields = (groupBy as { fields?: unknown }).fields
    if (Array.isArray(fields)) return fields.length > 0
    return Object.keys(groupBy).length > 0
  }
  return true
}

function applyGridPatch(kind: 'category' | 'dictionary', event?: GridChangeEvent<AnalysisConfigDraftRule | AnalysisConfigDictionaryRow>) {
  const patch = event?.patch
  if (!patch) return
  if (kind === 'category') {
    activeState.value.draft.categoryRules = activeState.value.draft.categoryRules.map((row) =>
      row.id === String(patch.rowId) ? { ...row, ...(patch.data as Partial<AnalysisConfigDraftRule>) } : row,
    )
    return
  }
  activeState.value.draft.dictionaryRows = activeState.value.draft.dictionaryRows.map((row) =>
    row.id === String(patch.rowId)
      ? { ...row, ...(patch.data as Partial<AnalysisConfigDictionaryRow>), risk_group: parseDictionaryGroup((patch.data as Partial<AnalysisConfigDictionaryRow>).risk_group ?? row.risk_group) }
      : row,
  )
}

function handleCategoryCellEdit(event: DataGridCellEditEvent<AnalysisConfigDraftRule>) {
  preserveCategoryPriorityOnNextGridChange = true
  applyGridPatch('category', event)
}

function handleDictionaryCellEdit(event: DataGridCellEditEvent<AnalysisConfigDictionaryRow>) {
  applyGridPatch('dictionary', event)
}

const runCategoryStructuralRowAction = defineDataGridStructuralRowActionHandler<AnalysisConfigDraftRule>()((context) =>
  runStructuralRowAction('category', context),
)

const runDictionaryStructuralRowAction = defineDataGridStructuralRowActionHandler<AnalysisConfigDictionaryRow>()((context) =>
  runStructuralRowAction('dictionary', context),
)

const categoryCellClassForGrid = categoryCellClass as DataGridCellClassResolver<unknown>
const dictionaryCellClassForGrid = dictionaryCellClass as DataGridCellClassResolver<unknown>
const runCategoryStructuralRowActionForGrid =
  runCategoryStructuralRowAction as DataGridStructuralRowActionHandler<Record<string, unknown>>
const runDictionaryStructuralRowActionForGrid =
  runDictionaryStructuralRowAction as DataGridStructuralRowActionHandler<Record<string, unknown>>

function handleCategoryGridChange(event: unknown) {
  syncRowsFromGrid('category', event as GridChangeEvent<AnalysisConfigDraftRule | AnalysisConfigDictionaryRow>, {
    normalizePriorities: !preserveCategoryPriorityOnNextGridChange,
  })
  preserveCategoryPriorityOnNextGridChange = false
}

function handleDictionaryGridChange(event: unknown) {
  syncRowsFromGrid('dictionary', event as GridChangeEvent<AnalysisConfigDraftRule | AnalysisConfigDictionaryRow>)
}

function syncActiveGrid() {
  if (activeEditorSection.value === 'categories') {
    syncRowsFromGrid('category')
    return
  }
  syncRowsFromGrid('dictionary')
}

function runStructuralRowAction(
  kind: 'category' | 'dictionary',
  context: DataGridStructuralRowActionContext<AnalysisConfigDraftRule | AnalysisConfigDictionaryRow>,
) {
  syncRowsFromGrid(kind)
  if (context.action === 'delete-selected-rows') {
    const ids = new Set((context.selectedRowIds.length ? context.selectedRowIds : [context.rowId]).map(String))
    if (kind === 'category') {
      activeState.value.draft.categoryRules = normalizeVisiblePriorities(activeState.value.draft.categoryRules.filter((row) => !ids.has(row.id)))
    } else {
      activeState.value.draft.dictionaryRows = activeState.value.draft.dictionaryRows.filter((row) => !ids.has(row.id))
    }
    return true
  }

  const insertAfter = context.action === 'insert-row-below'
  const index = Math.max(0, context.rowIndex + (insertAfter ? 1 : 0))
  if (kind === 'category') {
    const rows = [...activeState.value.draft.categoryRules]
    rows.splice(index, 0, createDraftRule('', [], index + 1))
    activeState.value.draft.categoryRules = normalizeVisiblePriorities(rows)
    return true
  }

  const rows = [...activeState.value.draft.dictionaryRows]
  const group = (context.row?.data as AnalysisConfigDictionaryRow | undefined)?.risk_group ?? 'exclude'
  rows.splice(index, 0, createDictionaryRow(group))
  activeState.value.draft.dictionaryRows = rows
  return true
}

watch(
  () => route.query.source,
  (value) => {
    const next = parseSource(value)
    if (tabs.state.value.value !== next) {
      tabs.select(next)
    }
  },
  { immediate: true },
)

watch(
  activeSource,
  (source) => {
    persistActiveSource(source)
    void syncRoute(source)
    void loadSourceConfig(source)
  },
  { immediate: true },
)

function switchTab(source: AnalysisConfigSource) {
  syncActiveGrid()
  tabs.select(source)
}

function switchEditorSection(section: AnalysisConfigEditorSection) {
  if (activeEditorSection.value === section) return
  syncActiveGrid()
  activeEditorSections[activeSource.value] = section
  persistEditorSection(activeSource.value, section)
}
</script>

<template>
  <section class="route-page route-page--analysis" aria-labelledby="analysis-config-route-title">
    <header class="route-page__header">
      <div>
        <span class="eyebrow">Анализ</span>
        <h1 id="analysis-config-route-title">Конфигурация анализа</h1>
        <p>{{ activeDescription }}</p>
      </div>
      <div class="route-page__actions">
        <span v-if="activeDirty" class="analysis-config-dirty">Есть несохраненные изменения</span>
        <button
          class="primary-button"
          type="button"
          :disabled="activeLoading || activeSaving || !activeDirty"
          @click="void saveSourceConfig(activeSource)"
        >
          {{ activeSaving ? 'Сохраняю' : 'Сохранить' }}
        </button>
      </div>
    </header>

    <div class="analysis-config-tabs" role="tablist" aria-label="Вид анализа">
      <button
        v-for="option in (['auction', 'procurement'] as const)"
        :key="option"
        type="button"
        class="analysis-config-tabs__tab"
        :class="{ 'analysis-config-tabs__tab--active': tabs.isSelected(option) }"
        role="tab"
        :aria-selected="tabs.isSelected(option)"
        @click="switchTab(option)"
      >
        {{ sourceTabLabels[option] }}
      </button>
    </div>

    <div class="analysis-config-status">
      <p v-if="activeUpdatedAt" class="route-page__meta">
        Последнее обновление: {{ activeUpdatedAt }}
      </p>
      <p v-if="activeError" class="error-banner error-banner--inline">{{ activeError }}</p>
      <div v-if="duplicateCategoryCount || duplicateDictionaryTermCount || hasPriorityConflicts" class="analysis-config-warning">
        <span v-if="hasPriorityConflicts">Есть повторяющиеся приоритеты: при сохранении порядок будет нормализован.</span>
        <span v-if="duplicateCategoryCount">Повторяющиеся категории: {{ duplicateCategoryCount }}.</span>
        <span v-if="duplicateDictionaryTermCount">Повторяющиеся словарные термины: {{ duplicateDictionaryTermCount }}.</span>
      </div>
    </div>

    <div v-if="activeLoading" class="route-page__state">Загружаю актуальный конфиг анализа</div>
    <div v-else class="analysis-config-workspace">
      <div class="analysis-config-subtabs" role="tablist" aria-label="Раздел конфигурации">
        <button
          type="button"
          class="analysis-config-subtabs__tab"
          :class="{ 'analysis-config-subtabs__tab--active': activeEditorSection === 'categories' }"
          role="tab"
          :aria-selected="activeEditorSection === 'categories'"
          @click="switchEditorSection('categories')"
        >
          Правила категорий
        </button>
        <button
          type="button"
          class="analysis-config-subtabs__tab"
          :class="{ 'analysis-config-subtabs__tab--active': activeEditorSection === 'dictionaries' }"
          role="tab"
          :aria-selected="activeEditorSection === 'dictionaries'"
          @click="switchEditorSection('dictionaries')"
        >
          {{ isAuctionTab ? 'Юридические риски' : 'Словари анализа' }}
        </button>
      </div>

      <section
        v-if="activeEditorSection === 'categories'"
        class="analysis-config-section route-card analysis-config-section--categories analysis-config-section--single"
      >
        <div class="analysis-config-section__header">
          <div>
            <span class="eyebrow">Правила категорий</span>
            <p class="analysis-config-section__hint">Порядок важен: категория назначается по первому совпавшему правилу.</p>
          </div>
        </div>

        <div class="analysis-config-grid-shell analysis-config-grid-shell--categories">
          <DataGrid
            ref="categoryGridRef"
            :rows="activeState.draft.categoryRules"
            :columns="categoryColumns"
            :theme="workspaceDataGridTheme"
            row-height-mode="auto"
            :base-row-height="34"
            :cell-class="categoryCellClassForGrid"
            :history="gridHistory"
            :state-persistence="categoryGridStatePersistence"
            :placeholder-rows="{ count: 1, materializeOn: ['edit', 'paste'], createRowAt: () => createDraftRule('', [], activeState.draft.categoryRules.length + 1) }"
            :row-reorder="true"
            :row-selection="false"
            :row-index-menu="true"
            :run-structural-row-action="runCategoryStructuralRowActionForGrid"
            fill-handle
            range-move
            layout-mode="fill"
            :chrome="{ toolbarPlacement: 'integrated', density: 'compact', toolbarGap: 0, workspaceGap: 8 }"
            @cell-edit="handleCategoryCellEdit"
            @cell-change="handleCategoryGridChange"
          />
        </div>
      </section>

      <section
        v-else
        class="analysis-config-section analysis-config-section--dictionaries route-card analysis-config-section--single"
      >
        <div class="analysis-config-section__header">
          <div>
            <span class="eyebrow">{{ isAuctionTab ? 'Юридические риски' : 'Словари анализа' }}</span>
            <p class="analysis-config-section__hint">
              Группа "Исключение" сохраняется в {{ isAuctionTab ? 'исключения лотов' : 'стоп-слова тендеров' }}.
            </p>
          </div>
        </div>

        <div class="analysis-config-grid-shell analysis-config-grid-shell--dictionaries">
          <DataGrid
            ref="dictionaryGridRef"
            :rows="activeState.draft.dictionaryRows"
            :columns="dictionaryColumns"
            :theme="workspaceDataGridTheme"
            :base-row-height="28"
            :cell-class="dictionaryCellClassForGrid"
            :history="gridHistory"
            :state-persistence="dictionaryGridStatePersistence"
            :placeholder-rows="{ count: 1, materializeOn: ['edit', 'paste'], createRowAt: () => createDictionaryRow('exclude') }"
            :row-selection="false"
            :row-index-menu="true"
            :run-structural-row-action="runDictionaryStructuralRowActionForGrid"
            fill-handle
            range-move
            layout-mode="fill"
            :chrome="{ toolbarPlacement: 'integrated', density: 'compact', toolbarGap: 0, workspaceGap: 8 }"
            @cell-edit="handleDictionaryCellEdit"
            @cell-change="handleDictionaryGridChange"
          />
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.route-page--analysis {
  grid-template-rows: auto auto auto minmax(0, 1fr);
  height: 100%;
  overflow: hidden;
}

.analysis-config-tabs {
  display: flex;
  gap: 8px;
  margin: 0 28px;
  padding: 4px;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface-muted);
}

.analysis-config-tabs__tab {
  border: 0;
  border-radius: 12px;
  padding: 11px 18px;
  color: var(--color-text-muted);
  background: transparent;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease, box-shadow 120ms ease;
}

.analysis-config-tabs__tab--active {
  color: var(--color-text-strong);
  background: var(--color-surface);
  box-shadow: 0 6px 14px rgba(37, 52, 71, 0.08);
}

.analysis-config-status {
  display: grid;
  gap: 8px;
  min-height: 0;
  margin: 0 28px;
}

.analysis-config-status:empty {
  display: none;
}

.analysis-config-status .route-page__meta {
  padding: 0;
}

.analysis-config-workspace {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.analysis-config-subtabs {
  display: flex;
  gap: 8px;
  margin: 0 28px;
  padding: 3px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-muted);
}

.analysis-config-subtabs__tab {
  border: 0;
  border-radius: 9px;
  padding: 7px 11px;
  color: var(--color-text-muted);
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease, box-shadow 120ms ease;
}

.analysis-config-subtabs__tab--active {
  color: var(--color-text-strong);
  background: var(--color-surface);
  box-shadow: 0 6px 14px rgba(37, 52, 71, 0.08);
}

.analysis-config-dirty {
  align-self: center;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 600;
}

.analysis-config-warning {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #f1c96b;
  border-radius: 12px;
  color: #68450a;
  background: #fff7df;
  font-size: 13px;
}

.analysis-config-layout--grid,
.analysis-config-layout--compact.analysis-config-layout--grid {
  grid-template-columns: minmax(0, 1.25fr) minmax(380px, 0.75fr);
  align-items: stretch;
}

.analysis-config-layout--compact {
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.9fr);
}

.analysis-config-section__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.analysis-config-section--single {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  margin: 0 28px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.analysis-config-section--dictionaries {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.analysis-config-grid-shell {
  min-width: 0;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  overflow: hidden;
  background: var(--color-surface);
}

.analysis-config-grid-shell--dictionaries {
  min-height: 0;
}

:deep(.analysis-config-grid-cell--warning) {
  background: #fff1c7 !important;
}

:deep(.analysis-config-group-label) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  cursor: pointer;
  outline: none;
}

:deep(.analysis-config-group-label:focus-visible) {
  border-radius: 8px;
  box-shadow: 0 0 0 2px rgba(31, 143, 82, 0.16);
}

:deep(.analysis-config-group-label__caret) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  color: var(--color-accent);
  font-size: 12px;
  line-height: 1;
}

:deep(.analysis-config-group-label__title) {
  overflow: hidden;
  color: var(--color-text-strong);
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.analysis-config-group-label__count) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  min-height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  color: #31543f;
  background: #dcece2;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

:deep(.analysis-config-keyword-preview) {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 5px;
  max-width: 100%;
  padding: 3px 0;
  overflow: visible;
  vertical-align: middle;
  white-space: normal;
}

:deep(.analysis-config-keyword-preview__chip) {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 2px 7px;
  overflow: hidden;
  border-radius: 999px;
  color: #264534;
  background: #edf7ef;
  text-overflow: ellipsis;
  white-space: normal;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .analysis-config-tabs,
  .analysis-config-subtabs {
    flex-wrap: wrap;
  }

  .analysis-config-layout--grid,
  .analysis-config-layout--compact.analysis-config-layout--grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .analysis-config-warning {
    margin: 0;
  }

  .analysis-config-subtabs,
  .analysis-config-tabs,
  .analysis-config-section--single {
    margin: 0;
  }

}
</style>
