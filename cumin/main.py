from src.models.llm import Message
from src.services.openai_inference import OpenAIInference

inference = OpenAIInference()
completion = inference.complete(
    [Message(role="user", content="Summarize https://example.com")],
    model="gpt-4o-mini",
)
print(completion.text)
print(completion.usage)

print()

completion = inference.complete(
    [Message(role="user", content="Summarize https://example.com"), Message(role="user", content="Summarize https://example.com")],
    model="gpt-4o-mini",
)
print(completion.text)
print(completion.usage)


print(inference.cost_usd("gpt-4o-mini", completion.usage))