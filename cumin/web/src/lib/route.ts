import { useEffect, useState } from "react"

export type Route =
  | { page: "overview" }
  | { page: "plans" }
  | { page: "playground"; tenant?: string }
  | { page: "tenant"; id: string }

function parse(hash: string): Route {
  const tenant = hash.match(/^#\/tenants\/([^/]+)$/)
  if (tenant) return { page: "tenant", id: decodeURIComponent(tenant[1]) }
  const playground = hash.match(/^#\/playground(?:\/([^/]+))?$/)
  if (playground) return { page: "playground", tenant: playground[1] ? decodeURIComponent(playground[1]) : undefined }
  if (hash === "#/plans") return { page: "plans" }
  return { page: "overview" }
}

export function navigate(route: Route) {
  if (route.page === "tenant") window.location.hash = `/tenants/${encodeURIComponent(route.id)}`
  else if (route.page === "plans") window.location.hash = "/plans"
  else if (route.page === "playground") window.location.hash = route.tenant ? `/playground/${encodeURIComponent(route.tenant)}` : "/playground"
  else window.location.hash = "/"
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash))
  useEffect(() => {
    const update = () => setRoute(parse(window.location.hash))
    window.addEventListener("hashchange", update)
    return () => window.removeEventListener("hashchange", update)
  }, [])
  return route
}
