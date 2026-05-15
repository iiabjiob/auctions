import { apiRequest } from './http'
import type {
  AnalysisConfigResponse,
  AnalysisConfigCategoryRule,
  AnalysisConfigLegalRiskRules,
  OwnerScoringProfile,
  ScoringDimensionWeights,
} from '@/app/types'

export type AnalysisConfigSource = 'auction' | 'procurement'

export type AnalysisConfigUpdatePayload = {
  category_rules: AnalysisConfigCategoryRule[]
  exclusion_keywords: string[]
  legal_risk_rules: AnalysisConfigLegalRiskRules
  owner_profile: OwnerScoringProfile
  dimension_weights: ScoringDimensionWeights
}

export function fetchAnalysisConfig(source: AnalysisConfigSource) {
  return apiRequest<AnalysisConfigResponse>(`/auctions/analysis-config?source=${encodeURIComponent(source)}`, {
    auth: true,
  })
}

export function updateAnalysisConfig(source: AnalysisConfigSource, payload: AnalysisConfigUpdatePayload) {
  return apiRequest<AnalysisConfigResponse>(`/auctions/analysis-config?source=${encodeURIComponent(source)}`, {
    auth: true,
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
