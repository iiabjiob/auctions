export type LotScoringProfilePayload = {
  profile_identifier?: string | null
  target_regions?: string[]
  target_categories?: string[]
  budget_min?: string | number | null
  budget_max?: string | number | null
  minimum_roi?: string | number | null
  minimum_discount?: string | number | null
  allowed_legal_risks?: string[]
  max_distance_km?: string | number | null
  stop_words?: string[]
  desired_keywords?: string[]
  strategy?: 'conservative' | 'balanced' | 'aggressive'
  weights?: Record<string, string | number>
}

export type UserInterestProfile = {
  id: string
  owner_user_id: string
  name: string
  profile_payload: LotScoringProfilePayload
  min_rating: number
  notification_priority_threshold: 'urgent' | 'high' | 'medium' | 'low' | null
  telegram_enabled: boolean
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export type UserInterestProfileCreate = {
  name: string
  profile_payload: LotScoringProfilePayload
  min_rating?: number
  notification_priority_threshold?: 'urgent' | 'high' | 'medium' | 'low' | null
  telegram_enabled?: boolean
  is_active?: boolean
}

export type UserInterestProfileUpdate = Partial<UserInterestProfileCreate>
