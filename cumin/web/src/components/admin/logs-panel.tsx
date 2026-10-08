import { useEffect, useState } from "react"
import { DownloadIcon, SearchIcon, XIcon } from "lucide-react"

import { EmptyPanel, Panel } from "@/components/admin/parts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, download, query } from "@/lib/api"
import { dateTime, label, money } from "@/lib/format"
import type { KeyRow, LogEvent, LogPage } from "@/lib/types"

const PAGE_SIZE = 25
const ALL = "all"

const KINDS = [
  { value: ALL, label: "All events" },
  { value: "completed", label: "Completed" },
  { value: "blocked", label: "Blocked" },
  { value: "replay", label: "Replays" },
  { value: "admin", label: "Admin changes" },
]

export const FAILURES = new Set(["rate_limited", "budget_exceeded", "injection", "moderated", "error", "unauthenticated", "unsupported_model", "idempotency_conflict"])

export function LogsPanel({
  tenantId,
  keys,
  refreshKey,
  onError,
}: {
  tenantId: string
  keys: KeyRow[]
  refreshKey?: unknown
  onError: (error: unknown) => void
}) {
  const [kind, setKind] = useState(ALL)
  const [key, setKey] = useState(ALL)
  const [search, setSearch] = useState("")
  const [text, setText] = useState("")
  const [since, setSince] = useState("")
  const [until, setUntil] = useState("")
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<LogPage | null>(null)
  const [open, setOpen] = useState<LogEvent | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setText(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setOffset(0)
  }, [kind, key, text, since, until, tenantId])

  const filters = {
    kind: kind === ALL ? null : kind,
    key: key === ALL ? null : key,
    q: text,
    since,
    until,
  }
  const filterQuery = query(filters)
  const pageQuery = query({ ...filters, limit: PAGE_SIZE, offset })

  useEffect(() => {
    let cancelled = false
    api<LogPage>(`/v1/admin/tenants/${encodeURIComponent(tenantId)}/logs${pageQuery}`)
      .then((body) => !cancelled && setPage(body))
      .catch((error) => !cancelled && onError(error))
    return () => {
      cancelled = true
    }
  }, [tenantId, pageQuery, refreshKey, onError])

  const filtered = kind !== ALL || key !== ALL || text !== "" || since !== "" || until !== ""
  const total = page?.total ?? 0
  const first = total === 0 ? 0 : offset + 1
  const last = Math.min(offset + PAGE_SIZE, total)

  function reset() {
    setKind(ALL)
    setKey(ALL)
    setSearch("")
    setText("")
    setSince("")
    setUntil("")
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search request and response text"
            className="pl-8"
            aria-label="Search logs"
          />
        </div>
        <Button
          variant="outline"
          disabled={total === 0}
          onClick={() =>
            void download(`/v1/admin/tenants/${encodeURIComponent(tenantId)}/logs.csv${filterQuery}`, `${tenantId}-logs.csv`).catch(onError)
          }
        >
          <DownloadIcon data-icon="inline-start" />
          Export CSV
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-36" aria-label="Event type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {KINDS.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={key} onValueChange={setKey}>
          <SelectTrigger className="w-36" aria-label="Key">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All keys</SelectItem>
            {keys.map((row) => (
              <SelectItem key={row.prefix} value={row.prefix}>
                <span className="font-mono text-xs">{row.prefix}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-1.5">
          <Input type="date" value={since} max={until || undefined} onChange={(event) => setSince(event.target.value)} className="w-36" aria-label="From date" />
          <span className="text-xs text-muted-foreground">to</span>
          <Input type="date" value={until} min={since || undefined} onChange={(event) => setUntil(event.target.value)} className="w-36" aria-label="To date" />
        </div>
        {filtered ? (
          <Button variant="ghost" size="sm" onClick={reset}>
            <XIcon data-icon="inline-start" />
            Clear
          </Button>
        ) : null}
      </div>

      {page === null ? (
        <Skeleton className="h-64 w-full" />
      ) : page.events.length === 0 ? (
        <EmptyPanel
          title={filtered ? "No matching events" : "No logs yet"}
          description={
            filtered
              ? "Try a wider date range or clear the filters."
              : "Requests, refusals, and admin changes appear here with personal data redacted."
          }
          action={filtered ? <Button variant="outline" onClick={reset}>Clear filters</Button> : undefined}
        />
      ) : (
        <Panel>
          <Table className="table-fixed">
            <TableHeader className="bg-muted/50">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-32 pl-4">Time</TableHead>
                <TableHead className="w-36">Event</TableHead>
                <TableHead className="w-24">Key</TableHead>
                <TableHead className="w-24 text-right">Cost</TableHead>
                <TableHead className="pr-4">Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page.events.map((event) => (
                <TableRow key={event.id} className="cursor-pointer" onClick={() => setOpen(event)}>
                  <TableCell className="pl-4 align-top text-xs whitespace-nowrap text-muted-foreground tabular-nums">
                    {dateTime(event.created_at)}
                  </TableCell>
                  <TableCell className="align-top">
                    <OutcomeBadge outcome={event.outcome} />
                  </TableCell>
                  <TableCell className="align-top font-mono text-xs text-muted-foreground">{event.key_prefix || "—"}</TableCell>
                  <TableCell className="text-right align-top font-mono text-xs tabular-nums">{money(event.cost_usd)}</TableCell>
                  <TableCell className="pr-4 align-top">
                    <p className="line-clamp-2 whitespace-normal text-muted-foreground">{event.request_text}</p>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-xs text-muted-foreground">
            <span className="tabular-nums">
              {first}–{last} of {total.toLocaleString()}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={last >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next
              </Button>
            </div>
          </div>
        </Panel>
      )}

      <Sheet open={open !== null} onOpenChange={(value) => !value && setOpen(null)}>
        <SheetContent className="w-full gap-0 sm:max-w-lg">
          <SheetHeader className="border-b">
            <SheetTitle className="flex items-center gap-2">
              {open ? <OutcomeBadge outcome={open.outcome} /> : null}
              <span className="text-sm font-normal text-muted-foreground">{open ? dateTime(open.created_at) : ""}</span>
            </SheetTitle>
            <SheetDescription>Personal data and API keys are redacted before they are stored.</SheetDescription>
          </SheetHeader>
          {open ? (
            <div className="flex flex-col gap-5 overflow-y-auto p-4">
              <dl className="grid grid-cols-3 gap-3 text-sm">
                <Fact label="Key" value={open.key_prefix || "—"} mono />
                <Fact label="Model" value={open.model} mono />
                <Fact label="Cost" value={money(open.cost_usd)} mono />
              </dl>
              <Block title="Request" text={open.request_text} />
              {open.response_text ? <Block title="Response" text={open.response_text} /> : null}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  )
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === "completed") return <Badge variant="secondary">Completed</Badge>
  if (FAILURES.has(outcome)) return <Badge variant="destructive">{label(outcome)}</Badge>
  return <Badge variant="outline">{label(outcome)}</Badge>
}

function Fact({ label: name, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs text-muted-foreground">{name}</dt>
      <dd className={mono ? "font-mono text-xs" : undefined}>{value}</dd>
    </div>
  )
}

function Block({ title, text }: { title: string; text: string }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
      <pre className="max-h-72 overflow-auto rounded-md bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">{text}</pre>
    </section>
  )
}
