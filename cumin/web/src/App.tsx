import { useCallback, useState } from "react"
import { toast } from "sonner"

import { BoardView } from "@/components/admin/board"
import { Login } from "@/components/admin/login"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AuthError, clearToken, getToken } from "@/lib/api"

export default function App() {
  const [authed, setAuthed] = useState(() => getToken() !== "")

  const signOut = useCallback(() => {
    clearToken()
    setAuthed(false)
  }, [])

  const onError = useCallback((error: unknown) => {
    if (error instanceof AuthError) {
      setAuthed(false)
      return
    }
    toast.error(error instanceof Error ? error.message : "The request failed.")
  }, [])

  return (
    <TooltipProvider>
      <Toaster position="bottom-right" />
      {authed ? <BoardView onSignOut={signOut} onError={onError} /> : <Login onSuccess={() => setAuthed(true)} />}
    </TooltipProvider>
  )
}
