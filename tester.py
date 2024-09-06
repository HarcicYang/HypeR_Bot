from typing import Any


class ChatActions:
    def __init__(self, actions: list["ChatActions"] = None):
        self.actions = actions or list()

    def clear(self) -> "ChatActions":
        class ClearRunner(type(self)):
            async def run(self) -> None:
                print(1)

        self.actions.append(ClearRunner())
        return self

    async def run(self, *args, **kwargs) -> Any:
        ...


c = ChatActions().clear().clear()
print(c.actions)
