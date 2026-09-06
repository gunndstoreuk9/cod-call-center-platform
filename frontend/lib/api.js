export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  let body = options.body
  if (body && typeof body !== 'string' && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    body,
    credentials: 'include',
    cache: 'no-store'
  })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const payload = await res.json()
      detail = payload.detail || detail
    } catch (_) {}
    const error = new Error(detail)
    error.status = res.status
    throw error
  }
  if (res.status === 204) return null
  return res.json()
}

export function money(value, currency = 'MAD') {
  const n = Number(value || 0)
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`
}
