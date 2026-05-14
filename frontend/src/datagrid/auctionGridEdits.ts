export type AuctionGridCellEdit = {
  rowId: string
  columnId: string
  value: unknown
}

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
