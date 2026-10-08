from src.models.llm import Message

# Byte-level BPE tokenizers emit at least one UTF-8 byte per text token, so a
# message's byte length bounds its token count. The chat format adds a few
# special tokens per message and for the reply priming; these are padded.
_PER_MESSAGE = 4
_PER_REQUEST = 3


def max_input_tokens(messages: list[Message]) -> int:
    """Upper bound on the input tokens a chat request can be billed for."""
    return _PER_REQUEST + sum(
        _PER_MESSAGE + len(message.role.encode()) + len(message.content.encode())
        for message in messages
    )
