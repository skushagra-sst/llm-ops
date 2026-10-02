import { useEffect, useState } from "react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { Panel } from "@/components/admin/parts"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, query } from "@/lib/api"
import { count, money, shortDate } from "@/lib/format"
import type { DailyPoint } from "@/lib/types"
import { cn } from "cn"

type MetricKey = "spend" | "requests" | "blocked"

const config = {
  spend: { label: "Spend", color: "var(--brand)" },
  requests: { label: "Requests", color: "var(--foreground)" },
  blocked: { label: "Blocked", color: "var(--destructive)" },
} satisfies ChartConfig

const RANGES = [7, 30, 90] as const

export function UsageChart({
  tenantId,
  refreshKey,
  onError,
}: {
  tenantId?: string
  refreshKey?: unknown
  onError: (error: unknown) => void
}) {
  const [days, setDays] = useState<number>(30)
  const [metric, setMetric] = useState<MetricKey>("spend")
  const [points, setPoints] = useState<DailyPoint[] | null>(null)

  useEffect(() => {
    let cancelled = false
    api<{ days: DailyPoint[] }>(`/v1/admin/usage/daily${query({ tenant_id: tenantId, days })}`)
      .then((body) => !cancelled && setPoints(body.days))
      .catch((error) => !cancelled && onError(error))
    return () => {
      cancelled = true
    }
  }, [tenantId, days, refreshKey, onError])

  const data = (points ?? []).map((point) => ({
    date: point.date,
    spend: Number(point.spend_usd),
    requests: point.requests,
    blocked: point.blocked,
  }))
  const totals = {
    spend: data.reduce((sum, point) => sum + point.spend, 0),
    requests: data.reduce((sum, point) => sum + point.requests, 0),
    blocked: data.reduce((sum, point) => sum + point.blocked, 0),
  }
  const format = (key: MetricKey, value: number) => (key === "spend" ? money(value) : count(value))

  return (
    <Panel>
      <div className="flex flex-wrap items-stretch justify-between border-b">
        <div className="flex">
          {(Object.keys(config) as MetricKey[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setMetric(key)}
              className={cn(
                "relative flex flex-col gap-1 border-r px-5 py-3.5 text-left transition-colors hover:bg-muted/40",
                metric === key && "bg-muted/40",
              )}
            >
              <span className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
                <span className="size-2 rounded-[2px]" style={{ background: config[key].color }} />
                {config[key].label}
              </span>
              <span className="font-mono text-lg tracking-tight tabular-nums">
                {points ? format(key, totals[key]) : <Skeleton className="h-6 w-16" />}
              </span>
              {metric === key ? <span className="absolute inset-x-0 -bottom-px h-0.5 bg-foreground" /> : null}
            </button>
          ))}
        </div>
        <div className="flex items-center px-4 py-3">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={0}
            value={String(days)}
            onValueChange={(value) => value && setDays(Number(value))}
          >
            {RANGES.map((range) => (
              <ToggleGroupItem key={range} value={String(range)} className="px-2.5 font-mono text-xs">
                {range}d
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>
      <div className="px-2 pt-4 pb-2">
        {points ? (
          <ChartContainer config={config} className="aspect-auto h-56 w-full">
            <BarChart data={data} margin={{ left: 4, right: 12 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={28}
                tickFormatter={shortDate}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={68}
                domain={[0, (dataMax: number) => (dataMax > 0 ? dataMax : metric === "spend" ? 0.01 : 4)]}
                allowDecimals={metric !== "requests" && metric !== "blocked"}
                tickFormatter={(value: number) => (metric === "spend" ? `$${Number(value.toPrecision(2))}` : count(value))}
              />
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) => shortDate(String(value))}
                    formatter={(value) => (
                      <span className="flex w-full items-center justify-between gap-4">
                        <span className="text-muted-foreground">{config[metric].label}</span>
                        <span className="font-mono tabular-nums">{format(metric, Number(value))}</span>
                      </span>
                    )}
                  />
                }
              />
              <Bar dataKey={metric} fill={`var(--color-${metric})`} radius={[3, 3, 0, 0]} maxBarSize={28} isAnimationActive={false} />
            </BarChart>
          </ChartContainer>
        ) : (
          <Skeleton className="m-2 h-52" />
        )}
      </div>
    </Panel>
  )
}
