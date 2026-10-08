export type Usage = {
  request_count: number
  input_tokens: number
  output_tokens: number
  cached_input_tokens: number
  spent_usd: string
  spent_tokens: number
}

export type Plan = {
  id: string
  name: string
  monthly_budget_usd: string
  soft_budget_usd: string
  request_reserve_usd: string
  monthly_token_budget: number
  request_reserve_tokens: number
  requests_per_minute: number
  tenant_count?: number
}

export type TenantSummary = {
  id: string
  name: string
  is_active: boolean
  plan: {
    id: string
    monthly_budget_usd: string
    soft_budget_usd: string
    monthly_token_budget: number
  } | null
  usage: Usage
  warning: boolean
}

export type Board = {
  tenant_count: number
  request_count: number
  spent_usd: string
  spent_tokens: number
  tenants: TenantSummary[]
  plans: Plan[]
}

export type LedgerEntry = {
  id: string
  month: string
  status: string
  reserved_usd: string
  reserved_tokens: number
  actual_usd: string | null
  input_tokens: number | null
  output_tokens: number | null
  plan_id: string
  overrun: number
}

export type LogEvent = {
  id: number
  created_at: string | null
  outcome: string
  model: string
  key_prefix: string
  cost_usd: string | null
  request_text: string
  response_text: string | null
}

export type Replay = {
  idempotency_key: string
  text: string
  model: string
  input_tokens: number
  output_tokens: number
  cached_input_tokens: number
}

export type TenantDetail = {
  id: string
  name: string
  is_active: boolean
  plan: Plan | null
  usage: Usage
  warning: boolean
  keys: KeyRow[]
  ledger: LedgerEntry[]
  replays: Replay[]
}

export type KeyRow = {
  prefix: string
  status: "active" | "revoked" | "console"
  created_at: string | null
  requests: number
  spend_usd: string
  last_used: string | null
}

export type IssuedKey = {
  prefix: string
  api_key: string
}

export type LogPage = {
  total: number
  events: LogEvent[]
}

export type DailyPoint = {
  date: string
  spend_usd: string
  requests: number
  blocked: number
}

export type RateInfo = {
  used: number
  limit: number
  window_seconds: number
}

export type PlaygroundResult = {
  summary: string
  model: string
  usage: { input_tokens: number; output_tokens: number; cached_input_tokens: number }
  spent_usd: string
  warning: boolean
  replayed: boolean
  cost_usd: string
  latency_ms: number
  rate: RateInfo
}
