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

export const PROCUREMENT_LOADING_SKELETON_COLUMNS = [
  { key: 'score', label: 'Рейтинг', placeholderWidth: '42px' },
  { key: 'source', label: 'Площадка', placeholderWidth: '72px' },
  { key: 'registryNumber', label: 'Закупка', placeholderWidth: '120px' },
  { key: 'title', label: 'Наименование', placeholderWidth: '280px' },
  { key: 'customerName', label: 'Заказчик', placeholderWidth: '180px' },
  { key: 'initialPrice', label: 'Начальная цена', placeholderWidth: '96px' },
  { key: 'applicationDeadline', label: 'Прием заявок до', placeholderWidth: '120px' },
] as const

export const PROCUREMENT_LOADING_SKELETON_ROWS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] as const

export const PROCUREMENT_COLUMN_LAYOUT_OPTIONS = {
  buttonLabel: 'Колонки',
}

export const PROCUREMENT_COLUMN_MENU_OPTIONS = {
  trigger: 'button+contextmenu' as const,
  items: ['sort', 'pin', 'filter'],
  labels: {
    sort: 'Сортировка',
    pin: 'Закрепление',
    filter: 'Фильтр',
    valueSearchPlaceholder: 'Поиск значений',
    selectedValuesSummary: 'Выбрано {selected} из {total}',
  },
}

export const PROCUREMENT_LOADING_SKELETON_TEMPLATE = PROCUREMENT_LOADING_SKELETON_COLUMNS.map((column) => column.placeholderWidth).join(' ')
