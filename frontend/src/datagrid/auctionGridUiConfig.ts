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

export const catalogLoadingSkeletonColumns = [
  { key: 'ratingScore', label: 'Рейтинг', width: 96, placeholderWidth: '54%' },
  { key: 'analysisLabel', label: 'Сигнал', width: 176, placeholderWidth: '76%' },
  { key: 'analysisCategory', label: 'Категория', width: 168, placeholderWidth: '72%' },
  { key: 'isNew', label: 'Новый', width: 88, placeholderWidth: '42%' },
  { key: 'sourceTitle', label: 'Площадка', width: 120, placeholderWidth: '62%' },
  { key: 'auctionNumber', label: 'Аукцион', width: 120, placeholderWidth: '58%' },
  { key: 'publicationDate', label: 'Дата публикации', width: 160, placeholderWidth: '60%' },
  { key: 'lotNumber', label: 'Лот', width: 76, placeholderWidth: '46%' },
  { key: 'lotName', label: 'Наименование', width: 430, placeholderWidth: '88%' },
  { key: 'location', label: 'Локация', width: 220, placeholderWidth: '82%' },
  { key: 'initialPrice', label: 'Начальная цена', width: 150, placeholderWidth: '70%' },
  { key: 'price', label: 'Текущая цена', width: 150, placeholderWidth: '70%' },
  { key: 'minimumPrice', label: 'Мин. цена', width: 150, placeholderWidth: '64%' },
  { key: 'status', label: 'Статус', width: 170, placeholderWidth: '78%' },
  { key: 'organizer', label: 'Организатор', width: 240, placeholderWidth: '82%' },
  { key: 'applicationDeadline', label: 'Прием заявок до', width: 180, placeholderWidth: '68%' },
  { key: 'auctionDate', label: 'Дата торгов', width: 170, placeholderWidth: '66%' },
  { key: 'lastSeenAt', label: 'Последнее наблюдение', width: 190, placeholderWidth: '72%' },
  { key: 'lifecycleStatus', label: 'Актуальность', width: 148, placeholderWidth: '66%' },
] as const

export const catalogLoadingSkeletonRows = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] as const

export const catalogColumnMenuOptions = {
  trigger: 'button+contextmenu' as const,
  items: ['sort', 'group', 'pin', 'filter'],
  labels: {
    sort: 'Сортировка',
    group: 'Группировка',
    pin: 'Закрепление',
    filter: 'Фильтр по значениям',
    valueSearchPlaceholder: 'Поиск значений',
    selectedValuesSummary: 'Выбрано {selected} из {total}',
  },
  actions: {
    sortAsc: { label: 'По возрастанию' },
    sortDesc: { label: 'По убыванию' },
    clearSort: { label: 'Сбросить сортировку' },
    toggleGroup: { label: 'Группировать по колонке' },
    pinMenu: { label: 'Закрепить колонку' },
    pinLeft: { label: 'Слева' },
    pinRight: { label: 'Справа' },
    unpin: { label: 'Не закреплять' },
    clearFilter: { label: 'Сбросить фильтр' },
    addCurrentSelectionToFilter: { label: 'Добавить выделение в фильтр' },
    selectAllValues: { label: 'Выбрать все' },
    clearAllValues: { label: 'Очистить выбор' },
    applyFilter: { label: 'Применить' },
    cancelFilter: { label: 'Отмена' },
  },
}

export const catalogGridStatePersistence = {
  key: 'auction-grid-state-v1',
  storage: 'local' as const,
  includeViewportPosition: true,
  restoreOnReady: true,
  debounceMs: 300,
  setOptions: {
    dataSource: {
      atomic: true,
      resetViewportRange: { start: 0, end: 255 },
    },
  },
}
