import { formatDateTime } from './formatters'

type DetailFieldEntry = [string, unknown]

export type DetailField = {
  label: string
  value: string
}

type ApiField = {
  name: string
  value: string
}

type ApiDocument = {
  external_id: string | null
  received_at: string | null
  name: string | null
  url: string | null
  signature_status: string | null
  comment: string | null
  document_type: string | null
}

type ApiLotImage = {
  url: string
  thumbnail_url: string | null
  alt: string | null
  source: string | null
}

export type DetailImage = {
  url: string
  thumbnailUrl: string
  name: string | null
}

const DETAIL_RENDER_RAW_FIELDS_LIMIT = 120
const DETAIL_RENDER_DOCUMENTS_LIMIT = 120
const DETAIL_RENDER_IMAGES_LIMIT = 80

export function makeFields(entries: DetailFieldEntry[]): DetailField[] {
  return entries
    .map(([label, value]) => ({ label, value: truncateDetailText(normalizeTextValue(value)) }))
    .filter((field) => field.value && field.value !== 'Не задано')
}

export function normalizeTextValue(value: unknown) {
  if (value === null || value === undefined) return ''
  if (value instanceof Date) return formatDateTime(value)
  return String(value).trim()
}

export function normalizeRawFields(fields: ApiField[]): DetailField[] {
  const seen = new Set<string>()
  return fields
    .slice(0, DETAIL_RENDER_RAW_FIELDS_LIMIT)
    .map((field) => ({
      label: field.name.trim(),
      value: truncateDetailText(field.value.trim()),
    }))
    .filter((field) => {
      if (!field.label || !field.value) return false
      if (/^\d+$/.test(field.label)) return false
      if (field.label === '---' || field.label === '№') return false

      const key = `${field.label}\n${field.value}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function uniqueDocuments(documents: ApiDocument[]) {
  const seen = new Set<string>()
  return documents.slice(0, DETAIL_RENDER_DOCUMENTS_LIMIT).filter((document) => {
    const key = document.external_id || document.url || `${document.name || ''}\n${document.received_at || ''}`
    if (!key.trim() || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function uniqueDetailImages(images: Array<ApiLotImage | DetailImage>): DetailImage[] {
  const seen = new Set<string>()
  return images
    .slice(0, DETAIL_RENDER_IMAGES_LIMIT)
    .map((image) => ({
      url: image.url,
      thumbnailUrl: 'thumbnailUrl' in image ? image.thumbnailUrl : image.thumbnail_url || image.url,
      name: 'name' in image ? image.name : 'alt' in image ? image.alt : null,
    }))
    .filter((image) => {
      if (!image.url || seen.has(image.url)) return false
      seen.add(image.url)
      return true
    })
}

export function truncateDetailText(value: string, limit = 2_000) {
  return value.length > limit ? `${value.slice(0, limit).trim()}...` : value
}

export function isNoPhotoReason(reason: string) {
  return reason.trim().toLowerCase() === 'нет фото'
}

export function isLockedTbankrotImageUrl(url: string) {
  return /\/img\/blur\/|\/blur_/i.test(url)
}

export function isImageDocument(document: ApiDocument) {
  const documentType = (document.document_type || '').trim().toLowerCase()
  const text = [document.url, document.name, document.comment].filter(Boolean).join(' ')
  return documentType === 'photo' || /фото|photo|изображ/i.test(text) || /\.(png|jpe?g|gif|webp)(\?|$)/i.test(text)
}

export function isRelevantDetailImage(url: string, source: string | null | undefined) {
  if (source !== 'tbankrot') return true
  return /files\.tbankrot\.ru\//i.test(url) || /webapi\.torgi\.cdtrf\.ru\/doc\/public\/file/i.test(url)
}

export function belongsToSelectedLotMedia(document: ApiDocument, lotNumber: string | null | undefined) {
  if (!lotNumber) return true

  const text = [document.name, document.document_type, document.comment].filter(Boolean).join(' ').toLowerCase()
  const explicitLotMatch = text.match(/(?:лот|lot)\s*0*(\d+)/i)
  return !explicitLotMatch || explicitLotMatch[1] === lotNumber.replace(/^0+/, '')
}
