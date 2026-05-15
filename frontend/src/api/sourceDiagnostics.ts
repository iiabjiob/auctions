import { apiRequest } from './http'

export type SourceDiagnosticsRange = 'day' | 'week' | 'month' | '3months' | 'all'
export type SourceDiagnosticsKind = 'all' | 'auction' | 'procurement'

export type SourceDiagnosticsTotals = {
  request_count: number
  success_count: number
  error_count: number
  inbound_bytes: number
  outbound_bytes: number
  total_bytes: number
  average_duration_ms: number | null
}

export type SourceDiagnosticsBucket = {
  bucket_start: string
  request_count: number
  inbound_bytes: number
  outbound_bytes: number
  error_count: number
}

export type SourceDiagnosticsOperationBucket = {
  operation: string
  request_count: number
  inbound_bytes: number
  outbound_bytes: number
  average_duration_ms: number | null
}

export type SourceDiagnosticsStatusBucket = {
  status_code: number | null
  count: number
}

export type SourceDiagnosticsErrorBucket = {
  error_type: string
  count: number
  last_message: string | null
}

export type SourceDiagnosticsSource = {
  code: string
  kind: 'auction' | 'procurement'
  title: string
  website: string
  totals: SourceDiagnosticsTotals
  operations: SourceDiagnosticsOperationBucket[]
  status_codes: SourceDiagnosticsStatusBucket[]
  errors: SourceDiagnosticsErrorBucket[]
}

export type SourceDiagnosticsResponse = {
  range: SourceDiagnosticsRange
  generated_at: string
  from_at: string | null
  to_at: string
  totals: SourceDiagnosticsTotals
  sources: SourceDiagnosticsSource[]
  timeline: SourceDiagnosticsBucket[]
}

export function fetchSourceDiagnostics(
  range: SourceDiagnosticsRange,
  options?: {
    kind?: SourceDiagnosticsKind
    source?: string | null
  },
) {
  const params = new URLSearchParams({ range })
  if (options?.kind) params.set('kind', options.kind)
  if (options?.source) params.set('source', options.source)
  return apiRequest<SourceDiagnosticsResponse>(`/health/source-diagnostics?${params.toString()}`)
}
