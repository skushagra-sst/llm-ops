import { useEffect, useState, type ReactNode } from "react"
import { CheckIcon, CircleDashedIcon, CornerDownLeftIcon, Loader2Icon, RotateCcwIcon, ShuffleIcon, XIcon } from "lucide-react"

import { LiveDot, useRate } from "@/components/admin/live-rate"
import { CopyButton, EmptyPanel, PageHeader, Panel, UsageMeter } from "@/components/admin/parts"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError, api } from "@/lib/api"
import { count, money, percent } from "@/lib/format"
import { navigate } from "@/lib/route"
import type { PlaygroundResult, TenantSummary } from "@/lib/types"
import { cn } from "cn"

const MODELS = ["gpt-4o-mini"]

const STEPS = [
  { id: "fetch", title: "Fetch page", detail: "The URL resolves to a public host and returns text." },
  { id: "replay", title: "Idempotency", detail: "A repeated Idempotency-Key returns the stored response." },
  { id: "rate", title: "Rate limit", detail: "Requests per minute stay under the plan’s limit." },
  { id: "input", title: "Prompt check", detail: "The page text is screened for prompt injection." },
  { id: "budget", title: "Budget reservation", detail: "Budget is held before the model runs." },
  { id: "model", title: "Model call", detail: "The model writes the summary." },
  { id: "output", title: "Output check", detail: "The summary is moderated before it is returned." },
  { id: "settle", title: "Ledger settle", detail: "The hold settles to the real token cost." },
] as const

type StepId = (typeof STEPS)[number]["id"]
type StepState = "passed" | "failed" | "skipped" | "reused" | "unused"

type Run =
  | { kind: "ok"; result: PlaygroundResult; idempotencyKey: string }
  | { kind: "error"; status: number; message: string; failedAt: StepId | null }

export function Playground({
  tenants,
  tenantId,
  onRan,
  onError,
}: {
  tenants: TenantSummary[]
  tenantId?: string
  onRan: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const selected = tenants.find((tenant) => tenant.id === tenantId) ?? tenants.find((tenant) => tenant.is_active) ?? tenants[0]
  const [url, setUrl] = useState("https://example.com")
  const [model, setModel] = useState(MODELS[0])
  const [idempotencyKey, setIdempotencyKey] = useState("")
  const [running, setRunning] = useState(false)
  const [run, setRun] = useState<Run | null>(null)
  const rate = useRate(selected?.id ?? "", run)

  useEffect(() => {
    setRun(null)
  }, [selected?.id])

  if (!selected) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Playground" />
        <EmptyPanel title="No tenants yet" description="Create a tenant first. Playground requests are billed to a tenant." />
      </div>
    )
  }

  const tenant = selected

  async function submit() {
    if (running) return
    setRunning(true)
    try {
      const result = await api<PlaygroundResult>(`/v1/admin/tenants/${encodeURIComponent(tenant.id)}/playground`, {
        method: "POST",
        body: { url, model, idempotency_key: idempotencyKey.trim() || null },
      })
      setRun({ kind: "ok", result, idempotencyKey: idempotencyKey.trim() })
    } catch (error) {
      if (error instanceof ApiError) {
        setRun({ kind: "error", status: error.status, message: error.message, failedAt: failedStep(error.status, error.message) })
      } else {
        onError(error)
      }
    } finally {
      setRunning(false)
      await onRan()
    }
  }

  const budgetUsed = tenant.plan ? percent(tenant.usage.spent_usd, tenant.plan.monthly_budget_usd) : 0

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Playground"
        description="Send a real summarize request as a tenant. It runs every guardrail and is billed like any API call."
      />
      <div className="grid items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Panel className="lg:sticky lg:top-20">
          <form
            className="flex flex-col gap-5 p-4"
            onSubmit={(event) => {
              event.preventDefault()
              void submit()
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault()
                void submit()
              }
            }}
          >
            <div className="flex flex-col gap-2">
              <Label>Tenant</Label>
              <Select value={tenant.id} onValueChange={(id) => navigate({ page: "playground", tenant: id })}>
                <SelectTrigger className="w-full" aria-label="Tenant">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {tenants.map((item) => (
                    <SelectItem key={item.id} value={item.id} disabled={!item.is_active}>
                      {item.name}
                      {!item.is_active ? <span className="text-muted-foreground">(inactive)</span> : null}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="w-full font-mono text-xs" aria-label="Model">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODELS.map((item) => (
                    <SelectItem key={item} value={item} className="font-mono text-xs">
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="playground-url">URL to summarize</Label>
              <Input id="playground-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} required />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="playground-idem">Idempotency key</Label>
                <span className="text-xs text-muted-foreground">Optional</span>
              </div>
              <div className="flex gap-2">
                <Input
                  id="playground-idem"
                  value={idempotencyKey}
                  onChange={(event) => setIdempotencyKey(event.target.value)}
                  placeholder="Leave empty for a fresh call"
                  className="font-mono text-xs placeholder:font-sans placeholder:text-sm"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="Generate key"
                  title="Generate key"
                  onClick={() => setIdempotencyKey(`run-${crypto.randomUUID().slice(0, 8)}`)}
                >
                  <ShuffleIcon />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">Send the same key twice to see a free replay.</p>
            </div>
            <Button type="submit" disabled={running || !tenant.is_active} className="relative w-full">
              {running ? <Loader2Icon className="animate-spin" data-icon="inline-start" /> : null}
              {running ? "Running" : "Run"}
              {!running ? (
                <kbd aria-hidden className="absolute right-3 inline-flex items-center gap-0.5 font-mono text-[11px] opacity-60">
                  ⌘<CornerDownLeftIcon className="size-3" />
                </kbd>
              ) : null}
            </Button>
          </form>
          <div className="flex flex-col gap-4 border-t bg-muted/30 p-4 text-sm">
            <MiniMeter
              title="Rate limit"
              aside={<LiveDot />}
              value={rate ? `${count(rate.used)} / ${count(rate.limit)} this minute` : "—"}
              percent={rate ? percent(rate.used, rate.limit) : 0}
              warn={rate !== null && rate.limit > 0 && rate.used >= rate.limit}
            />
            <MiniMeter
              title="Monthly budget"
              value={tenant.plan ? `${money(tenant.usage.spent_usd)} / ${money(tenant.plan.monthly_budget_usd)}` : "No plan"}
              percent={budgetUsed}
              warn={tenant.warning}
            />
          </div>
        </Panel>

        <div className="flex min-w-0 flex-col gap-4">
          {run === null ? (
            <EmptyPanel
              title={running ? "Running…" : "No run yet"}
              description="The summary, its cost, and each guardrail it passed will appear here."
            />
          ) : run.kind === "ok" ? (
            <Result result={run.result} idempotencyKey={run.idempotencyKey} onRunAgain={() => void submit()} running={running} />
          ) : (
            <Alert variant="destructive">
              <XIcon />
              <AlertTitle>{errorTitle(run.status, run.message)}</AlertTitle>
              <AlertDescription>
                <span>
                  HTTP {run.status} · {run.message}
                </span>
              </AlertDescription>
            </Alert>
          )}
          <Pipeline run={run} />
        </div>
      </div>
    </div>
  )
}

function Result({
  result,
  idempotencyKey,
  onRunAgain,
  running,
}: {
  result: PlaygroundResult
  idempotencyKey: string
  onRunAgain: () => void
  running: boolean
}) {
  return (
    <Panel>
      <div className="flex items-center justify-between gap-3 border-b px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Summary</span>
          {result.replayed ? <Badge variant="outline">Replayed · no charge</Badge> : <Badge variant="secondary">Billed</Badge>}
          {result.warning ? <Badge variant="destructive">Soft cap reached</Badge> : null}
        </div>
        <div className="flex items-center gap-1">
          <CopyButton value={result.summary} label="Copy summary" />
          {idempotencyKey ? (
            <Button variant="ghost" size="sm" onClick={onRunAgain} disabled={running}>
              <RotateCcwIcon data-icon="inline-start" />
              Send again
            </Button>
          ) : null}
        </div>
      </div>
      <p className="px-4 py-4 text-[15px] leading-relaxed whitespace-pre-wrap">{result.summary}</p>
      <dl className="grid grid-cols-2 gap-px border-t bg-border sm:grid-cols-5 [&>*]:bg-card">
        <Stat label="Cost" value={money(result.cost_usd)} />
        <Stat label="Input tokens" value={count(result.usage.input_tokens)} hint={`${count(result.usage.cached_input_tokens)} cached`} />
        <Stat label="Output tokens" value={count(result.usage.output_tokens)} />
        <Stat label="Latency" value={`${count(result.latency_ms)} ms`} />
        <Stat label="Month to date" value={money(result.spent_usd)} />
      </dl>
    </Panel>
  )
}

function Pipeline({ run }: { run: Run | null }) {
  return (
    <Panel>
      <div className="border-b px-4 py-2.5 text-sm font-medium">Request path</div>
      <ol className="flex flex-col">
        {STEPS.map((step, index) => {
          const state = run ? stepState(run, step.id, index) : null
          return (
            <li key={step.id} className="flex items-start gap-3 border-b px-4 py-3 last:border-b-0">
              <StepIcon state={state} />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className={cn("text-sm", (state === "skipped" || state === "unused") && "text-muted-foreground")}>{step.title}</span>
                <span className="text-xs text-muted-foreground">{step.detail}</span>
              </div>
              <span
                className={cn(
                  "shrink-0 text-xs",
                  state === "failed" ? "text-destructive" : state === "passed" || state === "reused" ? "text-success" : "text-muted-foreground",
                )}
              >
                {state === null ? "" : STATE_LABEL[state]}
              </span>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}

const STATE_LABEL: Record<StepState, string> = {
  passed: "Passed",
  failed: "Stopped here",
  skipped: "Not reached",
  reused: "Stored response",
  unused: "No key sent",
}

function StepIcon({ state }: { state: StepState | null }) {
  const base = "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full"
  if (state === "passed" || state === "reused") {
    return (
      <span className={cn(base, "bg-success/15 text-success")}>
        <CheckIcon className="size-3" />
      </span>
    )
  }
  if (state === "failed") {
    return (
      <span className={cn(base, "bg-destructive/15 text-destructive")}>
        <XIcon className="size-3" />
      </span>
    )
  }
  return (
    <span className={cn(base, "text-muted-foreground/60")}>
      <CircleDashedIcon className="size-4" />
    </span>
  )
}

function stepState(run: Run, id: StepId, index: number): StepState {
  if (run.kind === "ok") {
    if (run.result.replayed) {
      if (id === "fetch") return "passed"
      if (id === "replay") return "reused"
      return "skipped"
    }
    if (id === "replay" && !run.idempotencyKey) return "unused"
    return "passed"
  }
  if (run.failedAt === null) return "skipped"
  const failedIndex = STEPS.findIndex((step) => step.id === run.failedAt)
  if (index < failedIndex) return id === "replay" ? "unused" : "passed"
  if (index === failedIndex) return "failed"
  return "skipped"
}

function failedStep(status: number, message: string): StepId | null {
  if (status === 400) return message === "prompt rejected" ? "input" : "fetch"
  if (status === 429) return "rate"
  if (status === 402) return "budget"
  if (status === 422) return "output"
  if (status === 403 || status === 404) return null
  return "model"
}

function errorTitle(status: number, message: string) {
  if (status === 429) return "Rate limited"
  if (status === 402) return "Budget exceeded"
  if (status === 422) return "Output was moderated"
  if (status === 403) return "Tenant is inactive"
  if (status === 400) return message === "prompt rejected" ? "Prompt rejected" : "Couldn’t fetch that page"
  return "The model call failed"
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-4 py-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-sm tabular-nums">{value}</dd>
      {hint ? <dd className="text-[11px] text-muted-foreground">{hint}</dd> : null}
    </div>
  )
}

function MiniMeter({
  title,
  aside,
  value,
  percent: amount,
  warn,
}: {
  title: string
  aside?: ReactNode
  value: string
  percent: number
  warn?: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">{title}</span>
        {aside}
      </div>
      <UsageMeter value={amount} warn={warn} />
      <span className="font-mono text-xs text-muted-foreground tabular-nums">{value}</span>
    </div>
  )
}
