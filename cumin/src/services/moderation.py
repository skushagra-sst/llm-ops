import re
from dataclasses import dataclass

from openai import OpenAI

from src.models.llm import Message

_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior) instructions"
    r"|disregard (your )?(previous|prior) instructions"
    r"|reveal your system prompt"
    r"|you are now (a |an )?(unfiltered|jailbroken)"
    r"|<\|im_start\|>",
    re.IGNORECASE,
)
_OUTPUT = re.compile(
    r"developer mode enabled"
    r"|i will ignore my safety"
    r"|as dan,",
    re.IGNORECASE,
)


class PromptRejected(Exception):
    pass


class OutputRejected(Exception):
    pass


@dataclass(frozen=True)
class Classification:
    label: str
    score: float


class InjectionClassifier:
    """Scores a prompt for jailbreak and instruction-override attempts."""

    def classify(self, text: str) -> Classification:
        if _INJECTION.search(text):
            return Classification(label="injection", score=1.0)
        return Classification(label="allow", score=0.0)


def check_input(messages: list[Message]) -> None:
    text = "\n".join(message.content for message in messages)
    if InjectionClassifier().classify(text).label == "injection":
        raise PromptRejected("prompt rejected")


def check_output(text: str) -> None:
    if _OUTPUT.search(text):
        raise OutputRejected("output rejected")


class PatternModerator:
    def check_input(self, messages: list[Message]) -> None:
        check_input(messages)

    def check_output(self, text: str) -> None:
        check_output(text)


class OpenAIModerator:
    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or OpenAI()
        self._injection = InjectionClassifier()

    def check_input(self, messages: list[Message]) -> None:
        text = "\n".join(message.content for message in messages)
        if self._injection.classify(text).label == "injection":
            raise PromptRejected("prompt rejected")
        self._moderate(text, PromptRejected)

    def check_output(self, text: str) -> None:
        self._moderate(text, OutputRejected)
        check_output(text)

    def _moderate(self, text: str, error: type[Exception]) -> None:
        if not text.strip():
            return
        result = self._client.moderations.create(input=text, model="omni-moderation-latest")
        if result.results and result.results[0].flagged:
            raise error("content flagged by moderation")
