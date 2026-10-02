import { PlusIcon } from "lucide-react"

import { EmptyPanel, Metric, MetricStrip, PageHeader, Panel, Section, StatusDot, UsageMeter } from "@/components/admin/parts"
import { UsageChart } from "@/components/admin/usage-chart"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { count, currentMonth, money, percent, percentLabel } from "@/lib/format"
import { navigate } from "@/lib/route"
import type { Board, Plan } from "@/lib/types"

export function Overview({
  board,
  plans,
  onNewTenant,
  onError,
}: {
  board: Board
  plans: Plan[]
  onNewTenant: () => void
  onError: (error: unknown) => void
}) {
  const planName = (id: string | undefined) => plans.find((plan) => plan.id === id)?.name ?? id ?? "Unknown"
  const active = board.tenants.filter((tenant) => tenant.is_active).length

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        description={`Usage across every tenant for ${currentMonth()}.`}
        actions={
          <Button onClick={onNewTenant}>
            <PlusIcon data-icon="inline-start" />
            Create tenant
          </Button>
        }
      />
      <MetricStrip>
        <Metric label="Spend" value={money(board.spent_usd)} hint="Settled this month" />
        <Metric label="Requests" value={count(board.request_count)} hint="Billed calls" />
        <Metric label="Tokens" value={count(board.spent_tokens)} hint="Input and output" />
        <Metric label="Tenants" value={count(board.tenant_count)} hint={`${active} active`} />
      </MetricStrip>
      <Section title="Activity" description="Daily spend, billed requests, and requests stopped by a guardrail, across every tenant.">
        <UsageChart refreshKey={board} onError={onError} />
      </Section>
      <Section title="Tenants" description="Select a tenant to manage its keys, plan, ledger, and logs.">
        {board.tenants.length === 0 ? (
          <EmptyPanel
            title="No tenants yet"
            description="Create a tenant, then issue it an API key."
            action={<Button onClick={onNewTenant}>Create tenant</Button>}
          />
        ) : (
          <Panel>
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Name</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Requests</TableHead>
                  <TableHead className="text-right">Spend</TableHead>
                  <TableHead className="w-56 pr-4">Budget used</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {board.tenants.map((tenant) => {
                  const used = tenant.plan ? percent(tenant.usage.spent_usd, tenant.plan.monthly_budget_usd) : 0
                  return (
                    <TableRow
                      key={tenant.id}
                      className="cursor-pointer"
                      onClick={() => navigate({ page: "tenant", id: tenant.id })}
                    >
                      <TableCell className="py-3 pl-4">
                        <div className="flex flex-col">
                          <span className="font-medium">{tenant.name}</span>
                          <span className="font-mono text-xs text-muted-foreground">{tenant.id}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{planName(tenant.plan?.id)}</Badge>
                      </TableCell>
                      <TableCell>
                        <StatusDot active={tenant.is_active} />
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{count(tenant.usage.request_count)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{money(tenant.usage.spent_usd)}</TableCell>
                      <TableCell className="pr-4">
                        <div className="flex items-center gap-3">
                          <UsageMeter value={used} warn={tenant.warning} />
                          <span className="w-12 shrink-0 text-right font-mono text-xs text-muted-foreground tabular-nums">
                            {percentLabel(used)}
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </Panel>
        )}
      </Section>
    </div>
  )
}
