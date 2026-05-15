export type DatasetPeriod = 'week' | 'month' | 'year'

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

export function clampDetailPaneWidth(
  value: number,
  options: { minWidth?: number; maxWidth?: number } = {},
) {
  const minWidth = options.minWidth ?? 420
  const maxWidth = options.maxWidth ?? 980
  return Math.min(maxWidth, Math.max(minWidth, value))
}

export function readStoredDetailPaneWidth(
  storageKey: string,
  options: { defaultWidth?: number; minWidth?: number; maxWidth?: number } = {},
) {
  const defaultWidth = options.defaultWidth ?? 720
  const stored = window.localStorage.getItem(storageKey)
  if (!stored) return defaultWidth

  const parsed = Number(stored)
  return Number.isFinite(parsed) ? clampDetailPaneWidth(parsed, options) : defaultWidth
}

export function saveDetailPaneWidth(storageKey: string, value: number) {
  window.localStorage.setItem(storageKey, String(Math.round(value)))
}

export function isDatasetPeriod(value: unknown): value is DatasetPeriod {
  return value === 'week' || value === 'month' || value === 'year'
}

export function sanitizeServerFilters(
  value: Partial<ServerQuickFiltersState> | null | undefined,
  defaults: ServerQuickFiltersState,
): ServerQuickFiltersState {
  const hasPeriod = isDatasetPeriod(value?.period)
  const period: DatasetPeriod = hasPeriod ? (value.period as DatasetPeriod) : defaults.period
  const source = hasPeriod && typeof value?.source === 'string' && value.source.trim() === 'tbankrot' ? 'tbankrot' : defaults.source
  const analysisColor = typeof value?.analysisColor === 'string' ? value.analysisColor : defaults.analysisColor
  const status = typeof value?.status === 'string' ? value.status : defaults.status
  const minPrice = typeof value?.minPrice === 'string' ? value.minPrice : defaults.minPrice
  const maxPrice = typeof value?.maxPrice === 'string' ? value.maxPrice : defaults.maxPrice
  const onlyNew = value?.onlyNew === true
  const shortlist = value?.shortlist === true
  const minRating = Number.isFinite(value?.minRating)
    ? Math.min(100, Math.max(0, Number(value?.minRating)))
    : defaults.minRating
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

export function readStoredServerFilters(
  storageKey: string,
  defaults: ServerQuickFiltersState,
) {
  const stored = window.localStorage.getItem(storageKey)
  if (!stored) return { ...defaults }

  try {
    return sanitizeServerFilters(JSON.parse(stored) as Partial<ServerQuickFiltersState>, defaults)
  } catch {
    return { ...defaults }
  }
}

export function persistServerFilters(
  storageKey: string,
  filters: Partial<ServerQuickFiltersState> | null | undefined,
  defaults: ServerQuickFiltersState,
) {
  window.localStorage.setItem(storageKey, JSON.stringify(sanitizeServerFilters(filters, defaults)))
}

export function sanitizeGridColumnWidths(value: unknown): GridColumnWidthsState {
  if (!value || typeof value !== 'object') return {}

  const widths: GridColumnWidthsState = {}
  for (const [key, width] of Object.entries(value as Record<string, unknown>)) {
    if (!key.trim()) continue
    widths[key] = Number.isFinite(width) ? Math.max(0, Math.trunc(width as number)) : null
  }
  return widths
}

export function readStoredGridColumnWidths(storageKey: string): GridColumnWidthsState {
  const stored = window.localStorage.getItem(storageKey)
  if (!stored) return {}

  try {
    return sanitizeGridColumnWidths(JSON.parse(stored))
  } catch {
    return {}
  }
}

export function sanitizeGridSavedView(
  savedView: any,
  options: { dropSort?: boolean } = {},
): any {
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
      columns: {
        ...savedView.state.columns,
      },
    },
  }
}
