export const PROCUREMENT_VIRTUALIZATION_OPTIONS = {
  rows: true,
  columns: true,
  rowOverscan: 18,
  columnOverscan: 2,
}

export const PROCUREMENT_PREFETCH_OPTIONS = {
  enabled: true,
  triggerViewportFactor: 1,
  windowViewportFactor: 1,
  minBatchSize: 96,
  maxBatchSize: 192,
  directionalBias: 'scroll-direction' as const,
}

export const PROCUREMENT_QUICK_FILTER = {
  placeholder: 'Поиск: номер, заказчик, ИНН, регион, предмет',
  columns: ['registryNumber', 'title', 'customerName', 'customerInn', 'deliveryRegion', 'category', 'assignee'],
  mode: 'tokens' as const,
  applyMode: 'debounce' as const,
  debounceMs: 400,
}

export const PROCUREMENT_ADVANCED_FILTER_OPTIONS = {
  buttonLabel: 'Фильтр',
}
