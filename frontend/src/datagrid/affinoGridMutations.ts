import type { AffinoDatasource } from '@affino/datagrid-server-adapters'
import type { DataGridRowId } from '@affino/datagrid-vue'
import type { AffinoPostJsonFetch } from './affinoPostJsonFetch'

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
  datasetVersion: number
  updatedRows: AffinoGridUpdatedRow<TApiRow>[]
}

export type AffinoGridHistoryMutationResponse<TApiRow> = {
  datasetVersion: number
  updatedRows: AffinoGridUpdatedRow<TApiRow>[]
}

export async function commitAffinoCellEdits<TApiRow, TRow>(options: {
  datasource: AffinoDatasource<TRow>
  fetchImpl: AffinoPostJsonFetch
  tableId: string
  baseVersion: number
  edits: readonly AffinoGridCellEdit[]
  signal?: AbortSignal
}) {
  if (!options.datasource.commitEdits) {
    throw new Error(`${options.tableId} datasource does not support edit commits`)
  }
  await options.datasource.commitEdits({
    revision: options.baseVersion,
    edits: groupCellEdits<TRow>(options.edits),
    signal: options.signal,
  })

  return readLastJson<AffinoGridEditResponse<TApiRow>>(
    options.fetchImpl,
    `/api/${options.tableId}/edits`,
    `${options.tableId} edit commit did not return a server response`,
  )
}

export async function requestAffinoHistoryMutation<TApiRow, TRow>(options: {
  datasource: AffinoDatasource<TRow>
  fetchImpl: AffinoPostJsonFetch
  action: 'undo' | 'redo'
}) {
  if (options.action === 'undo') {
    await options.datasource.undoHistoryStack()
  } else {
    await options.datasource.redoHistoryStack()
  }
  return readLastJson<AffinoGridHistoryMutationResponse<TApiRow>>(
    options.fetchImpl,
    `/api/history/${options.action}`,
    `Grid history ${options.action} did not return a server response`,
  )
}

function groupCellEdits<TRow>(
  edits: readonly AffinoGridCellEdit[],
): Parameters<NonNullable<AffinoDatasource<TRow>['commitEdits']>>[0]['edits'] {
  const patches = new Map<string, Record<string, unknown>>()
  for (const edit of edits) {
    const rowId = String(edit.rowId)
    const patch = patches.get(rowId) ?? {}
    patch[edit.columnId] = edit.value
    patches.set(rowId, patch)
  }
  return Array.from(patches, ([rowId, data]) => ({ rowId: rowId as DataGridRowId, data: data as Partial<TRow> }))
}

function readLastJson<T>(fetchImpl: AffinoPostJsonFetch, path: string, message: string) {
  const data = fetchImpl.lastJsonByPath.get(path)
  if (!data) {
    throw new Error(message)
  }
  return data as T
}
