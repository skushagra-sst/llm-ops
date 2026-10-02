"""HTTP summarize, usage, and the billing page, with a fake model."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from src.app import bootstrap_tenant, create_app
from src.models.tenant import Tenant
from src.services.db import Database
from src.services.fakellm_inference import FakeLLM
from src.services.tenant import TenantManager
from src.services.fetch import FetchError, fetch_page
import src.app as app_module


def main() -> None:
    try:
        fetch_page("http://127.0.0.1/secret")
    except FetchError:
        pass
    else:
        raise SystemExit("private url was fetched")

    database = Database()
    raw_key = bootstrap_tenant(database)
    app_module.fetch_page = lambda url: "Example Domain. This domain is for use in examples."
    llm = FakeLLM(text="Example Domain is reserved for documentation.")
    app = create_app(database, llm, admin_token="admin-test")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {raw_key}"}

    denied = client.get("/v1/usage")
    if denied.status_code != 401:
        raise SystemExit(f"missing key returned {denied.status_code}")

    created = client.post("/v1/summarize", headers=headers, json={"url": "https://1.1.1.1/"})
    if created.status_code != 200 or "Example Domain" not in created.json()["summary"]:
        raise SystemExit(f"summarize failed: {created.status_code} {created.text}")

    first = client.post(
        "/v1/summarize",
        headers={**headers, "Idempotency-Key": "page-1"},
        json={"url": "https://1.1.1.1/"},
    )
    second = client.post(
        "/v1/summarize",
        headers={**headers, "Idempotency-Key": "page-1"},
        json={"url": "https://1.1.1.1/"},
    )
    if first.status_code != 200 or not second.json()["replayed"] or len(llm.calls) != 2:
        raise SystemExit(f"replay failed: {second.status_code} {second.text} calls={len(llm.calls)}")

    usage = client.get("/v1/usage", headers=headers)
    body = usage.json()
    if usage.status_code != 200 or body["usage"]["request_count"] != 2:
        raise SystemExit(f"usage failed: {usage.status_code} {usage.text}")
    if body["tenant"]["name"] != "Acme":
        raise SystemExit("usage returned the wrong tenant")

    blocked = client.post("/v1/summarize", headers=headers, json={"url": "http://127.0.0.1/secret"})
    if blocked.status_code != 400:
        raise SystemExit(f"private url returned {blocked.status_code}")

    page = client.get("/billing", follow_redirects=False)
    if page.status_code != 307 or page.headers["location"] != "/admin":
        raise SystemExit("billing did not redirect to the admin page")

    TenantManager(database).add_tenant(Tenant(id="idle", name="Idle Co", plan_id="pro", is_active=False))
    refused = client.get("/v1/admin/tenants")
    if refused.status_code != 401:
        raise SystemExit(f"admin without a token returned {refused.status_code}")
    board = client.get("/v1/admin/tenants", headers={"X-Admin-Token": "admin-test"})
    if board.status_code != 200:
        raise SystemExit(f"admin board returned {board.status_code} {board.text}")
    listed = {item["name"]: item for item in board.json()["tenants"]}
    if set(listed) != {"Acme", "Idle Co"}:
        raise SystemExit(f"unexpected tenants {set(listed)}")
    if listed["Acme"]["usage"]["request_count"] != 2 or listed["Idle Co"]["is_active"]:
        raise SystemExit(f"unexpected board rows {board.text}")
    if board.json()["request_count"] != 2:
        raise SystemExit("admin totals ignored a tenant")
    admin_page = client.get("/admin")
    if admin_page.status_code != 200 or "Cumin admin" not in admin_page.text:
        raise SystemExit("admin page did not render")
    detail = client.get("/v1/admin/tenants/acme", headers={"X-Admin-Token": "admin-test"})
    if detail.status_code != 200 or detail.json()["usage"]["request_count"] != 2:
        raise SystemExit(f"tenant detail failed: {detail.status_code} {detail.text}")
    if detail.json()["replays"][0]["text"] != "Example Domain is reserved for documentation.":
        raise SystemExit("stored replay was missing")
    admin = {"X-Admin-Token": "admin-test"}
    key_rows = {row["prefix"]: row for row in detail.json()["keys"]}
    if key_rows[raw_key.split(".", 1)[0]]["requests"] != 2:
        raise SystemExit(f"per-key usage was wrong: {key_rows}")

    daily = client.get("/v1/admin/usage/daily", params={"tenant_id": "acme", "days": 7}, headers=admin).json()["days"]
    if len(daily) != 7 or daily[-1]["requests"] != 2:
        raise SystemExit(f"daily usage was wrong: {daily}")
    completed = client.get("/v1/admin/tenants/acme/logs", params={"kind": "completed"}, headers=admin).json()
    if completed["total"] != 2 or {event["outcome"] for event in completed["events"]} != {"completed"}:
        raise SystemExit(f"log filter failed: {completed}")
    found = client.get("/v1/admin/tenants/acme/logs", params={"q": "documentation", "limit": 1}, headers=admin).json()
    if found["total"] < 1 or len(found["events"]) != 1:
        raise SystemExit(f"log search failed: {found}")
    exported = client.get("/v1/admin/tenants/acme/logs.csv", headers=admin)
    if exported.status_code != 200 or not exported.text.startswith("time,event,key"):
        raise SystemExit(f"csv export failed: {exported.status_code}")
    rate = client.get("/v1/admin/tenants/acme/rate", headers=admin).json()
    if rate != {"used": 2, "limit": 60, "window_seconds": 60}:
        raise SystemExit(f"rate view was wrong: {rate}")

    played = client.post("/v1/admin/tenants/acme/playground", headers=admin, json={"url": "https://1.1.1.1/"})
    if played.status_code != 200 or played.json()["replayed"] or played.json()["rate"]["used"] != 3:
        raise SystemExit(f"playground failed: {played.status_code} {played.text}")
    refused_idle = client.post("/v1/admin/tenants/idle/playground", headers=admin, json={"url": "https://1.1.1.1/"})
    if refused_idle.status_code != 403:
        raise SystemExit(f"playground ran for an inactive tenant: {refused_idle.status_code}")
    console = {row["prefix"]: row for row in client.get("/v1/admin/tenants/acme", headers=admin).json()["keys"]}
    if console.get("console", {}).get("status") != "console" or console["console"]["requests"] != 1:
        raise SystemExit(f"playground spend was not attributed: {console}")
    issued = client.post("/v1/admin/tenants/acme/keys", headers={"X-Admin-Token": "admin-test"})
    if issued.status_code != 200 or "." not in issued.json()["api_key"]:
        raise SystemExit(f"issue key failed: {issued.text}")
    revoked = client.delete(
        "/v1/admin/keys/" + issued.json()["prefix"],
        headers={"X-Admin-Token": "admin-test"},
    )
    if revoked.status_code != 200:
        raise SystemExit(f"revoke failed: {revoked.text}")
    after = client.get("/v1/admin/tenants/acme", headers={"X-Admin-Token": "admin-test"})
    active = [row["prefix"] for row in after.json()["keys"] if row["status"] == "active"]
    if issued.json()["prefix"] in active:
        raise SystemExit("revoked key is still listed")

    created = client.post(
        "/v1/admin/tenants",
        headers={"X-Admin-Token": "admin-test"},
        json={"id": "harbor", "name": "Harbor", "plan_id": "pro"},
    )
    if created.status_code != 200 or created.json()["name"] != "Harbor":
        raise SystemExit(f"create tenant failed: {created.status_code} {created.text}")
    duplicate = client.post(
        "/v1/admin/tenants",
        headers={"X-Admin-Token": "admin-test"},
        json={"id": "harbor", "name": "Harbor", "plan_id": "free"},
    )
    if duplicate.status_code != 409:
        raise SystemExit(f"duplicate tenant returned {duplicate.status_code}")
    renamed = client.post(
        "/v1/admin/tenants/harbor/name",
        headers={"X-Admin-Token": "admin-test"},
        json={"name": "Harbor Co"},
    )
    if renamed.status_code != 200 or renamed.json()["name"] != "Harbor Co":
        raise SystemExit(f"rename failed: {renamed.text}")
    removed = client.delete("/v1/admin/tenants/harbor", headers={"X-Admin-Token": "admin-test"})
    if removed.status_code != 200:
        raise SystemExit(f"delete failed: {removed.text}")
    gone = client.get("/v1/admin/tenants/harbor", headers={"X-Admin-Token": "admin-test"})
    if gone.status_code != 404:
        raise SystemExit("deleted tenant is still available")

    team = {
        "id": "team",
        "name": "Team",
        "monthly_budget_usd": "10",
        "soft_budget_usd": "8",
        "request_reserve_usd": "0.10",
        "requests_per_minute": 120,
        "monthly_token_budget": 2_000_000,
        "request_reserve_tokens": 8_000,
    }
    made = client.post("/v1/admin/plans", headers=admin, json=team)
    if made.status_code != 200 or made.json()["tenant_count"] != 0:
        raise SystemExit(f"create plan failed: {made.status_code} {made.text}")
    if client.post("/v1/admin/plans", headers=admin, json=team).status_code != 409:
        raise SystemExit("duplicate plan was accepted")
    upside_down = client.post("/v1/admin/plans", headers=admin, json={**team, "id": "odd", "soft_budget_usd": "20"})
    if upside_down.status_code != 400:
        raise SystemExit(f"soft warning above the budget returned {upside_down.status_code}")
    edited = client.put("/v1/admin/plans/team", headers=admin, json={**team, "requests_per_minute": 1})
    if edited.status_code != 200 or edited.json()["requests_per_minute"] != 1:
        raise SystemExit(f"edit plan failed: {edited.text}")
    client.post("/v1/admin/tenants/acme/plan", headers=admin, json={"plan_id": "team"})
    if client.post("/v1/summarize", headers=headers, json={"url": "https://1.1.1.1/"}).status_code != 429:
        raise SystemExit("edited rate limit was not enforced")
    if client.delete("/v1/admin/plans/team", headers=admin).status_code != 409:
        raise SystemExit("deleted a plan that tenants still use")
    client.post("/v1/admin/tenants/acme/plan", headers=admin, json={"plan_id": "free"})
    if client.delete("/v1/admin/plans/team", headers=admin).status_code != 200:
        raise SystemExit("delete plan failed")
    if "team" in {plan["id"] for plan in client.get("/v1/admin/plans", headers=admin).json()["plans"]}:
        raise SystemExit("deleted plan is still listed")

    print("api ok", body["usage"]["spent_usd"])


if __name__ == "__main__":
    main()
