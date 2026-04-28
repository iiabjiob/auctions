export type AuthUser = {
  id: string
  email: string
  full_name: string
}

export type AuthSession = {
  access_token: string
  token_type: string
  user: AuthUser
}

export type AuthPublicConfig = {
  default_user_enabled: boolean
  default_user_email: string | null
}

export type LoginInput = {
  email: string
  password: string
}
