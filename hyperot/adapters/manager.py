from __future__ import annotations
from typing import Dict, Optional, Any, Type
import importlib
import asyncio
import inspect
from .base import Adapter

# Map logical adapter names to module:Class specs. Use the Actions classes exported by existing adapters.
DEFAULT_REGISTRY: Dict[str, str] = {
    "onebot": "hyperot.Adapters.OneBot:Actions",
    "kritor": "hyperot.Adapters.Kritor:Actions",
}

class AdapterManager:
    def __init__(self, registry: Optional[Dict[str, str]] = None):
        self._registry = dict(DEFAULT_REGISTRY)
        if registry:
            self._registry.update(registry)
        self._instances: Dict[str, Any] = {}

    def _load_class(self, spec: str) -> Type[Any]:
        module_path, _, class_name = spec.partition(":")
        if not module_path or not class_name:
            raise ValueError("Invalid adapter spec (expected 'module.path:ClassName')")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls

    def create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Instantiate (or return cached) adapter instance for `name`.

        We avoid strict runtime Protocol checks because many adapter Actions classes are
        lightweight and do not provide e.g. a `name` attribute. We still prefer the
        classes listed in the registry.
        """
        if name in self._instances:
            return self._instances[name]

        spec = self._registry.get(name)
        if not spec:
            raise ValueError(f"No adapter registered under name {name!r}")

        cls = self._load_class(spec)
        inst = cls(*args, **kwargs)

        # best-effort — do not enforce isinstance checks to be flexible with existing modules
        self._instances[name] = inst
        return inst

    def get(self, name: str) -> Optional[Any]:
        return self._instances.get(name)

    def register(self, name: str, spec: str) -> None:
        """Register a new adapter mapping. Spec should be 'module.path:ClassName'."""
        self._registry[name] = spec

    async def _maybe_disconnect(self, inst: Any) -> None:
        if not inst:
            return
        fn = getattr(inst, "disconnect", None)
        if fn and callable(fn):
            try:
                res = fn()
                if inspect.isawaitable(res):
                    await res
            except Exception:
                # swallow exceptions on teardown
                pass

    async def _maybe_connect(self, inst: Any, *args: Any, **kwargs: Any) -> None:
        fn = getattr(inst, "connect", None)
        if fn and callable(fn):
            try:
                res = fn(*args, **kwargs)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                # bubble? for now, re-raise so callers are aware of connect failures
                raise

    async def switch(self, new_name: str, *args: Any, **kwargs: Any) -> Any:
        """Disconnect existing adapters (best-effort), create or reuse the requested adapter,
        and call its `connect` if available.
        """
        # Disconnect all currently cached instances (best-effort).
        tasks = [self._maybe_disconnect(i) for i in list(self._instances.values())]
        if tasks:
            await asyncio.gather(*tasks)

        adapter = self.create(new_name, *args, **kwargs)
        await self._maybe_connect(adapter)
        return adapter
