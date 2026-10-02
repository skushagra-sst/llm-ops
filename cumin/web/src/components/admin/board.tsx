import { useCallback, useEffect, useState } from "react"
import { ChevronsUpDownIcon, FlaskConicalIcon, LayersIcon, LayoutGridIcon, LogOutIcon, PlusIcon } from "lucide-react"

import { NewTenantDialog } from "@/components/admin/new-tenant"
import { Overview } from "@/components/admin/overview"
import { Playground } from "@/components/admin/playground"
import { PlansPage } from "@/components/admin/plans"
import { TenantDetailView } from "@/components/admin/tenant-detail"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Separator } from "@/components/ui/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyPanel } from "@/components/admin/parts"
import { api } from "@/lib/api"
import { navigate, useRoute } from "@/lib/route"
import type { Board, TenantDetail } from "@/lib/types"
import { cn } from "cn"

export function BoardView({
  onSignOut,
  onError,
}: {
  onSignOut: () => void
  onError: (error: unknown) => void
}) {
  const route = useRoute()
  const [board, setBoard] = useState<Board | null>(null)
  const [detail, setDetail] = useState<TenantDetail | null>(null)
  const [missing, setMissing] = useState(false)
  const [creating, setCreating] = useState(false)

  const loadBoard = useCallback(async () => {
    setBoard(await api<Board>("/v1/admin/tenants"))
  }, [])

  const loadDetail = useCallback(async (id: string) => {
    try {
      setDetail(await api<TenantDetail>(`/v1/admin/tenants/${encodeURIComponent(id)}`))
      setMissing(false)
    } catch (error) {
      if (error instanceof Error && error.message === "tenant not found") {
        setDetail(null)
        setMissing(true)
        return
      }
      throw error
    }
  }, [])

  useEffect(() => {
    loadBoard().catch(onError)
  }, [loadBoard, onError])

  useEffect(() => {
    if (route.page !== "tenant") return
    loadDetail(route.id).catch(onError)
  }, [route, loadDetail, onError])

  const refresh = useCallback(async () => {
    try {
      await loadBoard()
      if (route.page === "tenant") await loadDetail(route.id)
    } catch (error) {
      onError(error)
    }
  }, [loadBoard, loadDetail, onError, route])

  const tenants = board?.tenants ?? []
  const plans = board?.plans ?? []
  const sorted = [...tenants].sort((a, b) => a.name.localeCompare(b.name))
  const current = route.page === "tenant" ? tenants.find((tenant) => tenant.id === route.id) : undefined

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader className="px-3 pt-4">
          <div className="flex items-center gap-2 px-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-brand font-heading text-base text-white">C</span>
            <span className="font-heading text-lg tracking-tight">Cumin</span>
            <span className="ml-auto rounded-md border bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground">Admin</span>
          </div>
        </SidebarHeader>
        <SidebarContent className="px-1">
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton isActive={route.page === "overview"} onClick={() => navigate({ page: "overview" })}>
                    <LayoutGridIcon />
                    <span>Overview</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton isActive={route.page === "playground"} onClick={() => navigate({ page: "playground" })}>
                    <FlaskConicalIcon />
                    <span>Playground</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton isActive={route.page === "plans"} onClick={() => navigate({ page: "plans" })}>
                    <LayersIcon />
                    <span>Plans</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
          <SidebarGroup>
            <SidebarGroupLabel>Tenants</SidebarGroupLabel>
            <SidebarGroupAction title="Create tenant" onClick={() => setCreating(true)}>
              <PlusIcon />
              <span className="sr-only">Create tenant</span>
            </SidebarGroupAction>
            <SidebarGroupContent>
              <SidebarMenu>
                {board === null
                  ? Array.from({ length: 3 }, (_, index) => (
                      <SidebarMenuItem key={index}>
                        <Skeleton className="h-8 w-full" />
                      </SidebarMenuItem>
                    ))
                  : sorted.map((tenant) => (
                      <SidebarMenuItem key={tenant.id}>
                        <SidebarMenuButton
                          isActive={route.page === "tenant" && route.id === tenant.id}
                          onClick={() => navigate({ page: "tenant", id: tenant.id })}
                        >
                          <span
                            className={cn(
                              "flex size-5 shrink-0 items-center justify-center rounded text-[11px] font-medium",
                              tenant.is_active ? "bg-background text-foreground ring-1 ring-border" : "bg-muted text-muted-foreground",
                            )}
                          >
                            {tenant.name.charAt(0).toUpperCase()}
                          </span>
                          <span className={cn(!tenant.is_active && "text-muted-foreground")}>{tenant.name}</span>
                        </SidebarMenuButton>
                        {!tenant.is_active ? <SidebarMenuBadge className="text-[10px] text-muted-foreground">Off</SidebarMenuBadge> : null}
                      </SidebarMenuItem>
                    ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton size="lg" className="border bg-background">
                <span className="flex size-7 items-center justify-center rounded-full bg-muted text-xs font-medium">A</span>
                <span className="flex flex-col text-left leading-tight">
                  <span className="text-sm font-medium">Administrator</span>
                  <span className="text-xs text-muted-foreground">Local console</span>
                </span>
                <ChevronsUpDownIcon className="ml-auto text-muted-foreground" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" className="w-56">
              <DropdownMenuLabel className="text-xs text-muted-foreground">Signed in with admin token</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={onSignOut}>
                <LogOutIcon />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4! self-center!" />
          <Breadcrumb>
            <BreadcrumbList>
              {route.page !== "tenant" ? (
                <BreadcrumbItem>
                  <BreadcrumbPage>{route.page === "overview" ? "Overview" : route.page === "plans" ? "Plans" : "Playground"}</BreadcrumbPage>
                </BreadcrumbItem>
              ) : (
                <>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="#/">Tenants</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{current?.name ?? (route.page === "tenant" ? route.id : "")}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
            </BreadcrumbList>
          </Breadcrumb>
        </header>
        <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-10">
          {route.page === "overview" ? (
            board ? (
              <Overview board={board} plans={plans} onNewTenant={() => setCreating(true)} onError={onError} />
            ) : (
              <LoadingPage />
            )
          ) : route.page === "plans" ? (
            board ? <PlansPage plans={plans} onChange={refresh} onError={onError} /> : <LoadingPage />
          ) : route.page === "playground" ? (
            board ? (
              <Playground tenants={sorted} tenantId={route.tenant} onRan={() => loadBoard().catch(onError)} onError={onError} />
            ) : (
              <LoadingPage />
            )
          ) : missing ? (
            <EmptyPanel title="Tenant not found" description="It may have been deleted. Pick another tenant from the sidebar." />
          ) : detail && detail.id === route.id ? (
            <TenantDetailView
              detail={detail}
              plans={plans}
              onChange={refresh}
              onDeleted={async () => {
                navigate({ page: "overview" })
                await loadBoard()
              }}
              onError={onError}
            />
          ) : (
            <LoadingPage />
          )}
        </div>
      </SidebarInset>
      <NewTenantDialog
        open={creating}
        onOpenChange={setCreating}
        plans={plans}
        onError={onError}
        onCreated={async (id) => {
          await loadBoard()
          navigate({ page: "tenant", id })
        }}
      />
    </SidebarProvider>
  )
}

function LoadingPage() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}
