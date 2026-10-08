import { useEffect, useState, type ChangeEvent, type ReactNode } from "react"
import { MoreHorizontalIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react"

import { slug } from "@/components/admin/new-tenant"
import { EmptyPanel, PageHeader, Panel } from "@/components/admin/parts"
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
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"
import { count, price } from "@/lib/format"
import type { Plan } from "@/lib/types"

type Draft = {
  id: string
  name: string
  monthly_budget_usd: string
  soft_budget_usd: string
  request_reserve_usd: string
  requests_per_minute: string
  monthly_token_budget: string
  request_reserve_tokens: string
}

const BLANK: Draft = {
  id: "",
  name: "",
  monthly_budget_usd: "10",
  soft_budget_usd: "8",
  request_reserve_usd: "0.05",
  requests_per_minute: "60",
  monthly_token_budget: "1000000",
  request_reserve_tokens: "8000",
}

export function PlansPage({ plans, onChange, onError }: { plans: Plan[]; onChange: () => Promise<void>; onError: (error: unknown) => void }) {
  const [editing, setEditing] = useState<Plan | "new" | null>(null)
  const [deleting, setDeleting] = useState<Plan | null>(null)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Plans"
        description="Plans set each tenant’s monthly budget, token allowance, and rate limit. Edits apply to every tenant on the plan right away."
        actions={
          <Button onClick={() => setEditing("new")}>
            <PlusIcon data-icon="inline-start" />
            Create plan
          </Button>
        }
      />
      {plans.length === 0 ? (
        <EmptyPanel
          title="No plans"
          description="Create a plan before you add tenants."
          action={<Button onClick={() => setEditing("new")}>Create plan</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} onEdit={() => setEditing(plan)} onDelete={() => setDeleting(plan)} />
          ))}
        </div>
      )}

      <PlanDialog
        target={editing}
        onClose={() => setEditing(null)}
        onSaved={onChange}
        onError={onError}
      />

      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleting?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              New tenants can’t be put on this plan any more. Past ledger entries keep the plan id they were billed under.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                const plan = deleting
                setDeleting(null)
                if (plan) {
                  void api(`/v1/admin/plans/${encodeURIComponent(plan.id)}`, { method: "DELETE" })
                    .then(onChange)
                    .catch(onError)
                }
              }}
            >
              Delete plan
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function PlanCard({ plan, onEdit, onDelete }: { plan: Plan; onEdit: () => void; onDelete: () => void }) {
  const tenants = plan.tenant_count ?? 0
  return (
    <Panel className="flex flex-col">
      <div className="flex items-start justify-between gap-3 p-4 pb-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="font-heading text-xl tracking-tight">{plan.name}</span>
          <span className="font-mono text-xs text-muted-foreground">{plan.id}</span>
        </div>
        <div className="flex items-center gap-1">
          <Badge variant={tenants > 0 ? "secondary" : "outline"}>
            {tenants} {tenants === 1 ? "tenant" : "tenants"}
          </Badge>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${plan.name}`}>
                <MoreHorizontalIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onSelect={onEdit}>
                <PencilIcon />
                Edit plan
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" disabled={tenants > 0} onSelect={onDelete}>
                <Trash2Icon />
                {tenants > 0 ? "In use, can’t delete" : "Delete plan"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <div className="flex items-baseline gap-1.5 px-4 pb-4 font-mono tabular-nums">
        <span className="text-2xl tracking-tight">{price(plan.monthly_budget_usd)}</span>
        <span className="text-sm text-muted-foreground">per month</span>
      </div>
      <Separator />
      <dl className="flex flex-1 flex-col gap-2.5 p-4 text-sm">
        <Fact label="Soft warning" value={price(plan.soft_budget_usd)} />
        <Fact label="Tokens per month" value={count(plan.monthly_token_budget)} />
        <Fact label="Rate limit" value={`${count(plan.requests_per_minute)} / min`} />
        <Fact label="Minimum hold" value={`${price(plan.request_reserve_usd)} · ${count(plan.request_reserve_tokens)} ${plan.request_reserve_tokens === 1 ? "token" : "tokens"}`} />
      </dl>
      <div className="border-t p-3">
        <Button variant="outline" size="sm" className="w-full" onClick={onEdit}>
          Edit plan
        </Button>
      </div>
    </Panel>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-xs tabular-nums">{value}</dd>
    </div>
  )
}

function PlanDialog({
  target,
  onClose,
  onSaved,
  onError,
}: {
  target: Plan | "new" | null
  onClose: () => void
  onSaved: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const creating = target === "new"
  const [draft, setDraft] = useState<Draft>(BLANK)
  const [idEdited, setIdEdited] = useState(false)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (target === null) return
    setIdEdited(false)
    setDraft(
      target === "new"
        ? BLANK
        : {
            id: target.id,
            name: target.name,
            monthly_budget_usd: String(Number(target.monthly_budget_usd)),
            soft_budget_usd: String(Number(target.soft_budget_usd)),
            request_reserve_usd: String(Number(target.request_reserve_usd)),
            requests_per_minute: String(target.requests_per_minute),
            monthly_token_budget: String(target.monthly_token_budget),
            request_reserve_tokens: String(target.request_reserve_tokens),
          },
    )
  }, [target])

  const set = (field: keyof Draft) => (event: ChangeEvent<HTMLInputElement>) =>
    setDraft((current) => ({ ...current, [field]: event.target.value }))

  const softTooHigh = Number(draft.soft_budget_usd) > Number(draft.monthly_budget_usd)

  async function save() {
    setPending(true)
    const body = {
      name: draft.name,
      monthly_budget_usd: draft.monthly_budget_usd,
      soft_budget_usd: draft.soft_budget_usd,
      request_reserve_usd: draft.request_reserve_usd,
      requests_per_minute: Number(draft.requests_per_minute),
      monthly_token_budget: Number(draft.monthly_token_budget),
      request_reserve_tokens: Number(draft.request_reserve_tokens),
    }
    try {
      if (creating) await api("/v1/admin/plans", { method: "POST", body: { ...body, id: draft.id } })
      else await api(`/v1/admin/plans/${encodeURIComponent(draft.id)}`, { method: "PUT", body })
      onClose()
      await onSaved()
    } catch (error) {
      onError(error)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{creating ? "Create plan" : `Edit ${draft.name || "plan"}`}</DialogTitle>
          <DialogDescription>
            {creating
              ? "Set the limits tenants on this plan get."
              : "Changes apply to every tenant on this plan from their next request."}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="plan-name">
              <Input
                id="plan-name"
                value={draft.name}
                placeholder="Team"
                required
                onChange={(event) => {
                  const value = event.target.value
                  setDraft((current) => ({ ...current, name: value, id: creating && !idEdited ? slug(value) : current.id }))
                }}
              />
            </Field>
            <Field label="Plan id" htmlFor="plan-id" hint={creating ? "Can’t be changed later." : undefined}>
              <Input
                id="plan-id"
                className="font-mono"
                value={draft.id}
                placeholder="team"
                required
                disabled={!creating}
                onChange={(event) => {
                  setIdEdited(true)
                  set("id")(event)
                }}
              />
            </Field>
          </div>

          <Group title="Budget">
            <Field label="Monthly budget" htmlFor="plan-budget" hint="Requests stop at this cap.">
              <Money id="plan-budget" value={draft.monthly_budget_usd} onChange={set("monthly_budget_usd")} />
            </Field>
            <Field
              label="Soft warning"
              htmlFor="plan-soft"
              hint={softTooHigh ? "Must not be above the monthly budget." : "Responses carry a warning past this."}
              invalid={softTooHigh}
            >
              <Money id="plan-soft" value={draft.soft_budget_usd} onChange={set("soft_budget_usd")} invalid={softTooHigh} />
            </Field>
          </Group>

          <Group title="Limits">
            <Field label="Tokens per month" htmlFor="plan-tokens">
              <Input id="plan-tokens" type="number" min={0} step={1} className="font-mono" value={draft.monthly_token_budget} onChange={set("monthly_token_budget")} required />
            </Field>
            <Field label="Requests per minute" htmlFor="plan-rpm">
              <Input id="plan-rpm" type="number" min={1} step={1} className="font-mono" value={draft.requests_per_minute} onChange={set("requests_per_minute")} required />
            </Field>
          </Group>

          <Group title="Minimum hold per request" description="Each request holds the larger of this and its own worst case (prompt bound plus the output cap) before the model call, then settles to the billed cost.">
            <Field label="Amount" htmlFor="plan-reserve">
              <Money id="plan-reserve" value={draft.request_reserve_usd} onChange={set("request_reserve_usd")} />
            </Field>
            <Field label="Tokens" htmlFor="plan-reserve-tokens">
              <Input id="plan-reserve-tokens" type="number" min={1} step={1} className="font-mono" value={draft.request_reserve_tokens} onChange={set("request_reserve_tokens")} required />
            </Field>
          </Group>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || softTooHigh}>
              {pending ? "Saving…" : creating ? "Create plan" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Group({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-3 border-t pt-4">
      <legend className="sr-only">{title}</legend>
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium">{title}</span>
        {description ? <span className="text-xs text-muted-foreground">{description}</span> : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  )
}

function Field({
  label,
  htmlFor,
  hint,
  invalid,
  children,
}: {
  label: string
  htmlFor: string
  hint?: string
  invalid?: boolean
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint ? <p className={invalid ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>{hint}</p> : null}
    </div>
  )
}

function Money({
  id,
  value,
  onChange,
  invalid,
}: {
  id: string
  value: string
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  invalid?: boolean
}) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-muted-foreground">$</span>
      <Input
        id={id}
        type="number"
        min={0}
        step="any"
        className="pl-6 font-mono"
        value={value}
        onChange={onChange}
        aria-invalid={invalid || undefined}
        required
      />
    </div>
  )
}
