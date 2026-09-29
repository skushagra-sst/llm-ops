from dataclasses import dataclass
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List

@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str

@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0

@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: Usage

class LLM(ABC):
    @abstractmethod
    def complete(self, messages: List[Message], model: str) -> Completion:
        raise NotImplementedError

    @abstractmethod
    def cost_usd(self, model: str, usage: Usage) -> Decimal:
        raise NotImplementedError