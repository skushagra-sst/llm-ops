import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api } from "@/lib/api"
import type { Plan, TenantDetail } from "@/lib/types"

export function NewTenantDialog({
  open,
  onOpenChange,
  plans,
  onCreated,
  onError,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  plans: Plan[]
  onCreated: (id: string) => Promise<void>
  onError: (error: unknown) => void
}) {
  const [name, setName] = useState("")
  const [tenantId, setTenantId] = useState("")
  const [idEdited, setIdEdited] = useState(false)
  const [planId, setPlanId] = useState("free")
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!open) return
    setName("")
    setTenantId("")
    setIdEdited(false)
    setPlanId(plans.find((plan) => plan.id === "free")?.id ?? plans[0]?.id ?? "free")
  }, [open, plans])

  async function create() {
    setPending(true)
    try {
      const created = await api<TenantDetail>("/v1/admin/tenants", {
        method: "POST",
        body: { id: tenantId, name, plan_id: planId },
      })
      onOpenChange(false)
      await onCreated(created.id)
    } catch (error) {
      onError(error)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create tenant</DialogTitle>
          <DialogDescription>Each tenant gets its own keys, budget, and ledger.</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            void create()
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="tenant-name">Name</Label>
            <Input
              id="tenant-name"
              placeholder="Acme Inc"
              value={name}
              onChange={(event) => {
                const value = event.target.value
                setName(value)
                if (!idEdited) setTenantId(slug(value))
              }}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="tenant-id">Tenant id</Label>
            <Input
              id="tenant-id"
              className="font-mono"
              placeholder="acme"
              value={tenantId}
              onChange={(event) => {
                setIdEdited(true)
                setTenantId(event.target.value)
              }}
              required
            />
            <p className="text-xs text-muted-foreground">Lowercase letters, numbers, and hyphens. This can’t be changed later.</p>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Plan</Label>
            <Select value={planId} onValueChange={setPlanId}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {plans.map((plan) => (
                  <SelectItem key={plan.id} value={plan.id}>
                    {plan.name} · ${Number(plan.monthly_budget_usd).toFixed(2)} per month
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Creating…" : "Create tenant"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function slug(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^[^a-z]+/, "")
    .slice(0, 40)
}
