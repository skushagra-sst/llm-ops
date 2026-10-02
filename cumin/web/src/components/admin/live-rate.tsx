import { useEffect, useState } from "react"

import { Panel, UsageMeter } from "@/components/admin/parts"
import { api } from "@/lib/api"
import { count, percent, percentLabel } from "@/lib/format"
import type { RateInfo } from "@/lib/types"

const POLL_MS = 3000

export function useRate(tenantId: string, refreshKey?: unknown) {
  const [rate, setRate] = useState<RateInfo | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      if (document.hidden) return
      api<RateInfo>(`/v1/admin/tenants/${encodeURIComponent(tenantId)}/rate`)
        .then((body) => !cancelled && setRate(body))
        .catch(() => undefined)
    }
    load()
    const timer = window.setInterval(load, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [tenantId, refreshKey])

  return rate
}

export function LiveRateCard({ tenantId, refreshKey }: { tenantId: string; refreshKey?: unknown }) {
  const rate = useRate(tenantId, refreshKey)
  const used = rate ? percent(rate.used, rate.limit) : 0
  const full = rate !== null && rate.limit > 0 && rate.used >= rate.limit

  return (
    <Panel className="flex flex-col gap-4 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">Rate limit</span>
        <LiveDot />
      </div>
      <div className="flex items-baseline gap-1.5 font-mono tabular-nums">
        <span className="text-xl tracking-tight">{rate ? count(rate.used) : "—"}</span>
        <span className="text-sm text-muted-foreground">of {rate ? count(rate.limit) : "—"} per minute</span>
      </div>
      <UsageMeter value={used} warn={full} />
      <p className="text-xs text-muted-foreground">
        {full ? "New requests get 429 until the window resets." : `${percentLabel(used)} of this minute’s allowance used.`}
      </p>
    </Panel>
  )
}

export function LiveDot() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="relative flex size-1.5">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
        <span className="relative inline-flex size-1.5 rounded-full bg-success" />
      </span>
      Live
    </span>
  )
}
