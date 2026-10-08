import { useEffect, useState } from "react"
import { FlaskConicalIcon, KeyRoundIcon, MoreHorizontalIcon, PencilIcon, PowerIcon, Trash2Icon } from "lucide-react"

import { LiveRateCard } from "@/components/admin/live-rate"
import { LogsPanel } from "@/components/admin/logs-panel"
import { UsageChart } from "@/components/admin/usage-chart"
import {
  CopyButton,
  EmptyPanel,
  Metric,
  MetricStrip,
  PageHeader,
  Panel,
  Section,
  StatusDot,
  UsageMeter,
} from "@/components/admin/parts"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { ago, count, currentMonth, dateTime, label, money, percent, percentLabel } from "@/lib/format"
import { navigate } from "@/lib/route"
import type { IssuedKey, KeyRow, Plan, Replay, TenantDetail } from "@/lib/types"
import { cn } from "cn"

export function TenantDetailView({
  detail,
  plans,
  onChange,
  onDeleted,
  onError,
}: {
  detail: TenantDetail
  plans: Plan[]
  onChange: () => Promise<void>
  onDeleted: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const [tab, setTab] = useState("usage")
  const [issued, setIssued] = useState<IssuedKey | null>(null)
  const [revokePrefix, setRevokePrefix] = useState<string | null>(null)
  const [replay, setReplay] = useState<Replay | null>(null)
  const [renameOpen, setRenameOpen] = useState(false)
  const [name, setName] = useState(detail.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setIssued(null)
    setReplay(null)
    setTab("usage")
  }, [detail.id])

  useEffect(() => {
    setName(detail.name)
  }, [detail.name])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
      await onChange()
    } catch (error) {
      onError(error)
    } finally {
      setBusy(false)
    }
  }

  function issueKey() {
    setTab("keys")
    return run(async () => {
      setIssued(await api<IssuedKey>(`/v1/admin/tenants/${detail.id}/keys`, { method: "POST" }))
    })
  }

  const plan = detail.plan
  const activeKeys = detail.keys.filter((key) => key.status === "active")
  const spendUsed = plan ? percent(detail.usage.spent_usd, plan.monthly_budget_usd) : 0
  const tokensUsed = plan ? percent(detail.usage.spent_tokens, plan.monthly_token_budget) : 0

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {detail.name}
            {detail.warning ? <Badge variant="destructive" className="font-sans">Soft cap reached</Badge> : null}
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="inline-flex items-center gap-1">
              <span className="font-mono text-xs">{detail.id}</span>
              <CopyButton value={detail.id} label="Copy tenant id" />
            </span>
            <StatusDot active={detail.is_active} />
          </span>
        }
        actions={
          <>
            <Select
              value={plan?.id}
              onValueChange={(planId) => {
                if (planId === plan?.id) return
                void run(() => api(`/v1/admin/tenants/${detail.id}/plan`, { method: "POST", body: { plan_id: planId } }))
              }}
              disabled={busy || plans.length === 0}
            >
              <SelectTrigger className="w-32" aria-label="Plan">
                <SelectValue placeholder="Plan" />
              </SelectTrigger>
              <SelectContent>
                {plans.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              disabled={!detail.is_active}
              onClick={() => navigate({ page: "playground", tenant: detail.id })}
            >
              <FlaskConicalIcon data-icon="inline-start" />
              Playground
            </Button>
            <Button disabled={busy} onClick={() => void issueKey()}>
              <KeyRoundIcon data-icon="inline-start" />
              Issue key
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" aria-label="More actions" disabled={busy}>
                  <MoreHorizontalIcon />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                  <PencilIcon />
                  Rename
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() =>
                    void run(() =>
                      api(`/v1/admin/tenants/${detail.id}/active`, {
                        method: "POST",
                        body: { is_active: !detail.is_active },
                      }),
                    )
                  }
                >
                  <PowerIcon />
                  {detail.is_active ? "Deactivate" : "Activate"}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
                  <Trash2Icon />
                  Delete tenant
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      {!detail.is_active ? (
        <Alert>
          <AlertTitle>This tenant is inactive</AlertTitle>
          <AlertDescription>Its API keys are refused until you activate it again.</AlertDescription>
        </Alert>
      ) : null}

      <Tabs value={tab} onValueChange={setTab} className="gap-6">
        <TabsList variant="line" className="w-full justify-start gap-4 border-b pb-px">
          <TabsTrigger value="usage" className="flex-none px-0">Usage</TabsTrigger>
          <TabsTrigger value="keys" className="flex-none px-0">
            API keys
            <CountBadge value={activeKeys.length} />
          </TabsTrigger>
          <TabsTrigger value="ledger" className="flex-none px-0">Ledger</TabsTrigger>
          <TabsTrigger value="logs" className="flex-none px-0">Logs</TabsTrigger>
          <TabsTrigger value="stored" className="flex-none px-0">
            Stored responses
            <CountBadge value={detail.replays.length} />
          </TabsTrigger>
        </TabsList>

        <TabsContent value="usage" className="flex flex-col gap-6">
          <MetricStrip>
            <Metric label="Spend" value={money(detail.usage.spent_usd)} hint={currentMonth()} />
            <Metric label="Requests" value={count(detail.usage.request_count)} hint="Billed calls" />
            <Metric label="Input tokens" value={count(detail.usage.input_tokens)} hint={`${count(detail.usage.cached_input_tokens)} cached`} />
            <Metric label="Output tokens" value={count(detail.usage.output_tokens)} hint="Generated" />
          </MetricStrip>
          <UsageChart tenantId={detail.id} refreshKey={detail} onError={onError} />
          <div className="grid gap-4 lg:grid-cols-3">
            <LimitCard
              title="Monthly budget"
              used={money(detail.usage.spent_usd)}
              cap={plan ? money(plan.monthly_budget_usd) : "—"}
              value={spendUsed}
              warn={detail.warning}
              note={plan ? `Soft warning at ${money(plan.soft_budget_usd)}. Requests stop at the cap.` : "No plan found."}
            />
            <LimitCard
              title="Monthly tokens"
              used={count(detail.usage.spent_tokens)}
              cap={plan ? count(plan.monthly_token_budget) : "—"}
              value={tokensUsed}
              note="Input and output tokens across every key."
            />
            <LiveRateCard tenantId={detail.id} refreshKey={detail} />
          </div>
          {plan ? (
            <Section title="Plan limits">
              <Panel>
                <dl className="grid divide-y text-sm sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                  <PlanFact label="Plan" value={plan.name} />
                  <PlanFact label="Rate limit" value={`${count(plan.requests_per_minute)} requests per minute`} />
                  <PlanFact label="Soft warning" value={money(plan.soft_budget_usd)} />
                </dl>
              </Panel>
            </Section>
          ) : null}
        </TabsContent>

        <TabsContent value="keys" className="flex flex-col gap-4">
          {issued ? (
            <Alert>
              <KeyRoundIcon />
              <AlertTitle>Save this key now</AlertTitle>
              <AlertDescription>
                <span>It won’t be shown again.</span>
                <code className="mt-2 block rounded-md bg-muted px-3 py-2 font-mono text-xs break-all text-foreground">
                  {issued.api_key}
                </code>
              </AlertDescription>
              <AlertAction>
                <CopyButton value={issued.api_key} label="Copy key" />
              </AlertAction>
            </Alert>
          ) : null}
          {detail.keys.length === 0 ? (
            <EmptyPanel
              title="No API keys"
              description="This tenant can’t call the API until it has a key."
              action={
                <Button disabled={busy} onClick={() => void issueKey()}>
                  Issue key
                </Button>
              }
            />
          ) : (
            <Section
              title="Cost by key"
              description="Every completed request is billed to the key that made it. Revoked keys keep their history."
            >
              <Panel>
                <Table>
                  <TableHeader className="bg-muted/50">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-4">Key</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Last used</TableHead>
                      <TableHead className="text-right">Requests</TableHead>
                      <TableHead className="text-right">Spend</TableHead>
                      <TableHead className="w-32">Share</TableHead>
                      <TableHead className="w-20 pr-4 text-right" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.keys.map((key) => (
                      <KeyTableRow key={key.prefix} row={key} total={keyTotal(detail.keys)} onRevoke={() => setRevokePrefix(key.prefix)} />
                    ))}
                  </TableBody>
                </Table>
              </Panel>
            </Section>
          )}
        </TabsContent>

        <TabsContent value="ledger">
          {detail.ledger.length === 0 ? (
            <EmptyPanel title="No ledger entries" description="Each request reserves budget first, then settles to the real cost." />
          ) : (
            <Panel>
              <Table>
                <TableHeader className="bg-muted/50">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-4">Status</TableHead>
                    <TableHead>Month</TableHead>
                    <TableHead>Plan</TableHead>
                    <TableHead className="text-right">Reserved</TableHead>
                    <TableHead className="text-right">Charged</TableHead>
                    <TableHead className="pr-4 text-right">Tokens</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {detail.ledger.map((entry) => {
                    const tokens = (entry.input_tokens ?? 0) + (entry.output_tokens ?? 0)
                    return (
                      <TableRow key={entry.id}>
                        <TableCell className="pl-4">
                          <LedgerStatus status={entry.status} overrun={Boolean(entry.overrun)} />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{entry.month}</TableCell>
                        <TableCell className="text-muted-foreground">{label(entry.plan_id)}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{money(entry.reserved_usd)}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums">{money(entry.actual_usd)}</TableCell>
                        <TableCell className="pr-4 text-right font-mono tabular-nums">
                          {entry.status === "settled" ? count(tokens) : `${count(entry.reserved_tokens)} held`}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </Panel>
          )}
        </TabsContent>

        <TabsContent value="logs">
          <LogsPanel tenantId={detail.id} keys={detail.keys} refreshKey={detail} onError={onError} />
        </TabsContent>

        <TabsContent value="stored">
          {detail.replays.length === 0 ? (
            <EmptyPanel
              title="No stored responses"
              description="Responses are stored when the caller sends an Idempotency-Key header. Replaying one shows the saved text without calling the model."
            />
          ) : (
            <Panel>
              <Table>
                <TableHeader className="bg-muted/50">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-4">Idempotency key</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Tokens</TableHead>
                    <TableHead className="w-28 pr-4 text-right" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {detail.replays.map((item) => (
                    <TableRow key={item.idempotency_key}>
                      <TableCell className="pl-4 font-mono text-xs">{item.idempotency_key}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{item.model}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{count(item.input_tokens + item.output_tokens)}</TableCell>
                      <TableCell className="pr-4 text-right">
                        <Button variant="outline" size="sm" onClick={() => setReplay(item)}>
                          Replay
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Panel>
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={replay !== null} onOpenChange={(open) => !open && setReplay(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Stored response</DialogTitle>
            <DialogDescription>
              <span className="font-mono">{replay?.idempotency_key}</span> · {replay?.model}. No model call and no charge.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-80 overflow-auto rounded-md bg-muted p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap">
            {replay?.text}
          </pre>
          <DialogFooter>
            {replay ? <CopyButton value={replay.text} label="Copy response" /> : null}
            <Button variant="outline" onClick={() => setReplay(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename tenant</DialogTitle>
            <DialogDescription>
              The tenant id stays <span className="font-mono">{detail.id}</span>.
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              void run(async () => {
                await api(`/v1/admin/tenants/${detail.id}/name`, { method: "POST", body: { name } })
                setRenameOpen(false)
              })
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="rename">Name</Label>
              <Input id="rename" value={name} onChange={(event) => setName(event.target.value)} required />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {detail.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the tenant with its keys, ledger, logs, and stored responses.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setBusy(true)
                void api(`/v1/admin/tenants/${detail.id}`, { method: "DELETE" })
                  .then(onDeleted)
                  .catch(onError)
                  .finally(() => setBusy(false))
              }}
            >
              Delete tenant
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={revokePrefix !== null} onOpenChange={(open) => !open && setRevokePrefix(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke this key?</AlertDialogTitle>
            <AlertDialogDescription>
              <span className="font-mono">{revokePrefix}</span> stops working right away. Spend it already booked stays on the ledger.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                const prefix = revokePrefix
                setRevokePrefix(null)
                if (prefix) void run(() => api(`/v1/admin/keys/${encodeURIComponent(prefix)}`, { method: "DELETE" }))
              }}
            >
              Revoke key
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function CountBadge({ value }: { value: number }) {
  return <span className="rounded-full bg-muted px-1.5 font-mono text-[11px] text-muted-foreground tabular-nums">{value}</span>
}

function LimitCard({
  title,
  used,
  cap,
  value,
  note,
  warn,
}: {
  title: string
  used: string
  cap: string
  value: number
  note: string
  warn?: boolean
}) {
  return (
    <Panel className="flex flex-col gap-4 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{title}</span>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">{percentLabel(value)} used</span>
      </div>
      <div className="flex items-baseline gap-1.5 font-mono tabular-nums">
        <span className="text-xl tracking-tight">{used}</span>
        <span className="text-sm text-muted-foreground">of {cap}</span>
      </div>
      <UsageMeter value={value} warn={warn} />
      <p className="text-xs text-muted-foreground">{note}</p>
    </Panel>
  )
}

function PlanFact({ label: name, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 p-4">
      <dt className="text-[13px] text-muted-foreground">{name}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}

function LedgerStatus({ status, overrun }: { status: string; overrun: boolean }) {
  if (status === "settled" && overrun) {
    return (
      <Badge variant="destructive" title="The provider billed more than this request's hold">
        Over hold
      </Badge>
    )
  }
  if (status === "settled") return <Badge variant="secondary">Settled</Badge>
  if (status === "open") return <Badge variant="outline">Reserved</Badge>
  return <Badge variant="outline" className="text-muted-foreground">Released</Badge>
}

function keyTotal(keys: KeyRow[]) {
  return keys.reduce((sum, key) => sum + Number(key.spend_usd), 0)
}

function KeyTableRow({ row, total, onRevoke }: { row: KeyRow; total: number; onRevoke: () => void }) {
  const share = total > 0 ? (Number(row.spend_usd) / total) * 100 : 0
  const muted = row.status === "revoked"
  return (
    <TableRow className={cn(muted && "text-muted-foreground")}>
      <TableCell className="pl-4">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-xs">{row.status === "console" ? "Playground" : `${row.prefix}.••••••••`}</span>
          {row.created_at ? <span className="text-[11px] text-muted-foreground">Created {dateTime(row.created_at)}</span> : null}
        </div>
      </TableCell>
      <TableCell>
        {row.status === "active" ? (
          <Badge variant="secondary">Active</Badge>
        ) : row.status === "console" ? (
          <Badge variant="outline">Admin console</Badge>
        ) : (
          <Badge variant="outline" className="text-muted-foreground">Revoked</Badge>
        )}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground" title={row.last_used ?? undefined}>{row.last_used === null && row.requests > 0 ? "—" : ago(row.last_used)}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">{count(row.requests)}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">{money(row.spend_usd)}</TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <UsageMeter value={share} className="min-w-12 flex-1" />
          <span className="w-8 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums">{share.toFixed(0)}%</span>
        </div>
      </TableCell>
      <TableCell className="pr-4 text-right">
        {row.status === "active" ? (
          <Button variant="ghost" size="sm" className="text-destructive" onClick={onRevoke}>
            Revoke
          </Button>
        ) : null}
      </TableCell>
    </TableRow>
  )
}
