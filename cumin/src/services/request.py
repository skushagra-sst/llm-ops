from dataclasses import dataclass
from decimal import Decimal

from src.models.llm import Completion, LLM, Message
from src.models.tenant import Tenant
from src.services.audit import AuditLog
from src.services.budget import BudgetExceeded, BudgetGate
from src.services.idempotency import IdempotencyStore
from src.services.moderation import OpenAIModerator, OutputRejected, PatternModerator, PromptRejected
from src.services.rate_limit import RateLimitExceeded, RateLimiter
from src.services.tenant import AuthenticationError, TenantManager


@dataclass(frozen=True)
class RequestResult:
    completion: Completion
    spent_usd: Decimal
    warning: bool
    replayed: bool
    cost_usd: Decimal = Decimal(0)


class RequestHandler:
    def __init__(
        self,
        tenants: TenantManager,
        budget: BudgetGate,
        llm: LLM,
        limiter: RateLimiter,
        audit: AuditLog,
        idempotency: IdempotencyStore,
        moderator: PatternModerator | OpenAIModerator | None = None,
    ) -> None:
        self.tenants = tenants
        self.budget = budget
        self.llm = llm
        self.limiter = limiter
        self.audit = audit
        self.idempotency = idempotency
        self.moderator = moderator or PatternModerator()

    def handle(
        self,
        raw_key: str,
        messages: list[Message],
        model: str,
        idempotency_key: str | None = None,
    ) -> RequestResult:
        prefix = _key_prefix(raw_key)
        try:
            tenant = self.tenants.authenticate(raw_key)
        except AuthenticationError:
            request_text = "\n".join(message.content for message in messages)
            self._audit(None, prefix, model, "unauthenticated", None, request_text, None)
            raise
        return self.handle_tenant(tenant, prefix, messages, model, idempotency_key)

    def handle_tenant(
        self,
        tenant: Tenant,
        prefix: str,
        messages: list[Message],
        model: str,
        idempotency_key: str | None = None,
    ) -> RequestResult:
        request_text = "\n".join(message.content for message in messages)
        if idempotency_key:
            saved = self.idempotency.get(tenant.id, idempotency_key)
            if saved is not None:
                result = self._result(tenant, saved, replayed=True)
                self._audit(
                    tenant.id,
                    prefix,
                    model,
                    "idempotent_replay",
                    None,
                    request_text,
                    saved.text,
                )
                return result

        plan = self.budget.plan_for(tenant)
        if not self.limiter.allow(tenant.id, plan.requests_per_minute):
            self._audit(tenant.id, prefix, model, "rate_limited", None, request_text, None)
            raise RateLimitExceeded("rate limit exceeded")

        try:
            self.moderator.check_input(messages)
        except PromptRejected:
            self._audit(tenant.id, prefix, model, "injection", None, request_text, None)
            raise

        try:
            reservation_id = self.budget.reserve(tenant)
        except BudgetExceeded:
            self._audit(tenant.id, prefix, model, "budget_exceeded", None, request_text, None)
            raise

        try:
            completion = self.llm.complete(messages, model)
            self.moderator.check_output(completion.text)
            actual_usd = self.llm.cost_usd(completion.model, completion.usage)
        except OutputRejected as exc:
            self.budget.release(reservation_id)
            self._audit(tenant.id, prefix, model, "moderated", None, request_text, str(exc))
            raise
        except Exception:
            self.budget.release(reservation_id)
            self._audit(tenant.id, prefix, model, "error", None, request_text, None)
            raise

        settlement = self.budget.settle(reservation_id, actual_usd, completion.usage)
        if idempotency_key:
            self.idempotency.put(tenant.id, idempotency_key, completion)
        result = RequestResult(
            completion=completion,
            spent_usd=settlement.spent_usd,
            warning=settlement.warning,
            replayed=False,
            cost_usd=actual_usd,
        )
        self._audit(
            tenant.id,
            prefix,
            model,
            "completed",
            actual_usd,
            request_text,
            completion.text,
        )
        return result

    def _result(self, tenant, completion: Completion, replayed: bool) -> RequestResult:
        spent = self.budget.spent_usd(tenant.id)
        plan = self.budget.plan_for(tenant)
        return RequestResult(
            completion=completion,
            spent_usd=spent,
            warning=spent >= plan.soft_budget_usd,
            replayed=replayed,
        )

    def _audit(
        self,
        tenant_id: str | None,
        key_prefix: str,
        model: str,
        outcome: str,
        cost_usd: Decimal | None,
        request_text: str,
        response_text: str | None,
    ) -> None:
        self.audit.record(
            tenant_id=tenant_id,
            key_prefix=key_prefix,
            model=model,
            outcome=outcome,
            cost_usd=cost_usd,
            request_text=request_text,
            response_text=response_text,
        )


def _key_prefix(raw_key: str) -> str:
    prefix, separator, _secret = raw_key.partition(".")
    if separator == "":
        return ""
    return prefix
