import { apiRequest } from '@/api/http'
import type { DecisionLevel, LotDecisionReport } from '@/types/decisionReport'

export type DecisionReportListKind = 'top' | 'bid_candidates' | 'inspect_candidates'

export type DecisionReportListParams = {
  kind?: DecisionReportListKind
  decisionLevel?: DecisionLevel
  profileHash?: string
  notificationShouldSend?: boolean
  limit?: number
}

export async function fetchLotDecisionReport(lotRecordId: number): Promise<LotDecisionReport> {
  return apiRequest<LotDecisionReport>(`/auctions/lots/${lotRecordId}/decision-report`, {
    auth: true,
  })
}

export async function fetchDecisionReports(params: DecisionReportListParams = {}): Promise<LotDecisionReport[]> {
  const query = new URLSearchParams()
  if (params.kind) query.set('kind', params.kind)
  if (params.decisionLevel) query.set('decision_level', params.decisionLevel)
  if (params.profileHash) query.set('profile_hash', params.profileHash)
  if (typeof params.notificationShouldSend === 'boolean') {
    query.set('notification_should_send', String(params.notificationShouldSend))
  }
  if (typeof params.limit === 'number') query.set('limit', String(params.limit))
  const suffix = query.toString()
  return apiRequest<LotDecisionReport[]>(`/auctions/decision-reports${suffix ? `?${suffix}` : ''}`, {
    auth: true,
  })
}
