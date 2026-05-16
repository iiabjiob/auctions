import type { DataGridExposed, DataGridFocusAnchor, DataGridRestoreFocusAnchorOptions } from '@affino/datagrid-vue-app'

type FocusableDataGrid = Pick<DataGridExposed<unknown>, 'captureFocusAnchor' | 'restoreFocusAnchor'>

type DataGridRef = {
  value: FocusableDataGrid | null
}

const DEFAULT_RESTORE_OPTIONS: DataGridRestoreFocusAnchorOptions = {
  preventScroll: true,
  scrollIntoView: true,
  retries: 8,
}

export const AUCTION_GRID_FOCUS_ANCHOR_STORAGE_KEY = 'auction-grid-focus-anchor-v1'
export const PROCUREMENT_GRID_FOCUS_ANCHOR_STORAGE_KEY = 'procurement-grid-focus-anchor-v1'

export function persistGridFocusAnchor(gridRef: DataGridRef, storageKey: string) {
  const anchor = gridRef.value?.captureFocusAnchor({
    includeSelection: true,
    includeRowSelection: true,
  })
  if (!anchor) return false
  return writeStoredGridFocusAnchor(storageKey, anchor)
}

export async function restoreStoredGridFocusAnchor(
  gridRef: DataGridRef,
  storageKey: string,
  options: DataGridRestoreFocusAnchorOptions = DEFAULT_RESTORE_OPTIONS,
) {
  const anchor = readStoredGridFocusAnchor(storageKey)
  if (!anchor) return false
  try {
    return await gridRef.value?.restoreFocusAnchor(anchor, options) ?? false
  } catch {
    return false
  }
}

export function registerGridFocusPersistence(gridRef: DataGridRef, storageKey: string) {
  const save = () => {
    persistGridFocusAnchor(gridRef, storageKey)
  }
  const saveOnHidden = () => {
    if (document.visibilityState === 'hidden') save()
  }

  window.addEventListener('pagehide', save)
  window.addEventListener('beforeunload', save)
  document.addEventListener('visibilitychange', saveOnHidden)

  return () => {
    save()
    window.removeEventListener('pagehide', save)
    window.removeEventListener('beforeunload', save)
    document.removeEventListener('visibilitychange', saveOnHidden)
  }
}

function readStoredGridFocusAnchor(storageKey: string): DataGridFocusAnchor | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return isGridFocusAnchor(parsed) ? parsed : null
  } catch {
    return null
  }
}

function writeStoredGridFocusAnchor(storageKey: string, anchor: DataGridFocusAnchor) {
  if (typeof window === 'undefined') return false
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(anchor))
    return true
  } catch {
    return false
  }
}

function isGridFocusAnchor(value: unknown): value is DataGridFocusAnchor {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<DataGridFocusAnchor>
  return candidate.version === 1
    && (candidate.rowId === null || typeof candidate.rowId === 'string' || typeof candidate.rowId === 'number')
    && (candidate.rowIndex === null || typeof candidate.rowIndex === 'number')
    && (candidate.columnKey === null || typeof candidate.columnKey === 'string')
    && (candidate.columnIndex === null || typeof candidate.columnIndex === 'number')
}
