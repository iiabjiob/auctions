type PostJson = <TResponse>(path: string, payload: unknown, signal?: AbortSignal) => Promise<TResponse>

export type AffinoPostJsonFetch = typeof fetch & {
  readonly lastJsonByPath: ReadonlyMap<string, unknown>
}

export function createAffinoPostJsonFetch(postJson: PostJson): AffinoPostJsonFetch {
  const lastJsonByPath = new Map<string, unknown>()

  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = resolvePath(input)
    const method = String(init?.method ?? 'GET').toUpperCase()
    if (method !== 'POST') {
      throw new Error(`Affino datasource fetch adapter only supports POST: ${method} ${path}`)
    }
    const payload = parseJsonBody(init?.body)
    const data = await postJson<unknown>(path, payload, init?.signal ?? undefined)
    lastJsonByPath.set(path, data)
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as AffinoPostJsonFetch

  Object.defineProperty(fetchImpl, 'lastJsonByPath', {
    value: lastJsonByPath,
    enumerable: true,
  })

  return fetchImpl
}

function resolvePath(input: RequestInfo | URL) {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  const url = new URL(raw, window.location.origin)
  return `${url.pathname}${url.search}`
}

function parseJsonBody(body: BodyInit | null | undefined) {
  if (typeof body !== 'string' || body.trim().length === 0) return {}
  return JSON.parse(body) as unknown
}
