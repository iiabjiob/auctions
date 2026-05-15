import type { ActionRecommendation, DecisionLevel } from '@/types/decisionReport'

type DateLike = Date | string | null

type LifecycleTooltipRow = {
  lastSeenAt: DateLike
  actualityCheckedAt: DateLike
}

type EnrichmentState = {
  claimed_at?: string | null
  claimed_by?: string | null
  requested_at?: string | null
  next_attempt_at?: string | null
}

type SyncWindowState = {
  next_sync_not_before?: DateLike
  next_sync_not_after?: DateLike
}

export function parseNumber(value: string | number | null) {
  if (value === null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function parseDateTime(value: DateLike) {
  if (!value) return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }
  if (typeof value === 'number') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }
  const normalized = value.trim()
  const russianDateTime = normalized.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?/)
  if (russianDateTime) {
    const [, day, month, year, hour = '0', minute = '0', second = '0'] = russianDateTime
    return new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second))
  }

  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value: DateLike) {
  if (!value) return ''
  if (value instanceof Date) return value.toLocaleString('ru-RU')

  const date = parseDateTime(value)
  return date ? date.toLocaleString('ru-RU') : value
}

export function formatLifecycleStatus(value: string | null | undefined) {
  const status = (value || '').trim().toLowerCase()
  if (!status) return 'Неизвестно'
  if (status === 'active') return 'Активен'
  if (status === 'expired') return 'Истек'
  if (status === 'stale') return 'Устарел'
  if (status === 'archived') return 'Архив'
  return value || 'Неизвестно'
}

export function lifecycleStatusTone(value: string | null | undefined) {
  const status = (value || '').trim().toLowerCase()
  if (status === 'active') return 'active'
  if (status === 'expired') return 'warning'
  if (status === 'stale') return 'warning'
  if (status === 'archived') return 'muted'
  return 'muted'
}

export function buildLifecycleStatusTooltip(row: LifecycleTooltipRow) {
  const details = [
    `Последнее наблюдение: ${formatDateTime(row.lastSeenAt) || 'нет данных'}`,
    `Проверка актуальности: ${formatDateTime(row.actualityCheckedAt) || 'нет данных'}`,
  ]
  return details.join('\n')
}

export function formatEnrichmentState(state: EnrichmentState | null | undefined) {
  if (!state) return 'Не запрошено'
  if (state.claimed_at) {
    return `В работе${state.claimed_by ? ` · ${state.claimed_by}` : ''}`
  }
  if (state.requested_at) {
    return state.next_attempt_at ? `В очереди до ${formatDateTime(state.next_attempt_at)}` : 'В очереди'
  }
  return 'Не запрошено'
}

export function formatSourceSyncWindow(source: SyncWindowState | null | undefined) {
  if (!source) return 'Нет данных'
  if (!source.next_sync_not_before && !source.next_sync_not_after) return 'Не запланировано'
  const windowStart = formatDateTime(source.next_sync_not_before ?? null)
  const windowEnd = formatDateTime(source.next_sync_not_after ?? null)
  if (windowStart && windowEnd) return `${windowStart} - ${windowEnd}`
  return windowStart || windowEnd || 'Не запланировано'
}

export function formatCurrency(value: number | null) {
  if (value === null || Number.isNaN(value)) return 'Не указана'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    currencyDisplay: 'symbol',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatApiMoney(value: string | number | null | undefined) {
  const parsed = parseNumber(value ?? null)
  return parsed === null ? '' : formatCurrency(parsed)
}

export function formatApiPercent(value: string | number | null | undefined) {
  const parsed = parseNumber(value ?? null)
  if (parsed === null) return ''
  return new Intl.NumberFormat('ru-RU', {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(parsed)
}

export function formatDecisionLevel(value: DecisionLevel) {
  return {
    ignore: 'Игнорировать',
    watch: 'Наблюдать',
    inspect: 'Осмотреть',
    calculate: 'Посчитать',
    bid_candidate: 'Кандидат на торги',
  }[value]
}

export function formatActionRecommendation(value: ActionRecommendation) {
  return {
    ignore: 'Игнорировать',
    monitor: 'Мониторить',
    request_docs: 'Запросить документы',
    inspect: 'Осмотреть лот',
    calculate_max_bid: 'Посчитать максимум',
    prepare_bid: 'Готовить заявку',
  }[value]
}
