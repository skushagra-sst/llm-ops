import hashlib
import json
import time
from collections.abc import Callable

from src.models.llm import Completion, Message, Usage
from src.services.db import Database

# A claim older than this is reported as an unknown outcome rather than in
# flight. It is never taken over: the owner may have been billed before it
# died, so a retry could charge twice. The client must use a new key.
CLAIM_STALE_SECONDS = 600


class IdempotencyConflict(Exception):
    """The key is held by another request, or was used for a different request."""

    def __init__(self, message: str, retry: bool) -> None:
        super().__init__(message)
        self.retry = retry


def request_fingerprint(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def message_fingerprint(messages: list[Message], model: str) -> str:
    return request_fingerprint(model, *(f"{m.role}\n{m.content}" for m in messages))


class IdempotencyStore:
    def __init__(self, database: Database | None = None, clock: Callable[[], float] = time.time) -> None:
        self._db = database or Database()
        self._clock = clock

    def list_for_tenant(self, tenant_id: str) -> list[dict]:
        rows = self._db.read(
            """
            SELECT idempotency_key, text, model, input_tokens, output_tokens, cached_input_tokens
            FROM idempotency WHERE tenant_id = ? ORDER BY idempotency_key
            """,
            (tenant_id,),
        )
        return [
            {
                "idempotency_key": row["idempotency_key"],
                "text": row["text"],
                "model": row["model"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cached_input_tokens": row["cached_input_tokens"],
            }
            for row in rows
        ]

    def get(self, tenant_id: str, key: str) -> Completion | None:
        rows = self._db.read(
            "SELECT * FROM idempotency WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, key),
        )
        return _completion(rows[0]) if rows else None

    def claim(self, tenant_id: str, key: str, fingerprint: str) -> Completion | None:
        """Return the saved result to replay, or None if the caller now owns the key.

        Raises IdempotencyConflict while another request holds the key, after
        its owner was lost, or when the key was used for a different request.
        """
        with self._db.transaction() as conn:
            saved = conn.execute(
                "SELECT * FROM idempotency WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, key),
            ).fetchone()
            if saved is not None:
                # Results saved before fingerprints existed replay unconditionally.
                if saved["fingerprint"] not in (None, fingerprint):
                    raise IdempotencyConflict("idempotency key was used for a different request", retry=False)
                return _completion(saved)
            pending = conn.execute(
                "SELECT fingerprint, claimed_at FROM idempotency_claims WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, key),
            ).fetchone()
            if pending is not None:
                if pending["fingerprint"] != fingerprint:
                    raise IdempotencyConflict("idempotency key was used for a different request", retry=False)
                if self._clock() - pending["claimed_at"] > CLAIM_STALE_SECONDS:
                    raise IdempotencyConflict(
                        "outcome of the earlier request with this idempotency key is unknown; use a new key",
                        retry=False,
                    )
                raise IdempotencyConflict("a request with this idempotency key is in progress", retry=True)
            conn.execute(
                """
                INSERT INTO idempotency_claims (tenant_id, idempotency_key, fingerprint, claimed_at)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, key, fingerprint, self._clock()),
            )
            return None

    def complete(self, tenant_id: str, key: str, fingerprint: str, completion: Completion) -> None:
        """Save the owner's result and drop its claim in one transaction."""
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO idempotency (
                    tenant_id, idempotency_key, text, model,
                    input_tokens, output_tokens, cached_input_tokens, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    key,
                    completion.text,
                    completion.model,
                    completion.usage.input_tokens,
                    completion.usage.output_tokens,
                    completion.usage.cached_input_tokens,
                    fingerprint,
                ),
            )
            conn.execute(
                "DELETE FROM idempotency_claims WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, key),
            )

    def release(self, tenant_id: str, key: str) -> None:
        """Drop a claim whose request failed before any charge, so the key can be retried."""
        self._db.write(
            "DELETE FROM idempotency_claims WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, key),
        )


def _completion(row) -> Completion:
    return Completion(
        text=row["text"],
        model=row["model"],
        usage=Usage(
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cached_input_tokens=row["cached_input_tokens"],
        ),
    )
