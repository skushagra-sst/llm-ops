from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.models.llm import Usage


@dataclass
class LedgerEntry:
    id: str
    tenant_id: str
    plan_id: str
    month: str
    reserved_usd: Decimal
    reserved_tokens: int
    status: Literal["open", "settled", "released"]
    actual_usd: Decimal | None = None
    usage: Usage | None = None
