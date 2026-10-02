const TOKEN_KEY = "cumin-admin-token"

export class AuthError extends Error {}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) ?? ""
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

async function send(path: string, options: { method?: string; body?: unknown } = {}) {
  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers: {
      "X-Admin-Token": getToken(),
      ...(options.body == null ? {} : { "Content-Type": "application/json" }),
    },
    body: options.body == null ? undefined : JSON.stringify(options.body),
  })
  if (response.status === 401) {
    clearToken()
    throw new AuthError("That admin token was refused.")
  }
  if (!response.ok) {
    let message = "The request failed."
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === "string") message = body.detail
    } catch {
      message = "The request failed."
    }
    throw new ApiError(response.status, message)
  }
  return response
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const response = await send(path, options)
  return response.json() as Promise<T>
}

export async function download(path: string, filename: string) {
  const response = await send(path)
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function query(params: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ""
}
