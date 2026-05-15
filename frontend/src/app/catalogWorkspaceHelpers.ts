import type { DataGridFilterSnapshot, DataGridSortState } from '@affino/datagrid-vue'
import type { AuctionServerGridFilters } from '@/datagrid/auctionServerDatasource'
import { parseNumber } from './formatters'
import type { ServerQuickFiltersState } from './types'

export type GridViewportRange = { start: number; end: number }

export function resolveViewportRangeSize(range?: GridViewportRange | null) {
  return range && Number.isFinite(range.start) && Number.isFinite(range.end) ? Math.trunc(range.end - range.start + 1) : 0
}

export function resolveCatalogServerViewportSize(
  preferredRange?: GridViewportRange | null,
  snapshotRange?: GridViewportRange | null,
  options: { initialFetchSize: number; serverFetchLimit: number } = { initialFetchSize: 256, serverFetchLimit: 10_000 },
) {
  const range = preferredRange ?? snapshotRange
  const size = resolveViewportRangeSize(range)
  if (size > 1) {
    return Math.min(options.serverFetchLimit, Math.max(options.initialFetchSize, size))
  }
  return options.initialFetchSize
}

export function buildCatalogServerViewportRange(
  preferredRange?: GridViewportRange | null,
  snapshotRange?: GridViewportRange | null,
  options: { initialFetchSize: number; serverFetchLimit: number } = { initialFetchSize: 256, serverFetchLimit: 10_000 },
) {
  const size = resolveCatalogServerViewportSize(preferredRange, snapshotRange, options)
  return { start: 0, end: size - 1 }
}

export function buildAuctionServerGridFilters(filters: Pick<ServerQuickFiltersState, 'period' | 'includeArchived'>): AuctionServerGridFilters {
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

function parseFilterNumber(value: string) {
  const normalized = value.replace(',', '.').trim()
  if (!normalized) return null
  const parsed = parseNumber(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

export function buildCatalogFilterModel(filters: ServerQuickFiltersState): DataGridFilterSnapshot | null {
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

export function serializeCatalogFilterModel(filters: ServerQuickFiltersState) {
  return JSON.stringify(buildCatalogFilterModel(filters))
}

export function serializeCatalogQueryScope(filters: Pick<ServerQuickFiltersState, 'period' | 'includeArchived'>) {
  return JSON.stringify({
    period: filters.period,
    includeArchived: filters.includeArchived,
  })
}

export function resolveCatalogPullFilterModel(
  filterModel: DataGridFilterSnapshot | null | undefined,
  reason: string,
  snapshotFilterModel: DataGridFilterSnapshot | null | undefined,
) {
  if (filterModel && typeof filterModel === 'object') return filterModel ?? null
  if (reason === 'filter-change') return filterModel ?? null
  return snapshotFilterModel && typeof snapshotFilterModel === 'object' ? snapshotFilterModel : filterModel ?? null
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export function createAuthHeaders(accessToken: string | null | undefined) {
  if (!accessToken) {
    return new Headers()
  }

  return new Headers({
    Authorization: `Bearer ${accessToken}`,
  })
}

export function apiUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

export function isAbortLikeError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function isApiRequestStatus(error: unknown, status: number) {
  return error instanceof Error && 'status' in error && (error as { status?: unknown }).status === status
}

export function isSortOrFilterChangeReason(reason: string) {
  return reason === 'sort-change' || reason === 'filter-change'
}
