export type AuctionGridHistoryRequest = {
  tableId: string
  userId: string | null
  sessionId: string | null
}

export type AuctionGridHistoryMutationResponse<TApiRow> = {
  datasetVersion: number
  updatedRows: Array<{
    id: string
    index: number
    row: TApiRow
  }>
}

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

const AUCTION_GRID_HISTORY_REQUEST: AuctionGridHistoryRequest = {
  tableId: 'auction-lots',
  userId: null,
  sessionId: null,
}

export async function requestAuctionGridUndo<TApiRow>(options: {
  postJson: PostJson
  signal?: AbortSignal
}) {
  const response = await options.postJson<AuctionGridHistoryMutationResponse<TApiRow>>(
    '/api/history/undo',
    AUCTION_GRID_HISTORY_REQUEST,
    options.signal,
  )
  return response
}

export async function requestAuctionGridRedo<TApiRow>(options: {
  postJson: PostJson
  signal?: AbortSignal
}) {
  const response = await options.postJson<AuctionGridHistoryMutationResponse<TApiRow>>(
    '/api/history/redo',
    AUCTION_GRID_HISTORY_REQUEST,
    options.signal,
  )
  return response
}
