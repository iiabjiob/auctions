import { requestGridRedo, requestGridUndo } from './gridHistory'

type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

const AUCTION_LOTS_TABLE_ID = 'auction-lots'

export async function requestAuctionGridUndo<TApiRow>(options: {
  postJson: PostJson
  signal?: AbortSignal
}) {
  return requestGridUndo<TApiRow>({ ...options, tableId: AUCTION_LOTS_TABLE_ID })
}

export async function requestAuctionGridRedo<TApiRow>(options: {
  postJson: PostJson
  signal?: AbortSignal
}) {
  return requestGridRedo<TApiRow>({ ...options, tableId: AUCTION_LOTS_TABLE_ID })
}
