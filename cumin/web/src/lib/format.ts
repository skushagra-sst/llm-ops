export function money(value: string | number | null | undefined) {
  if (value == null || value === "") return "—"
  const amount = Number(value)
  if (!Number.isFinite(amount)) return "—"
  const digits = amount === 0 || Math.abs(amount) >= 1 ? 2 : 6
  return `$${amount.toFixed(digits)}`
}

export function price(value: string | number) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return "—"
  const trimmed = Number(amount.toFixed(6))
  return `$${trimmed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`
}

export function count(value: number) {
  return value.toLocaleString()
}

export function percent(used: string | number, cap: string | number) {
  const total = Number(cap)
  if (!Number.isFinite(total)) return 0
  if (total <= 0) return Number(used) > 0 ? 100 : 0
  return Math.min(100, (Number(used) / total) * 100)
}

export function percentLabel(value: number) {
  if (value === 0) return "0%"
  if (value < 0.1) return "<0.1%"
  return `${value.toFixed(value < 10 ? 1 : 0)}%`
}

export function currentMonth() {
  return new Date().toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })
}

export function dateTime(iso: string | null) {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
}

export function shortDate(day: string) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
}

export function ago(iso: string | null) {
  if (!iso) return "Never"
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return "Just now"
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)} days ago`
  return dateTime(iso)
}

export function label(value: string) {
  const text = value.replaceAll("_", " ")
  return text.charAt(0).toUpperCase() + text.slice(1)
}
