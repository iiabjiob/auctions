import { apiRequest } from '@/api/http'
import type {
  UserInterestProfile,
  UserInterestProfileCreate,
  UserInterestProfileUpdate,
} from '@/types/userInterestProfiles'

export async function fetchUserInterestProfiles(): Promise<UserInterestProfile[]> {
  return apiRequest<UserInterestProfile[]>('/user-interest-profiles', {
    auth: true,
  })
}

export async function createUserInterestProfile(payload: UserInterestProfileCreate): Promise<UserInterestProfile> {
  return apiRequest<UserInterestProfile>('/user-interest-profiles', {
    method: 'POST',
    auth: true,
    body: JSON.stringify(payload),
  })
}

export async function updateUserInterestProfile(
  profileId: string,
  payload: UserInterestProfileUpdate,
): Promise<UserInterestProfile> {
  return apiRequest<UserInterestProfile>(`/user-interest-profiles/${profileId}`, {
    method: 'PATCH',
    auth: true,
    body: JSON.stringify(payload),
  })
}

export async function deleteUserInterestProfile(profileId: string): Promise<void> {
  await apiRequest<unknown>(`/user-interest-profiles/${profileId}`, {
    method: 'DELETE',
    auth: true,
  })
}
