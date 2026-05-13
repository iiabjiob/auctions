 ## [] Slice 1: Atomic Saved View Apply

  Контекст:
  В package уже есть API для atomic saved-view/state apply без ручного pauseBackpressure/RAF/flush choreography.

  Задача:
  - Найди в реальном App.vue workaround-и:
    - applyGridSavedViewWithoutIntermediatePulls
    - manual pauseBackpressure/resumeBackpressure/flushBackpressure
    - manual setViewportRange reset around saved view/query change
    - nextTick/requestAnimationFrame choreography для saved view apply
  - Замени на package API для atomic apply saved view/state.
  - Удали ставшие ненужными helpers.

  Acceptance:
  - apply saved preset/grid_view не делает intermediate pulls.
  - sort/filter/group/pivot changes корректно reset server viewport.
  - viewport/query dimming поведение не ломается.
  - app type-check/build passes.

  Validation:
  - app type-check/build.
  - smoke: apply preset, reload page, apply another preset, verify backend pulls only final query.

  ## [] Slice 2: External Row Updates

  Контекст:
  В package уже есть explicit API для external row updates:
  api.rows.applyExternalUpdates(...)

  Задача:
  - Найди workaround-и:
    - patchGridRowsInDataGrid
    - suppressGridCellChangeDepth
    - suppressGridCommitEditsDepth
    - api.rows.applyEdits(... emit:false/reapply:false) для server/live updates
  - Замени external polling/live updates на api.rows.applyExternalUpdates.
  - User edits не трогай: они должны продолжать идти через normal edit/commit/history flow.

  Acceptance:
  - Live/poll updates обновляют loaded rows.
  - User cell edits still call commitEdits/history.
  - No synthetic user cell-change events from external updates.
  - Optimistic rollback/conflict behavior не ломается.

  Validation:
  - app type-check/build.
  - smoke: edit cell, receive external update, rollback/conflict path.

  ## [] Slice 3: Focus Anchor Integration

  Контекст:
  В package уже есть:
  - captureFocusAnchor(options?)
  - restoreFocusAnchor(anchor, options?)

  Задача:
  - Удали локальные DOM focus helpers:
    - getGridRootElement
    - escapeGridSelectorValue
    - captureGridFocusAnchor
    - remapGridSelectionSnapshot
    - findGridFocusTarget
    - focusGridElement
    - restoreGridFocus / nested RAF logic
  - Замени open/close/refresh detail pane focus flow на package focus anchor API.

  Acceptance:
  - Opening detail pane captures current grid focus/selection.
  - Closing/refreshing details restores focus/selection.
  - Missing/refetched row handled gracefully.
  - No unwanted viewport jump.

  Validation:
  - app type-check/build.
  - smoke: open lot details, refresh details, close, focus returns to same grid cell.

  ## [] Slice 4: Filter Normalization Integration

  Контекст:
  В package уже есть column filter hooks:
  - filter.valueSet
  - filter.normalizeValue
  - normalizeDataGridAppFilterModel / normalizeDataGridAppUnifiedStateFilters internally used by DataGrid.

  Задача:
  - Перенеси app-local filter workaround-и в column config:
    - PERCENT_FILTER_COLUMN_KEYS
    - VALUE_FILTER_COLUMN_KEYS
    - sanitizeGridValueSetFilters
    - sanitizePercentPredicatePayload*
    - sanitizePercentAdvancedFilters
    - sanitizePercentAdvancedExpression
  - Для percent columns (`roiValue`, `marketDiscount`) добавь `filter.normalizeValue`, чтобы UI percent превращался в backend decimal.
  - Для columns без backend valueSet support добавь `filter: { valueSet: false }`.

  Acceptance:
  - Backend получает decimal values для percent filters.
  - Unsupported valueSet filters удаляются package layer.
  - Saved presets/grid_view с legacy snapshots продолжают применяться.
  - App больше не мутирует DataGridFilterSnapshot вручную.

  Validation:
  - app type-check/build.
  - smoke: percent filter, save preset, reload/apply preset, inspect backend query.

  ## [] Slice 5: Type Ergonomics Integration

  Контекст:
  В package добавлены:
  - defineDataGridColumns<GridLotRow>()([...])
  - defineDataGridColumnMenu({...})

  Задача:
  - Убери casts:
    - typedColumns as unknown as DataGridAppColumnInput[]
    - columnMenuOptions as unknown as DataGridColumnMenuProp
  - Объяви columns через defineDataGridColumns<GridLotRow>().
  - Объяви columnMenuOptions через defineDataGridColumnMenu.
  - Не меняй runtime config semantics.

  Acceptance:
  - Нет `as unknown as` для datagrid columns/menu.
  - Columns still infer row type in renderers/interactions.
  - Column menu config accepts Object.fromEntries columns map без cast.
  - app type-check/build passes.

  Validation:
  - app type-check/build.
  - smoke: grid renders, column menu opens, sort/filter/pin still work.