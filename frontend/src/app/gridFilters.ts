import type { DataGridFilterSnapshot } from '@affino/datagrid-vue'

export function hasGridFilterModel(filterModel: DataGridFilterSnapshot | null | undefined) {
  if (!filterModel) return false
  const quickFilter = (filterModel as { quickFilter?: { query?: unknown } }).quickFilter
  return (
    hasMeaningfulColumnFilters(filterModel.columnFilters) ||
    hasMeaningfulAdvancedFilters(filterModel.advancedFilters) ||
    hasMeaningfulAdvancedExpression(filterModel.advancedExpression) ||
    (typeof quickFilter?.query === 'string' && quickFilter.query.trim().length > 0)
  )
}

export function hasMeaningfulColumnFilters(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false

  for (const payload of Object.values(value as Record<string, unknown>)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const filter = payload as Record<string, unknown>
    if (filter.kind === 'valueSet') {
      const tokens = filter.tokens
      if (Array.isArray(tokens) && tokens.length > 0) return true
      continue
    }
    if (filter.kind === 'predicate') {
      if (isMeaningfulAdvancedClause(filter)) return true
    }
  }
  return false
}

export function hasMeaningfulAdvancedFilters(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false

  for (const payload of Object.values(value as Record<string, unknown>)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const clauses = (payload as { clauses?: unknown }).clauses
    if (Array.isArray(clauses) && clauses.some(isMeaningfulAdvancedClause)) return true
  }
  return false
}

export function isMeaningfulAdvancedClause(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const clause = value as Record<string, unknown>
  const operator = typeof clause.operator === 'string' ? clause.operator.trim() : ''
  if (!operator) return false
  if (['isNull', 'notNull', 'is-null', 'not-null', 'isEmpty', 'notEmpty', 'is-empty', 'not-empty'].includes(operator)) {
    return true
  }
  const clauseValue = clause.value
  return clauseValue !== null && clauseValue !== undefined && String(clauseValue).trim().length > 0
}

export function hasMeaningfulAdvancedExpression(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false

  const expression = value as Record<string, unknown>
  if (expression.kind === 'condition') {
    return isMeaningfulAdvancedClause(expression)
  }
  if (expression.kind === 'group') {
    return Array.isArray(expression.children) && expression.children.some(hasMeaningfulAdvancedExpression)
  }
  if (expression.kind === 'not') {
    return hasMeaningfulAdvancedExpression(expression.child)
  }
  return false
}
