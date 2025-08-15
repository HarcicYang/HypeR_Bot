from __future__ import annotations
from typing import Protocol, runtime_checkable, Any, Dict, Optional, Callable, Awaitable

@runtime_checkable
class Adapter(Protocol):
    """
    Lightweight adapter protocol. Many existing adapter modules expose an Actions class
    (named Actions) that provides a send method. We include both send and send_message
    to maximize compatibility.
    """
    name: str

    async def connect(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Optional: start/connect adapter or perform setup."""
        ...

    async def disconnect(self) -> None:
        """Optional: stop/teardown adapter."""
        ...

    async def send(self, target: str, message: str, **kwargs: Any) -> Any:
        """Some adapters implement `send` (OneBot/Kritor Actions)."""
        ...

    async def send_message(self, target: str, message: str, **kwargs: Any) -> Any:
        """Some code may expect `send_message` instead of `send`. Implement either."""
        ...

    def on_event(self, event_name: str, handler: Callable[..., Awaitable[None]]) -> None:
        """Optional: register event handlers."""
        ...
