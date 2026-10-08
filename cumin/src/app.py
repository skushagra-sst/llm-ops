import csv
import hmac
import io
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from src.models.llm import LLM, Message
from src.models.plan import Plan
from src.models.tenant import Tenant
from src.services.audit import AuditEvent, AuditLog, LogFilter
from src.services.budget import BudgetExceeded, BudgetGate
from src.services.db import Database
from src.services.fetch import FetchError, assert_public_url, fetch_page
from src.services.idempotency import IdempotencyStore
from src.services.moderation import OpenAIModerator, OutputRejected, PatternModerator, PromptRejected
from src.services.plans import PlanExists, PlanInUse, PlanStore
from src.services.rate_limit import RateLimitExceeded, RateLimiter
from src.services.redis import RedisRateLimiter
from src.services.request import RequestHandler
from src.services.tenant import AuthenticationError, TenantExists, TenantManager

_ADMIN_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


class SummarizeIn(BaseModel):
    url: HttpUrl
    model: str = "gpt-4o-mini"


class ActiveIn(BaseModel):
    is_active: bool


class PlanIn(BaseModel):
    plan_id: str


class TenantIn(BaseModel):
    id: str
    name: str
    plan_id: str = "free"


class NameIn(BaseModel):
    name: str


class PlanFieldsIn(BaseModel):
    name: str
    monthly_budget_usd: Decimal = Field(ge=0, max_digits=14, decimal_places=6)
    soft_budget_usd: Decimal = Field(ge=0, max_digits=14, decimal_places=6)
    request_reserve_usd: Decimal = Field(ge=0, max_digits=14, decimal_places=6)
    requests_per_minute: int = Field(ge=1, le=1_000_000)
    monthly_token_budget: int = Field(ge=0, le=10**12)
    request_reserve_tokens: int = Field(ge=1, le=10**9)


class NewPlanIn(PlanFieldsIn):
    id: str


class PlaygroundIn(BaseModel):
    url: HttpUrl
    model: str = "gpt-4o-mini"
    idempotency_key: str | None = Field(default=None, max_length=200)


_TENANT_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_LOG_KINDS = ("completed", "blocked", "replay", "admin")
# Audit rows from the admin playground carry this in place of a key prefix.
CONSOLE_KEY = "console"


def create_app(
    database: Database,
    llm: LLM,
    moderator: PatternModerator | OpenAIModerator | None = None,
    limiter: RateLimiter | RedisRateLimiter | None = None,
    admin_token: str | None = None,
) -> FastAPI:
    tenants = TenantManager(database)
    plans = PlanStore(database)
    budget = BudgetGate(plans=plans, database=database)
    audit = AuditLog(database)
    idempotency = IdempotencyStore(database)
    limiter = limiter or RateLimiter()
    handler = RequestHandler(
        tenants,
        budget,
        llm,
        limiter,
        audit,
        idempotency,
        moderator=moderator or PatternModerator(),
    )
    app = FastAPI(title="Cumin")
    app.state.handler = handler
    app.state.tenants = tenants
    app.state.budget = budget
    app.state.audit = audit
    app.state.idempotency = idempotency
    app.state.admin_token = admin_token if admin_token is not None else os.environ.get("CUMIN_ADMIN_TOKEN", "")

    @app.get("/")
    @app.get("/billing")
    def home() -> RedirectResponse:
        return RedirectResponse("/admin")

    if _ADMIN_DIST.is_dir():
        app.mount("/admin", StaticFiles(directory=_ADMIN_DIST, html=True), name="admin")
    else:

        @app.get("/admin", response_class=HTMLResponse)
        def admin_missing() -> str:
            return "Admin UI is not built. From cumin/web, run npm install and npm run build."

    @app.get("/v1/admin/tenants")
    def admin_tenants(x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        rows = []
        spent_usd = Decimal(0)
        spent_tokens = 0
        request_count = 0
        for tenant in tenants.list_tenants():
            try:
                plan = budget.plan_for(tenant)
            except KeyError:
                plan = None
            month = budget.month_usage(tenant.id)
            spent_usd += month.spent_usd
            spent_tokens += month.spent_tokens
            request_count += month.request_count
            rows.append(
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "is_active": tenant.is_active,
                    "plan": None
                    if plan is None
                    else {
                        "id": plan.id,
                        "monthly_budget_usd": str(plan.monthly_budget_usd),
                        "soft_budget_usd": str(plan.soft_budget_usd),
                        "monthly_token_budget": plan.monthly_token_budget,
                    },
                    "usage": {
                        "request_count": month.request_count,
                        "input_tokens": month.input_tokens,
                        "output_tokens": month.output_tokens,
                        "cached_input_tokens": month.cached_input_tokens,
                        "spent_usd": str(month.spent_usd),
                        "spent_tokens": month.spent_tokens,
                    },
                    "warning": plan is not None and month.spent_usd >= plan.soft_budget_usd,
                }
            )
        rows.sort(key=lambda row: Decimal(row["usage"]["spent_usd"]), reverse=True)
        return {
            "tenant_count": len(rows),
            "request_count": request_count,
            "spent_usd": str(spent_usd),
            "spent_tokens": spent_tokens,
            "tenants": rows,
            "plans": _plans_json(plans),
        }

    @app.get("/v1/admin/plans")
    def admin_plans(x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        return {"plans": _plans_json(plans)}

    @app.post("/v1/admin/plans")
    def admin_create_plan(body: NewPlanIn, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        plan = _plan_from(_clean_id(body.id, "plan"), body)
        try:
            plans.create(plan)
        except PlanExists as exc:
            raise HTTPException(status_code=409, detail="plan id already exists") from exc
        return _plan_json(plan, 0)

    @app.put("/v1/admin/plans/{plan_id}")
    def admin_update_plan(
        plan_id: str,
        body: PlanFieldsIn,
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        try:
            plan = plans.update(_plan_from(plan_id, body))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="plan not found") from exc
        return _plan_json(plan, plans.tenant_counts().get(plan_id, 0))

    @app.delete("/v1/admin/plans/{plan_id}")
    def admin_delete_plan(plan_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        try:
            plans.delete(plan_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="plan not found") from exc
        except PlanInUse as exc:
            raise HTTPException(status_code=409, detail="move this plan's tenants to another plan first") from exc
        return {"deleted": plan_id}

    @app.post("/v1/admin/tenants")
    def admin_create_tenant(body: TenantIn, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        tenant_id = _clean_id(body.id)
        name = _clean_name(body.name)
        if body.plan_id not in plans:
            raise HTTPException(status_code=400, detail="unknown plan")
        try:
            tenants.create_tenant(Tenant(id=tenant_id, name=name, plan_id=body.plan_id))
        except TenantExists as exc:
            raise HTTPException(status_code=409, detail="tenant id already exists") from exc
        audit.record(
            tenant_id=tenant_id,
            key_prefix="",
            model="admin",
            outcome="tenant_created",
            cost_usd=None,
            request_text=f"created tenant {name}",
            response_text=None,
        )
        return _tenant_detail(tenants, budget, audit, idempotency, tenant_id)

    @app.get("/v1/admin/tenants/{tenant_id}")
    def admin_tenant(tenant_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        return _tenant_detail(tenants, budget, audit, idempotency, tenant_id)

    @app.post("/v1/admin/tenants/{tenant_id}/keys")
    def admin_issue_key(tenant_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        try:
            raw_key = tenants.issue_api_key(tenant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc
        prefix = raw_key.split(".", 1)[0]
        audit.record(
            tenant_id=tenant_id,
            key_prefix=prefix,
            model="admin",
            outcome="key_issued",
            cost_usd=None,
            request_text="issued api key",
            response_text=None,
        )
        return {"prefix": prefix, "api_key": raw_key}

    @app.delete("/v1/admin/keys/{prefix}")
    def admin_revoke_key(prefix: str, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        try:
            tenant_id = tenants.revoke_key(prefix)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="key not found") from exc
        audit.record(
            tenant_id=tenant_id,
            key_prefix=prefix,
            model="admin",
            outcome="key_revoked",
            cost_usd=None,
            request_text="revoked api key",
            response_text=None,
        )
        return {"revoked": prefix}

    @app.post("/v1/admin/tenants/{tenant_id}/active")
    def admin_set_active(
        tenant_id: str,
        body: ActiveIn,
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        try:
            tenant = tenants.set_active(tenant_id, body.is_active)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc
        audit.record(
            tenant_id=tenant_id,
            key_prefix="",
            model="admin",
            outcome="activated" if tenant.is_active else "deactivated",
            cost_usd=None,
            request_text="set tenant active" if tenant.is_active else "set tenant inactive",
            response_text=None,
        )
        return _tenant_detail(tenants, budget, audit, idempotency, tenant_id)

    @app.post("/v1/admin/tenants/{tenant_id}/plan")
    def admin_set_plan(
        tenant_id: str,
        body: PlanIn,
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        if body.plan_id not in plans:
            raise HTTPException(status_code=400, detail="unknown plan")
        try:
            tenants.set_plan(tenant_id, body.plan_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc
        audit.record(
            tenant_id=tenant_id,
            key_prefix="",
            model="admin",
            outcome="plan_changed",
            cost_usd=None,
            request_text=f"plan set to {body.plan_id}",
            response_text=None,
        )
        return _tenant_detail(tenants, budget, audit, idempotency, tenant_id)

    @app.post("/v1/admin/tenants/{tenant_id}/name")
    def admin_rename_tenant(
        tenant_id: str,
        body: NameIn,
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        name = _clean_name(body.name)
        try:
            tenants.rename(tenant_id, name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc
        audit.record(
            tenant_id=tenant_id,
            key_prefix="",
            model="admin",
            outcome="renamed",
            cost_usd=None,
            request_text=f"renamed to {name}",
            response_text=None,
        )
        return _tenant_detail(tenants, budget, audit, idempotency, tenant_id)

    @app.delete("/v1/admin/tenants/{tenant_id}")
    def admin_delete_tenant(tenant_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        try:
            tenants.delete_tenant(tenant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc
        return {"deleted": tenant_id}

    @app.get("/v1/admin/usage/daily")
    def admin_daily_usage(
        tenant_id: str | None = None,
        days: int = Query(default=30, ge=1, le=90),
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        end = datetime.now(timezone.utc).date()
        return {"days": audit.daily(tenant_id, end - timedelta(days=days - 1), end)}

    @app.get("/v1/admin/tenants/{tenant_id}/logs")
    def admin_logs(
        tenant_id: str,
        kind: str | None = None,
        key: str | None = None,
        q: str | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int = Query(default=25, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        _require_tenant(tenants, tenant_id)
        total, events = audit.search(tenant_id, _log_filter(kind, key, q, since, until), limit, offset)
        return {"total": total, "events": [_event_json(event) for event in events]}

    @app.get("/v1/admin/tenants/{tenant_id}/logs.csv")
    def admin_logs_csv(
        tenant_id: str,
        kind: str | None = None,
        key: str | None = None,
        q: str | None = None,
        since: date | None = None,
        until: date | None = None,
        x_admin_token: str | None = Header(default=None),
    ) -> Response:
        _require_admin(x_admin_token, app.state.admin_token)
        _require_tenant(tenants, tenant_id)
        _total, events = audit.search(tenant_id, _log_filter(kind, key, q, since, until), limit=10_000)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["time", "event", "key", "model", "cost_usd", "request", "response", "handler_latency_ms"])
        for event in events:
            writer.writerow(
                [
                    event.created_at or "",
                    event.outcome,
                    event.key_prefix,
                    event.model,
                    "" if event.cost_usd is None else str(event.cost_usd),
                    event.request_text,
                    event.response_text or "",
                    "" if event.latency_ms is None else event.latency_ms,
                ]
            )
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{tenant_id}-logs.csv"'},
        )

    @app.get("/v1/admin/tenants/{tenant_id}/rate")
    def admin_rate(tenant_id: str, x_admin_token: str | None = Header(default=None)) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        return _rate_json(limiter, budget, _require_tenant(tenants, tenant_id))

    @app.post("/v1/admin/tenants/{tenant_id}/playground")
    def admin_playground(
        tenant_id: str,
        body: PlaygroundIn,
        x_admin_token: str | None = Header(default=None),
    ) -> dict:
        _require_admin(x_admin_token, app.state.admin_token)
        tenant = _require_tenant(tenants, tenant_id)
        if not tenant.is_active:
            raise HTTPException(status_code=403, detail="tenant is inactive")
        started = time.perf_counter()
        messages = _summary_messages(str(body.url))
        idempotency_key = (body.idempotency_key or "").strip() or None
        result = _guarded(lambda: handler.handle_tenant(tenant, CONSOLE_KEY, messages, body.model, idempotency_key))
        return {
            **_summary_json(result),
            "cost_usd": str(result.cost_usd),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "rate": _rate_json(limiter, budget, tenant),
        }

    @app.get("/v1/usage")
    def usage(authorization: str | None = Header(default=None)) -> dict:
        tenant = _authenticate(handler, authorization)
        plan = budget.plan_for(tenant)
        month = budget.month_usage(tenant.id)
        return {
            "tenant": {"id": tenant.id, "name": tenant.name},
            "plan": {
                "id": plan.id,
                "monthly_budget_usd": str(plan.monthly_budget_usd),
                "soft_budget_usd": str(plan.soft_budget_usd),
                "monthly_token_budget": plan.monthly_token_budget,
            },
            "usage": {
                "request_count": month.request_count,
                "input_tokens": month.input_tokens,
                "output_tokens": month.output_tokens,
                "cached_input_tokens": month.cached_input_tokens,
                "spent_usd": str(month.spent_usd),
                "spent_tokens": month.spent_tokens,
            },
            "warning": month.spent_usd >= plan.soft_budget_usd,
            "events": [
                {
                    "outcome": event.outcome,
                    "model": event.model,
                    "cost_usd": None if event.cost_usd is None else str(event.cost_usd),
                    "request_text": event.request_text,
                    "handler_latency_ms": event.latency_ms,
                }
                for event in audit.for_tenant(tenant.id, limit=12)
            ],
        }

    @app.post("/v1/summarize")
    def summarize(
        body: SummarizeIn,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        raw_key = _bearer(authorization)
        messages = _summary_messages(str(body.url))
        result = _guarded(lambda: handler.handle(raw_key, messages, body.model, idempotency_key))
        return _summary_json(result)

    return app


def _summary_messages(url: str) -> list[Message]:
    try:
        assert_public_url(url)
        page = fetch_page(url)
    except FetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return summary_prompt(url, page)


def summary_prompt(url: str, page: str) -> list[Message]:
    return [
        Message(
            role="system",
            content="Summarize the page in a few sentences. Use only the page text.",
        ),
        Message(role="user", content=f"URL: {url}\n\n{page}"),
    ]


def _guarded(run):
    try:
        return run()
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="invalid api key") from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except BudgetExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except PromptRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OutputRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _summary_json(result) -> dict:
    usage = result.completion.usage
    return {
        "summary": result.completion.text,
        "model": result.completion.model,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
        },
        "spent_usd": str(result.spent_usd),
        "warning": result.warning,
        "replayed": result.replayed,
        "cost_usd": str(result.cost_usd),
        "handler_latency_ms": result.latency_ms,
    }


def _require_tenant(tenants: TenantManager, tenant_id: str) -> Tenant:
    try:
        return tenants.get_tenant(tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="tenant not found") from exc


def _rate_json(limiter, budget: BudgetGate, tenant: Tenant) -> dict:
    try:
        cap = budget.plan_for(tenant).requests_per_minute
    except KeyError:
        cap = 0
    return {"used": limiter.current(tenant.id), "limit": cap, "window_seconds": 60}


def _log_filter(kind, key, q, since, until) -> LogFilter:
    if kind and kind not in _LOG_KINDS:
        raise HTTPException(status_code=400, detail="unknown log kind")
    text = (q or "").strip()[:200] or None
    return LogFilter(kind=kind or None, key_prefix=key or None, text=text, since=since, until=until)


def _event_json(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "created_at": event.created_at,
        "handler_latency_ms": event.latency_ms,
        "outcome": event.outcome,
        "model": event.model,
        "key_prefix": event.key_prefix,
        "cost_usd": None if event.cost_usd is None else str(event.cost_usd),
        "request_text": event.request_text,
        "response_text": event.response_text,
    }


def _key_json(prefix: str, status: str, created_at: str | None, usage: dict | None) -> dict:
    usage = usage or {"requests": 0, "spend_usd": Decimal(0), "last_used": None}
    return {
        "prefix": prefix,
        "status": status,
        "created_at": created_at,
        "requests": usage["requests"],
        "spend_usd": str(usage["spend_usd"]),
        "last_used": usage["last_used"],
    }


def bootstrap_tenant(database: Database) -> str | None:
    tenants = TenantManager(database)
    try:
        tenants.get_tenant("acme")
    except KeyError:
        tenants.add_tenant(Tenant(id="acme", name="Acme", plan_id="free"))
        return tenants.issue_api_key("acme")
    return None


def limiter_from_env() -> RateLimiter | RedisRateLimiter:
    url = os.environ.get("REDIS_URL")
    if url:
        return RedisRateLimiter(url)
    return RateLimiter()


def _require_admin(presented: str | None, expected: str) -> None:
    if not expected or presented is None or not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="invalid admin token")


def _authenticate(handler: RequestHandler, authorization: str | None):
    try:
        return handler.tenants.authenticate(_bearer(authorization))
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="invalid api key") from exc


def _clean_id(value: str, kind: str = "tenant") -> str:
    if not _TENANT_ID.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail=f"{kind} id must start with a letter and use lowercase letters, numbers, and hyphens",
        )
    return value


def _clean_name(name: str, kind: str = "tenant") -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 80:
        raise HTTPException(status_code=400, detail=f"{kind} name is required")
    return cleaned


def _plan_from(plan_id: str, body: PlanFieldsIn) -> Plan:
    if body.soft_budget_usd > body.monthly_budget_usd:
        raise HTTPException(status_code=400, detail="soft warning can't be above the monthly budget")
    return Plan(
        id=plan_id,
        name=_clean_name(body.name, "plan"),
        monthly_budget_usd=body.monthly_budget_usd,
        soft_budget_usd=body.soft_budget_usd,
        request_reserve_usd=body.request_reserve_usd,
        requests_per_minute=body.requests_per_minute,
        monthly_token_budget=body.monthly_token_budget,
        request_reserve_tokens=body.request_reserve_tokens,
    )


def _plans_json(plans: PlanStore) -> list[dict]:
    counts = plans.tenant_counts()
    return [_plan_json(plan, counts.get(plan.id, 0)) for plan in plans.list_plans()]


def _plan_json(plan: Plan, tenant_count: int | None = None) -> dict:
    body = {
        "id": plan.id,
        "name": plan.name,
        "monthly_budget_usd": str(plan.monthly_budget_usd),
        "soft_budget_usd": str(plan.soft_budget_usd),
        "request_reserve_usd": str(plan.request_reserve_usd),
        "monthly_token_budget": plan.monthly_token_budget,
        "request_reserve_tokens": plan.request_reserve_tokens,
        "requests_per_minute": plan.requests_per_minute,
    }
    if tenant_count is not None:
        body["tenant_count"] = tenant_count
    return body


def _tenant_detail(tenants, budget, audit, idempotency, tenant_id: str) -> dict:
    try:
        tenant = tenants.get_tenant(tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="tenant not found") from exc
    try:
        plan = budget.plan_for(tenant)
    except KeyError:
        plan = None
    month = budget.month_usage(tenant.id)
    by_key = audit.key_usage(tenant.id)
    keys = [_key_json(row["prefix"], "active", row["created_at"], by_key.pop(row["prefix"], None)) for row in tenants.key_rows(tenant.id)]
    keys += [
        _key_json(prefix, "console" if prefix == CONSOLE_KEY else "revoked", None, usage)
        for prefix, usage in sorted(by_key.items(), key=lambda item: item[1]["spend_usd"], reverse=True)
    ]
    return {
        "id": tenant.id,
        "name": tenant.name,
        "is_active": tenant.is_active,
        "plan": None if plan is None else _plan_json(plan),
        "usage": {
            "request_count": month.request_count,
            "input_tokens": month.input_tokens,
            "output_tokens": month.output_tokens,
            "cached_input_tokens": month.cached_input_tokens,
            "spent_usd": str(month.spent_usd),
            "spent_tokens": month.spent_tokens,
        },
        "warning": plan is not None and month.spent_usd >= plan.soft_budget_usd,
        "keys": keys,
        "ledger": budget.ledger(tenant.id),
        "replays": idempotency.list_for_tenant(tenant.id),
    }


def _bearer(authorization: str | None) -> str:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing api key")
    return authorization.split(" ", 1)[1].strip()
