from decimal import Decimal

from src.models.llm import Completion, LLM, Message, Usage


class FakeLLM(LLM):
    def __init__(
        self,
        text: str = "fake completion",
        usage: Usage | None = None,
        usd_per_token: Decimal = Decimal("0.001"),
    ) -> None:
        self._text = text
        self._usage = usage or Usage(input_tokens=10, output_tokens=5)
        self._usd_per_token = usd_per_token
        self.calls: list[tuple[list[Message], str]] = []

    def complete(self, messages: list[Message], model: str) -> Completion:
        self.calls.append((list(messages), model))
        return Completion(text=self._text, model=model, usage=self._usage)

    def cost_usd(self, model: str, usage: Usage) -> Decimal:
        return Decimal(usage.input_tokens + usage.output_tokens) * self._usd_per_token
