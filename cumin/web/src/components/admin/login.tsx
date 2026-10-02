import { useState, type FormEvent } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { AuthError, api, setToken } from "@/lib/api"
import type { Board } from "@/lib/types"

export function Login({ onSuccess }: { onSuccess: () => void }) {
  const [token, setValue] = useState("")
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setPending(true)
    setToken(token.trim())
    try {
      await api<Board>("/v1/admin/tenants")
      onSuccess()
    } catch (caught) {
      setError(caught instanceof AuthError ? caught.message : "The server didn’t respond. Check that it’s running.")
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-sidebar px-6">
      <div className="flex w-full max-w-sm flex-col gap-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <span className="flex size-10 items-center justify-center rounded-lg bg-brand font-heading text-xl text-white">C</span>
          <div className="flex flex-col gap-1">
            <h1 className="font-heading text-2xl tracking-tight">Sign in to Cumin</h1>
            <p className="text-sm text-muted-foreground">Use the admin token printed when the server started.</p>
          </div>
        </div>
        <form className="flex flex-col gap-4 rounded-xl border bg-background p-6 shadow-xs" onSubmit={submit}>
          <div className="flex flex-col gap-2">
            <Label htmlFor="token">Admin token</Label>
            <Input
              id="token"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={token}
              onChange={(event) => setValue(event.target.value)}
              required
            />
          </div>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Signing in…" : "Continue"}
          </Button>
        </form>
      </div>
    </main>
  )
}
