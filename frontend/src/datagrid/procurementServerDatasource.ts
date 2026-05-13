import type {
  DataGridColumnHistogram,
  DataGridDataSource,
  DataGridDataSourceColumnHistogramRequest,
  DataGridDataSourcePullRequest,
  DataGridDataSourcePullResult,
  DataGridDataSourceRowEntry,
  DataGridFilterSnapshot,
  DataGridRowId,
  DataGridSortState,
} from '@affino/datagrid-vue'
import {
  normalizeDataGridServerQuery,
  type DataGridServerQuery,
} from '@affino/datagrid-server-adapters'

export type ProcurementServerGridFilters = {
  source: string | null
  law: string | null
  status: string | null
  workflowStatus: string | null
  assignee: string | null
  category: string | null
  minPrice: number | null
  maxPrice: number | null
  minScore: number | null
  onlyNew: boolean
}

export type ProcurementServerGridSummary = {
  total: number
  newCount: number
  relevantCount: number
  highScoreCount: number
  decisionPendingCount: number
}

export type ProcurementServerPullWindowRequest = {
  start: number
  end: number
  signal?: AbortSignal
  sortModel?: readonly DataGridSortState[]
  filterModel?: DataGridFilterSnapshot | null
  reason?: string
  priority?: string
}

export type ProcurementServerPullWindowResult<TRow> = {
  rows: TRow[]
  entries: DataGridDataSourceRowEntry<TRow>[]
  total: number
  datasetVersion: number
  summary: ProcurementServerGridSummary
  start: number
  end: number
}

export type ProcurementServerDatasource<TApiRow, TRow> = DataGridDataSource<TRow> & {
  pullWindow(request: ProcurementServerPullWindowRequest): Promise<ProcurementServerPullWindowResult<TRow>>
}

type ProcurementServerPullResponse<TApiRow> = {
  rows: Array<{
    id: string
    index: number
    row: TApiRow
  }>
  total: number
  datasetVersion: number
  summary?: ProcurementServerGridSummary
}

type ProcurementServerHistogramResponse = {
  columnId?: string
  entries: DataGridColumnHistogram
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>
type QueryRequestProjection = Pick<DataGridDataSourcePullRequest, 'range' | 'sortModel' | 'filterModel' | 'groupBy' | 'pagination'>

export type CreateProcurementServerDatasourceOptions<TApiRow, TRow> = {
  postJson: PostJson
  getFilters: () => ProcurementServerGridFilters
  hasFilterModel: (filterModel: DataGridFilterSnapshot | null | undefined) => boolean
  mapRow: (row: TApiRow, rowRevision: number) => TRow
  allocateRowRevision: () => number
  onPullCompleted?: (result: {
    rows: TRow[]
    total: number
    datasetVersion: number
    summary: ProcurementServerGridSummary
    rowRevision: number
    reason?: string
    priority?: string
  }) => void
}

export function createProcurementServerDatasource<TApiRow, TRow>(
  options: CreateProcurementServerDatasourceOptions<TApiRow, TRow>,
): ProcurementServerDatasource<TApiRow, TRow> {
  async function pullWindow(request: ProcurementServerPullWindowRequest): Promise<ProcurementServerPullWindowResult<TRow>> {
    if (request.signal?.aborted) {
      throw new DOMException('Request aborted', 'AbortError')
    }

    const start = Math.max(0, Math.trunc(request.start))
    const inclusiveEnd = Math.max(start, Math.trunc(request.end))
    const serverQuery = normalizeProcurementServerQuery(
      {
        range: { start, end: inclusiveEnd },
        sortModel: request.sortModel,
        filterModel: request.filterModel,
      },
      options.hasFilterModel,
    )
    const data = await options.postJson<ProcurementServerPullResponse<TApiRow>>(
      '/api/procurement-lots/pull',
      {
        ...options.getFilters(),
        ...mapProcurementServerQuery(serverQuery),
      },
      request.signal,
    )

    if (request.signal?.aborted) {
      throw new DOMException('Request aborted', 'AbortError')
    }

    const rowRevision = options.allocateRowRevision()
    const rows = data.rows.map((entry) => options.mapRow(entry.row, rowRevision))
    const entries = rows.map((row, index) => ({
      index: data.rows[index]?.index ?? start + index,
      row,
      rowId: data.rows[index]?.id as DataGridRowId,
    }))
    const summary = data.summary ?? emptyProcurementServerGridSummary(data.total)
    options.onPullCompleted?.({
      rows,
      total: data.total,
      datasetVersion: data.datasetVersion,
      summary,
      rowRevision,
      reason: request.reason,
      priority: request.priority,
    })

    return {
      rows,
      entries,
      total: data.total,
      datasetVersion: data.datasetVersion,
      summary,
      start,
      end: inclusiveEnd,
    }
  }

  async function pull(request: DataGridDataSourcePullRequest): Promise<DataGridDataSourcePullResult<TRow>> {
    const result = await pullWindow({
      start: request.range.start,
      end: request.range.end,
      signal: request.signal,
      sortModel: request.sortModel,
      filterModel: request.filterModel,
      reason: request.reason,
      priority: request.priority,
    })
    return {
      rows: result.entries,
      total: result.total,
      datasetVersion: result.datasetVersion,
    }
  }

  async function getColumnHistogram(request: DataGridDataSourceColumnHistogramRequest): Promise<DataGridColumnHistogram> {
    const serverQuery = normalizeProcurementServerQuery(request, options.hasFilterModel)
    const response = await options.postJson<ProcurementServerHistogramResponse | DataGridColumnHistogram>(
      '/api/procurement-lots/histogram',
      {
        ...options.getFilters(),
        columnId: request.columnId,
        options: request.options as Record<string, unknown>,
        sortModel: serverQuery.sortModel ?? [],
        filterModel: hasNormalizedFilterModel(serverQuery.filterModel) ? serverQuery.filterModel : null,
      },
      request.signal,
    )
    if (Array.isArray(response)) return response
    return (response as ProcurementServerHistogramResponse).entries
  }

  return {
    pull,
    pullWindow,
    getColumnHistogram,
  }
}

function emptyProcurementServerGridSummary(total: number): ProcurementServerGridSummary {
  return {
    total,
    newCount: 0,
    relevantCount: 0,
    highScoreCount: 0,
    decisionPendingCount: 0,
  }
}

function normalizeProcurementServerQuery(
  request: Partial<QueryRequestProjection>,
  hasFilterModel: (filterModel: DataGridFilterSnapshot | null | undefined) => boolean,
) {
  return normalizeDataGridServerQuery({
    range: request.range ?? { start: 0, end: 0 },
    sortModel: request.sortModel ?? [],
    filterModel: hasFilterModel(request.filterModel) ? request.filterModel ?? null : null,
    groupBy: request.groupBy ?? null,
    pagination: request.pagination ?? { snapshot: null },
  } as DataGridDataSourcePullRequest)
}

function mapProcurementServerQuery(query: DataGridServerQuery) {
  return {
    startRow: query.range.startRow,
    endRow: query.range.endRow,
    sortModel: query.sortModel ?? [],
    filterModel: hasNormalizedFilterModel(query.filterModel) ? query.filterModel : null,
  }
}

function hasNormalizedFilterModel(filterModel: DataGridServerQuery['filterModel']) {
  if (!filterModel) return false
  const quickFilter = filterModel.quickFilter
  return (
    Object.keys(filterModel.columnFilters ?? {}).length > 0 ||
    Object.keys(filterModel.columnStyleFilters ?? {}).length > 0 ||
    Object.keys(filterModel.advancedFilters ?? {}).length > 0 ||
    Boolean(filterModel.advancedExpression) ||
    (typeof quickFilter?.query === 'string' && quickFilter.query.trim().length > 0)
  )
}
