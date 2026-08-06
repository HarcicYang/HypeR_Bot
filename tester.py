import os
import sys

from openai import OpenAI

_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
_REASONING_COLOR = "\033[90m" if _USE_COLOR else ""
_RESET_COLOR = "\033[0m" if _USE_COLOR else ""

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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",
)


completion = client.chat.completions.create(
    model="deepseek-ai/deepseek-v4-flash",
    messages=[{"role": "user", "content": "自我介绍一下"}],
    temperature=1,
    top_p=1,
    max_tokens=16384,
    seed=42,
    stream=True,
)

for chunk in completion:
    if not getattr(chunk, "choices", None):
        continue
    if len(chunk.choices) == 0 or getattr(chunk.choices[0], "delta", None) is None:
        continue
    delta = chunk.choices[0].delta
    if getattr(delta, "content", None) is not None:
        print(delta.content, end="")
