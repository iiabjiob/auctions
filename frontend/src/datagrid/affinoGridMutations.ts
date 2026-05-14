export type AffinoGridCellEdit = {
  rowId: string
  columnId: string
  value: unknown
}

export type AffinoGridUpdatedRow<TApiRow> = {
  id: string
  index: number
  row: TApiRow
}

export type AffinoGridEditResponse<TApiRow> = {
  operationId?: string | null
  datasetVersion: number
  updatedRows: AffinoGridUpdatedRow<TApiRow>[]
  rows?: AffinoGridUpdatedRow<TApiRow>[]
  affectedRows?: number
  affectedCells?: number
  canUndo?: boolean
  canRedo?: boolean
  latestUndoOperationId?: string | null
  latestRedoOperationId?: string | null
}

export type AffinoGridHistoryMutationResponse<TApiRow> = {
  operationId?: string | null
  action?: 'undo' | 'redo'
  datasetVersion: number
  updatedRows: AffinoGridUpdatedRow<TApiRow>[]
  rows?: AffinoGridUpdatedRow<TApiRow>[]
  affectedRows?: number
  affectedCells?: number
  canUndo?: boolean
  canRedo?: boolean
  latestUndoOperationId?: string | null
  latestRedoOperationId?: string | null
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

export async function commitAffinoCellEdits<TApiRow>(options: {
  postJson: PostJson
  tableId: string
  baseVersion: number
  edits: readonly AffinoGridCellEdit[]
  signal?: AbortSignal
}) {
  return await options.postJson<AffinoGridEditResponse<TApiRow>>(
    `/api/${options.tableId}/edits`,
    {
      baseVersion: options.baseVersion,
      edits: options.edits.map((edit) => ({
        rowId: edit.rowId,
        columnId: edit.columnId,
        value: edit.value,
      })),
    },
    options.signal,
  )
}

export async function requestAffinoHistoryMutation<TApiRow>(options: {
  postJson: PostJson
  tableId: string
  action: 'undo' | 'redo'
  signal?: AbortSignal
}) {
  return await options.postJson<AffinoGridHistoryMutationResponse<TApiRow>>(
    `/api/history/${options.action}`,
    {
      tableId: options.tableId,
    },
    options.signal,
  )
}
