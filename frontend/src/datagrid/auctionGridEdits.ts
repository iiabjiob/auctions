export type AuctionGridCellEdit = {
  rowId: string
  columnId: string
  value: unknown
}

export type AuctionGridEditUpdatedRow<TApiRow> = {
  id: string
  index: number
  row: TApiRow
}

export type AuctionGridEditResponse<TApiRow> = {
  datasetVersion: number
  updatedRows: AuctionGridEditUpdatedRow<TApiRow>[]
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

const AUCTION_GRID_NUMERIC_EDIT_COLUMNS = new Set([
  'marketValue',
  'platformFee',
  'deliveryCost',
  'dismantlingCost',
  'repairCost',
  'storageCost',
  'legalCost',
  'otherCosts',
  'targetProfit',
])

export const AUCTION_GRID_EDITABLE_COLUMN_IDS: ReadonlySet<string> = new Set([
  ...AUCTION_GRID_NUMERIC_EDIT_COLUMNS,
  'excludeFromAnalysis',
  'exclusionReason',
])

export function isAuctionGridEditableColumnId(columnId: string) {
  return AUCTION_GRID_EDITABLE_COLUMN_IDS.has(columnId)
}

export function buildAuctionGridCellEditsFromPatch(
  rowId: string,
  patch: Record<string, unknown>,
): AuctionGridCellEdit[] {
  const edits: AuctionGridCellEdit[] = []
  for (const [columnId, rawValue] of Object.entries(patch)) {
    if (!isAuctionGridEditableColumnId(columnId)) continue
    edits.push({
      rowId,
      columnId,
      value: normalizeAuctionGridEditValue(columnId, rawValue),
    })
  }
  return edits
}

export async function commitAuctionGridEdits<TApiRow>(options: {
  postJson: PostJson
  baseVersion: number
  edits: readonly AuctionGridCellEdit[]
  signal?: AbortSignal
  debug?: boolean
}) {
  if (options.debug) {
    console.debug('[auction-grid] edits', {
      baseVersion: options.baseVersion,
      editCount: options.edits.length,
    })
  }

  const response = await options.postJson<AuctionGridEditResponse<TApiRow>>(
    '/api/auction-lots/edits',
    {
      baseVersion: options.baseVersion,
      edits: options.edits,
    },
    options.signal,
  )

  if (options.debug) {
    console.debug('[auction-grid] edits datasetVersion', response.datasetVersion)
  }
  return response
}

function normalizeAuctionGridEditValue(columnId: string, value: unknown) {
  if (AUCTION_GRID_NUMERIC_EDIT_COLUMNS.has(columnId)) {
    if (value === '' || value === null || typeof value === 'undefined') return null
    if (typeof value === 'number') return Number.isFinite(value) ? value : null
    if (typeof value === 'string') {
      const parsed = Number(value.trim().replace(/\s+/g, '').replace(',', '.'))
      return Number.isFinite(parsed) ? parsed : null
    }
    return value
  }
  if (columnId === 'excludeFromAnalysis') {
    return Boolean(value)
  }
  if (columnId === 'exclusionReason') {
    return typeof value === 'string' ? value.trim() || null : value
  }
  return value
}
