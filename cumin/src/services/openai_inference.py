from decimal import Decimal

from openai import OpenAI

from src.models.llm import Completion, LLM, Message, Usage
from src.utils.openai_cost import cost_usd as openai_cost_usd


class OpenAIInference(LLM):
    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or OpenAI()

    def complete(self, messages: list[Message], model: str) -> Completion:
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": message.role, "content": message.content} for message in messages],
        )
        if not response.choices:
            raise RuntimeError("OpenAI returned no choices")
        if response.usage is None:
            raise RuntimeError("OpenAI returned no usage")

        details = response.usage.prompt_tokens_details
        cached_input_tokens = 0
        if details is not None and details.cached_tokens is not None:
            cached_input_tokens = details.cached_tokens

        content = response.choices[0].message.content or ""
        return Completion(
            text=content,
            model=response.model,
            usage=Usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                cached_input_tokens=cached_input_tokens,
            ),
        )

    def cost_usd(self, model: str, usage: Usage) -> Decimal:
        return openai_cost_usd(model, usage)
