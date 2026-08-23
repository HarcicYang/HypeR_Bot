"""Actions wrapper used when Agent invokes another bot module."""

import os
import time
from typing import Any

from hyperot.listener import Actions


class CaptureActions:
    """Capture module send operations while forwarding all other actions."""

    CAPTURE_DIR = "./temps/agent_capture"

    def __init__(self, real: Actions) -> None:
        self._real = real
        self.captured: list[dict[str, Any]] = []

    @staticmethod
    def _preserve_image_files(segs: list[Any]) -> list[Any]:
        out: list[Any] = []
        for seg in segs:
            if isinstance(seg, dict) and seg.get("type") == "image":
                data = seg.get("data") or {}
                file = data.get("file", "")
                if file.startswith("file://"):
                    src = file[len("file://") :]
                    if os.path.isfile(src):
                        try:
                            os.makedirs(CaptureActions.CAPTURE_DIR, exist_ok=True)
                            dst = os.path.join(
                                CaptureActions.CAPTURE_DIR,
                                f"{int(time.time() * 1000)}_{os.path.basename(src)}",
                            )
                            import shutil

                            shutil.copy2(src, dst)
                            file = "file://" + os.path.abspath(dst).replace("\\", "/")
                        except OSError:
                            pass
                    seg = dict(seg)
                    seg["data"] = dict(data)
                    seg["data"]["file"] = file
            out.append(seg)
        return out

    async def send_msg(
        self,
        group_id: int | None = None,
        user_id: int | None = None,
        message: Any = None,
        **kw: Any,
    ) -> dict[str, Any]:
        try:
            segs: list[Any] = message.get_sync() if message is not None else []
        except Exception:
            segs = [{"type": "text", "data": {"text": str(message)}}]
        segs = self._preserve_image_files(segs)
        self.captured.append({"group_id": group_id, "user_id": user_id, "message": segs})
        return {"status": "ok", "retcode": 0, "data": {"message_id": 0}}

    async def send_group_msg(self, group_id: int | None, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(group_id=group_id, message=message, **kw)

    async def send_private_msg(self, user_id: int | None, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(user_id=user_id, message=message, **kw)

    async def send_forward_msg(self, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(message=message, **kw)

    async def send_group_forward_msg(self, group_id: int | None, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(group_id=group_id, message=message, **kw)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)
