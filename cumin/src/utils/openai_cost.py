from dataclasses import dataclass
from decimal import Decimal

from src.models.llm import Usage

# Standard tier, USD per 1M tokens.
# https://developers.openai.com/api/docs/models/gpt-4o-mini
_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class TokenRates:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal


RATES: dict[str, TokenRates] = {
    "gpt-4o-mini": TokenRates(
        input_per_million=Decimal("0.15"),
        cached_input_per_million=Decimal("0.075"),
        output_per_million=Decimal("0.60"),
    ),
    "gpt-4o-mini-2024-07-18": TokenRates(
        input_per_million=Decimal("0.15"),
        cached_input_per_million=Decimal("0.075"),
        output_per_million=Decimal("0.60"),
    ),
}


def cost_usd(model: str, usage: Usage) -> Decimal:
    rates = RATES.get(model)
    if rates is None:
        raise KeyError(f"No OpenAI rate for model {model}")

    uncached_input_tokens = usage.input_tokens - usage.cached_input_tokens
    if uncached_input_tokens < 0:
        raise ValueError("cached_input_tokens exceeds input_tokens")

    return (
        Decimal(uncached_input_tokens) * rates.input_per_million
        + Decimal(usage.cached_input_tokens) * rates.cached_input_per_million
        + Decimal(usage.output_tokens) * rates.output_per_million
    ) / _MILLION
