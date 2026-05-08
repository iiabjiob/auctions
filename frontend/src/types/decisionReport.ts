export type DecisionLevel = 'ignore' | 'watch' | 'inspect' | 'calculate' | 'bid_candidate'

export type ActionRecommendation =
  | 'ignore'
  | 'monitor'
  | 'request_docs'
  | 'inspect'
  | 'calculate_max_bid'
  | 'prepare_bid'

export type LotDecisionReason = {
  code: string
  message: string
  source: string | null
}

export type LotDecisionRisk = {
  code: string
  message: string
  level: 'low' | 'medium' | 'high'
}

export type LotDecisionNextAction = {
  action: ActionRecommendation
  label: string
  deadline: string | null
}

export type LotEconomicsDecision = {
  current_price: string | number | null
  market_value: string | number | null
  expected_costs: string | number
  target_roi: string | number
  max_buy_price: string | number | null
  estimated_profit: string | number | null
  confidence: 'low' | 'medium' | 'high'
  missing_inputs: string[]
}

export type LotNotificationEligibility = {
  should_notify: boolean
  priority: 'low' | 'medium' | 'high' | 'urgent'
  reasons: string[]
  blockers: string[]
  dedupe_key: string
  cooldown_key: string
}

export type LotDecisionReport = {
  source: string
  auction_id: string
  lot_id: string
  record_id: number
  title: string | null
  source_title: string | null
  region: string | null
  current_price: string | null
  deadline: string | null
  rating_score: number
  rating_level: string
  profile_hash: string | null
  profile_fit_summary: string | null
  economics: LotEconomicsDecision | null
  decision_level: DecisionLevel
  recommendation: ActionRecommendation
  reasons: LotDecisionReason[]
  risks: LotDecisionRisk[]
  next_actions: LotDecisionNextAction[]
  generated_at: string
}
