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

export type AuctionServerGridFilters = {
  period: string
  source: string | null
  status: string | null
  analysis_color: string | null
  min_price: number | null
  max_price: number | null
  only_new: boolean
  shortlist: boolean
  min_rating: number | null
}

export type AuctionServerPullWindowRequest = {
  start: number
  end: number
  signal?: AbortSignal
  sortModel?: readonly DataGridSortState[]
  filterModel?: DataGridFilterSnapshot | null
  reason?: string
  priority?: string
}

export type AuctionServerPullWindowResult<TRow> = {
  rows: TRow[]
  entries: DataGridDataSourceRowEntry<TRow>[]
  total: number
  datasetVersion: number
  summary: AuctionServerGridSummary
  start: number
  end: number
}

export type AuctionServerDatasource<TApiRow, TRow> = DataGridDataSource<TRow> & {
  pullWindow(request: AuctionServerPullWindowRequest): Promise<AuctionServerPullWindowResult<TRow>>
}

type AuctionServerPullResponse<TApiRow> = {
  rows: Array<{
    id: string
    index: number
    row: TApiRow
  }>
  total: number
  datasetVersion: number
  summary?: AuctionServerGridSummary
}

export type AuctionServerGridSummary = {
  total: number
  newCount: number
  openApplicationsCount: number
  highRatingCount: number
}

type AuctionServerHistogramResponse = {
  columnId?: string
  entries: DataGridColumnHistogram
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>
type QueryRequestProjection = Pick<DataGridDataSourcePullRequest, 'range' | 'sortModel' | 'filterModel' | 'groupBy' | 'pagination'>

export type CreateAuctionServerDatasourceOptions<TApiRow, TRow> = {
  postJson: PostJson
  getFilters: () => AuctionServerGridFilters
  hasFilterModel: (filterModel: DataGridFilterSnapshot | null | undefined) => boolean
  mapRow: (row: TApiRow, rowRevision: number) => TRow
  allocateRowRevision: () => number
  onPullCompleted?: (result: {
    rows: TRow[]
    total: number
    datasetVersion: number
    summary: AuctionServerGridSummary
    rowRevision: number
    reason?: string
    priority?: string
  }) => void
}

export function createAuctionServerDatasource<TApiRow, TRow>(
  options: CreateAuctionServerDatasourceOptions<TApiRow, TRow>,
): AuctionServerDatasource<TApiRow, TRow> {
  async function pullWindow(request: AuctionServerPullWindowRequest): Promise<AuctionServerPullWindowResult<TRow>> {
    if (request.signal?.aborted) {
      throw new DOMException('Request aborted', 'AbortError')
    }

    const start = Math.max(0, Math.trunc(request.start))
    const inclusiveEnd = Math.max(start, Math.trunc(request.end))
    const serverQuery = normalizeAuctionServerQuery(
      {
        range: { start, end: inclusiveEnd },
        sortModel: request.sortModel,
        filterModel: request.filterModel,
      },
      options.hasFilterModel,
    )

    const payload = {
      ...options.getFilters(),
      ...mapAuctionServerQuery(serverQuery),
    }
    const data = await options.postJson<AuctionServerPullResponse<TApiRow>>(
      '/api/auction-lots/pull',
      payload,
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

    options.onPullCompleted?.({
      rows,
      total: data.total,
      datasetVersion: data.datasetVersion,
      summary: data.summary ?? emptyAuctionServerGridSummary(data.total),
      rowRevision,
      reason: request.reason,
      priority: request.priority,
    })

    return {
      rows,
      entries,
      total: data.total,
      datasetVersion: data.datasetVersion,
      summary: data.summary ?? emptyAuctionServerGridSummary(data.total),
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
    const serverQuery = normalizeAuctionServerQuery(request, options.hasFilterModel)
    const response = await options.postJson<AuctionServerHistogramResponse | DataGridColumnHistogram>(
      '/api/auction-lots/histogram',
      {
        ...options.getFilters(),
        columnId: request.columnId,
        options: request.options as Record<string, unknown>,
        sortModel: serverQuery.sortModel ?? [],
        filterModel: serverQuery.filterModel ?? null,
      },
      request.signal,
    )
    if (Array.isArray(response)) {
      return response
    }
    return (response as AuctionServerHistogramResponse).entries
  }

  return {
    pull,
    pullWindow,
    getColumnHistogram,
  }
}

function emptyAuctionServerGridSummary(total: number): AuctionServerGridSummary {
  return {
    total,
    newCount: 0,
    openApplicationsCount: 0,
    highRatingCount: 0,
  }
}

function normalizeAuctionServerQuery(
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

function mapAuctionServerQuery(query: DataGridServerQuery) {
  return {
    startRow: query.range.startRow,
    endRow: query.range.endRow,
    sortModel: query.sortModel ?? [],
    filterModel: query.filterModel ?? null,
  }
}
