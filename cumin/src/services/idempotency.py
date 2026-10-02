from src.models.llm import Completion, Usage
from src.services.db import Database


class IdempotencyStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

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
        if not rows:
            return None
        row = rows[0]
        return Completion(
            text=row["text"],
            model=row["model"],
            usage=Usage(
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                cached_input_tokens=row["cached_input_tokens"],
            ),
        )

    def put(self, tenant_id: str, key: str, completion: Completion) -> None:
        self._db.write(
            """
            INSERT INTO idempotency (
                tenant_id, idempotency_key, text, model,
                input_tokens, output_tokens, cached_input_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, idempotency_key) DO NOTHING
            """,
            (
                tenant_id,
                key,
                completion.text,
                completion.model,
                completion.usage.input_tokens,
                completion.usage.output_tokens,
                completion.usage.cached_input_tokens,
            ),
        )
