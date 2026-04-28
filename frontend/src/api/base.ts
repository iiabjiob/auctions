const APP_BASE_PATH = import.meta.env.BASE_URL || '/'

export function buildAppPath(path: string) {
  if (/^https?:\/\//.test(path)) {
    return path
  }

  const normalizedBase = APP_BASE_PATH.endsWith('/') ? APP_BASE_PATH : `${APP_BASE_PATH}/`
  const normalizedPath = path.startsWith('/') ? path.slice(1) : path
  return `${normalizedBase}${normalizedPath}`
}