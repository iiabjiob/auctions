export type GridHistoryRequest = {
  tableId: string
  userId: string | null
  sessionId: string | null
}

export type GridHistoryMutationResponse<TApiRow> = {
  datasetVersion: number
  updatedRows: Array<{
    id: string
    index: number
    row: TApiRow
  }>
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

export async function requestGridUndo<TApiRow>(options: {
  postJson: PostJson
  tableId: string
  signal?: AbortSignal
}) {
  return options.postJson<GridHistoryMutationResponse<TApiRow>>(
    '/api/history/undo',
    gridHistoryRequest(options.tableId),
    options.signal,
  )
}

export async function requestGridRedo<TApiRow>(options: {
  postJson: PostJson
  tableId: string
  signal?: AbortSignal
}) {
  return options.postJson<GridHistoryMutationResponse<TApiRow>>(
    '/api/history/redo',
    gridHistoryRequest(options.tableId),
    options.signal,
  )
}

function gridHistoryRequest(tableId: string): GridHistoryRequest {
  return {
    tableId,
    userId: null,
    sessionId: null,
  }
}
