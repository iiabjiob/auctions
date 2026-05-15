export const CATALOG_VIEWPORT_ROW_OVERSCAN = 18
export const CATALOG_VIEWPORT_COLUMN_OVERSCAN = 2
export const CATALOG_ROW_MODEL_PREFETCH_TRIGGER_VIEWPORT_FACTOR = 1
export const CATALOG_ROW_MODEL_PREFETCH_WINDOW_VIEWPORT_FACTOR = 1
export const CATALOG_ROW_MODEL_PREFETCH_MIN_BATCH_SIZE = 128
export const CATALOG_ROW_MODEL_PREFETCH_MAX_BATCH_SIZE = 256

export const catalogVirtualizationOptions = {
  rows: true,
  columns: true,
  rowOverscan: CATALOG_VIEWPORT_ROW_OVERSCAN,
  columnOverscan: CATALOG_VIEWPORT_COLUMN_OVERSCAN,
}

export const catalogRowModelPrefetchOptions = {
  enabled: true,
  triggerViewportFactor: CATALOG_ROW_MODEL_PREFETCH_TRIGGER_VIEWPORT_FACTOR,
  windowViewportFactor: CATALOG_ROW_MODEL_PREFETCH_WINDOW_VIEWPORT_FACTOR,
  minBatchSize: CATALOG_ROW_MODEL_PREFETCH_MIN_BATCH_SIZE,
  maxBatchSize: CATALOG_ROW_MODEL_PREFETCH_MAX_BATCH_SIZE,
  directionalBias: 'scroll-direction' as const,
}

export const catalogAdvancedFilterOptions = {
  buttonLabel: 'Расширенный фильтр',
  labels: {
    buttonLabel: 'Расширенный фильтр',
    eyebrow: 'Расширенный фильтр',
    title: 'Условия фильтрации',
    close: 'Закрыть',
    appliedEyebrow: 'Применено к таблице',
    appliedTitle: 'Текущие фильтры',
    resetAllFilters: 'Сбросить все фильтры',
    noFiltersApplied: 'Фильтры не применены',
    joinLabel: 'Связка',
    joinAriaLabel: 'Логическая связка',
    columnLabel: 'Колонка',
    columnAriaLabel: 'Колонка',
    operatorLabel: 'Условие',
    operatorAriaLabel: 'Условие фильтра',
    valueLabel: 'Значение',
    valuePlaceholder: 'Значение',
    valueAriaLabel: 'Значение условия',
    clearClause: 'Очистить',
    removeClause: 'Удалить',
    addClause: 'Добавить условие',
    cancel: 'Отмена',
    apply: 'Применить',
    activeSummaryPrefix: 'Расширенный',
    activeSummaryFallback: 'активен',
    valuesSummaryLabel: 'значения',
    blankValueLabel: '(Пустые)',
    betweenJoiner: 'и',
    notOperatorLabel: 'НЕ',
    operators: {
      contains: 'Содержит',
      in: 'В списке',
      equals: 'Равно',
      'not-equals': 'Не равно',
      'starts-with': 'Начинается с',
      'ends-with': 'Заканчивается на',
      gt: '>',
      gte: '>=',
      lt: '<',
      lte: '<=',
      between: 'между',
      'is-empty': 'пусто',
      'not-empty': 'не пусто',
      'is-null': 'нет значения',
      'not-null': 'есть значение',
    },
    joins: {
      and: 'И',
      or: 'ИЛИ',
    },
  },
}

export const catalogQuickFilter = {
  placeholder: 'Поиск: название, организатор, номер, регион',
  columns: ['lotName', 'organizer', 'auctionNumber', 'location', 'sourceTitle', 'analysisCategory'],
  mode: 'tokens' as const,
  applyMode: 'debounce' as const,
  debounceMs: 400,
}
