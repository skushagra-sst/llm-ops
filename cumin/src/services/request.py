from dataclasses import dataclass, replace
from contextvars import ContextVar
from functools import wraps
import time
from decimal import Decimal

from src.models.llm import Completion, LLM, Message, Usage
from src.models.tenant import Tenant
from src.services.audit import AuditLog
from src.services.budget import BudgetExceeded, BudgetGate
from src.services.idempotency import IdempotencyConflict, IdempotencyStore, message_fingerprint
from src.services.moderation import OpenAIModerator, OutputRejected, PatternModerator, PromptRejected
from src.services.rate_limit import RateLimitExceeded, RateLimiter
from src.services.tenant import AuthenticationError, TenantManager
from src.utils.tokens import max_input_tokens

MAX_OUTPUT_TOKENS = 512


class UnsupportedModel(Exception):
    pass


@dataclass(frozen=True)
class RequestBound:
    input_tokens: int
    output_tokens: int
    usd: Decimal

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


_REQUEST_STARTED: ContextVar[float | None] = ContextVar("cumin_request_started", default=None)


def _timed_request(function):
    """One handler-only timer across handle -> handle_tenant; thread/task local."""
    @wraps(function)
    def timed(*args, **kwargs):
        if _REQUEST_STARTED.get() is not None:
            return function(*args, **kwargs)
        started = time.perf_counter()
        token = _REQUEST_STARTED.set(started)
        try:
            result = function(*args, **kwargs)
            return replace(result, latency_ms=(time.perf_counter() - started) * 1000)
        finally:
            _REQUEST_STARTED.reset(token)
    return timed


@dataclass(frozen=True)
class RequestResult:
    completion: Completion
    spent_usd: Decimal
    warning: bool
    replayed: bool
    cost_usd: Decimal = Decimal(0)
    latency_ms: float | None = None


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
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> None:
        self.tenants = tenants
        self.budget = budget
        self.llm = llm
        self.limiter = limiter
        self.audit = audit
        self.idempotency = idempotency
        self.moderator = moderator or PatternModerator()
        self.max_output_tokens = max_output_tokens

    def bound(self, messages: list[Message], model: str) -> RequestBound:
        """Worst-case tokens and cost: every input token uncached, output at its cap."""
        input_tokens = max_input_tokens(messages)
        try:
            usd = self.llm.cost_usd(model, Usage(input_tokens, self.max_output_tokens))
        except KeyError as exc:
            raise UnsupportedModel(f"no price for model {model}") from exc
        return RequestBound(input_tokens, self.max_output_tokens, usd)

    @_timed_request
    def handle(
        self,
        raw_key: str,
        messages: list[Message],
        model: str,
        idempotency_key: str | None = None,
        fingerprint: str | None = None,
    ) -> RequestResult:
        prefix = _key_prefix(raw_key)
        try:
            tenant = self.tenants.authenticate(raw_key)
        except AuthenticationError:
            request_text = "\n".join(message.content for message in messages)
            self._audit(None, prefix, model, "unauthenticated", None, request_text, None)
            raise
        return self.handle_tenant(tenant, prefix, messages, model, idempotency_key, fingerprint)

    @_timed_request
    def handle_tenant(
        self,
        tenant: Tenant,
        prefix: str,
        messages: list[Message],
        model: str,
        idempotency_key: str | None = None,
        fingerprint: str | None = None,
    ) -> RequestResult:
        """Serve one request. With a key, only the request that claims it calls the model.

        `fingerprint` identifies the request for key reuse checks; it defaults to
        the model and messages.
        """
        request_text = "\n".join(message.content for message in messages)
        if not idempotency_key:
            result, _ = self._serve(tenant, prefix, messages, model, request_text)
            return result

        fingerprint = fingerprint or message_fingerprint(messages, model)
        try:
            saved = self.idempotency.claim(tenant.id, idempotency_key, fingerprint)
        except IdempotencyConflict:
            self._audit(tenant.id, prefix, model, "idempotency_conflict", None, request_text, None)
            raise
        if saved is not None:
            result = self._result(tenant, saved, replayed=True)
            self._audit(tenant.id, prefix, model, "idempotent_replay", None, request_text, saved.text)
            return result

        charged = [False]
        try:
            result, completion = self._serve(tenant, prefix, messages, model, request_text, charged)
        except BaseException:
            # Nothing was billed to the tenant, so the key can be retried. After a
            # charge the claim stays: a retry must not call the model again.
            if not charged[0]:
                self.idempotency.release(tenant.id, idempotency_key)
            raise
        self.idempotency.complete(tenant.id, idempotency_key, fingerprint, completion)
        return result

    def _serve(
        self,
        tenant: Tenant,
        prefix: str,
        messages: list[Message],
        model: str,
        request_text: str,
        charged: list[bool] | None = None,
    ) -> tuple[RequestResult, Completion]:
        plan = self.budget.plan_for(tenant)
        if not self.limiter.allow(tenant.id, plan.requests_per_minute):
            self._audit(tenant.id, prefix, model, "rate_limited", None, request_text, None)
            raise RateLimitExceeded("rate limit exceeded")

        try:
            bound = self.bound(messages, model)
        except UnsupportedModel:
            self._audit(tenant.id, prefix, model, "unsupported_model", None, request_text, None)
            raise

        try:
            self.moderator.check_input(messages)
        except PromptRejected:
            self._audit(tenant.id, prefix, model, "injection", None, request_text, None)
            raise

        try:
            reservation_id = self.budget.reserve(tenant, usd=bound.usd, tokens=bound.tokens)
        except BudgetExceeded:
            self._audit(tenant.id, prefix, model, "budget_exceeded", None, request_text, None)
            raise

        try:
            completion = self.llm.complete(messages, model, max_output_tokens=bound.output_tokens)
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
        if charged is not None:
            charged[0] = True
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
        return result, completion

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
            latency_ms=None if _REQUEST_STARTED.get() is None else (time.perf_counter() - _REQUEST_STARTED.get()) * 1000,
        )


def _key_prefix(raw_key: str) -> str:
    prefix, separator, _secret = raw_key.partition(".")
    if separator == "":
        return ""
    return prefix
