from dataclasses import dataclass
from typing import Union, Any

from openai import OpenAI


@dataclass
class OpenAIContext:
    content: list[Union[dict, Any]]
    model: str
    client: OpenAI

    def gen(self, msg: str) -> str:
        self.content.append({"role": "user", "content": msg})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.content,
            stream=False,
        )
        self.content.append(response.choices[0].message)
        return response.choices[0].message.content