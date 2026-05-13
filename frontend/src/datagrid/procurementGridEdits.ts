export type ProcurementGridCellEdit = {
  rowId: string
  columnId: string
  value: unknown
}

export type ProcurementGridEditUpdatedRow<TApiRow> = {
  id: string
  index: number
  row: TApiRow
}

export type ProcurementGridEditResponse<TApiRow> = {
  datasetVersion: number
  updatedRows: ProcurementGridEditUpdatedRow<TApiRow>[]
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

const PROCUREMENT_GRID_NUMERIC_EDIT_COLUMNS = new Set([
  'quantity',
  'unitNmck',
  'bidSecurityAmount',
  'contractSecurityAmount',
  'prepaymentPercent',
  'fabricPrice',
  'fabricConsumptionPerUnit',
  'accessoriesCost',
  'sewingCost',
  'extraOperationsCost',
  'logisticsCost',
  'packagingCost',
  'defectReservePercent',
  'adminFotCost',
])

const PROCUREMENT_GRID_TEXT_EDIT_COLUMNS = new Set([
  'workflowStatus',
  'assignee',
  'comment',
  'finalDecision',
  'rejectionReason',
  'paymentTerms',
  'certificateRequirements',
  'productType',
  'fabricType',
  'vatMode',
])

export const PROCUREMENT_GRID_EDITABLE_COLUMN_IDS: ReadonlySet<string> = new Set([
  ...PROCUREMENT_GRID_NUMERIC_EDIT_COLUMNS,
  ...PROCUREMENT_GRID_TEXT_EDIT_COLUMNS,
  'documentationPresent',
])

export function isProcurementGridEditableColumnId(columnId: string) {
  return PROCUREMENT_GRID_EDITABLE_COLUMN_IDS.has(columnId)
}

export function buildProcurementGridCellEditsFromPatch(
  rowId: string,
  patch: Record<string, unknown>,
): ProcurementGridCellEdit[] {
  const edits: ProcurementGridCellEdit[] = []
  for (const [columnId, rawValue] of Object.entries(patch)) {
    if (!isProcurementGridEditableColumnId(columnId)) continue
    edits.push({
      rowId,
      columnId,
      value: normalizeProcurementGridEditValue(columnId, rawValue),
    })
  }
  return edits
}

export async function commitProcurementGridEdits<TApiRow>(options: {
  postJson: PostJson
  baseVersion: number
  edits: readonly ProcurementGridCellEdit[]
  signal?: AbortSignal
}) {
  return options.postJson<ProcurementGridEditResponse<TApiRow>>(
    '/api/procurement-lots/edits',
    {
      baseVersion: options.baseVersion,
      edits: options.edits,
    },
    options.signal,
  )
}

function normalizeProcurementGridEditValue(columnId: string, value: unknown) {
  if (PROCUREMENT_GRID_NUMERIC_EDIT_COLUMNS.has(columnId)) {
    if (value === '' || value === null || typeof value === 'undefined') return null
    if (typeof value === 'number') return Number.isFinite(value) ? value : null
    if (typeof value === 'string') {
      const parsed = Number(value.trim().replace(/\s+/g, '').replace(',', '.'))
      return Number.isFinite(parsed) ? parsed : null
    }
    return value
  }
  if (columnId === 'documentationPresent') {
    if (value === null || typeof value === 'undefined' || value === '') return null
    return Boolean(value)
  }
  if (PROCUREMENT_GRID_TEXT_EDIT_COLUMNS.has(columnId)) {
    return typeof value === 'string' ? value.trim() || null : value
  }
  return value
}
