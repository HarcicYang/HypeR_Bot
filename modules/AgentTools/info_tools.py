"""信息类工具:查群/查人、时间、读图片(Gemini 视觉)。网页阅读见 webpage_tools.py。"""

from typing import Any, cast

from hyperot import configurator

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool

config = configurator.BotConfig.get("hyper-bot")

# 图片识别使用的 Gemini 模型(config.others.gemini_model 可覆盖,默认最新的 Flash Lite)
GEMINI_MODEL = cast(str, config.others.get("gemini_model") or "gemini-3.5-flash-lite")


class InfoTools(AgentToolBase):
    @tool(group="info")
    async def get_group_info(self, ctx: ToolContext, group_id: int) -> Any:
        """获取群信息（群名、人数、群主等）。

        - group_id: 目标群号
        """
        return (await ctx.actions.get_group_info(group_id)).raw

    @tool(group="info")
    async def get_stranger_info(self, ctx: ToolContext, user_id: int) -> Any:
        """获取用户信息（昵称、性别、年龄等）。

        - user_id: 目标用户 QQ 号
        """
        return (await ctx.actions.get_stranger_info(user_id)).raw

    @tool(group="info")
    async def time(self, ctx: ToolContext) -> str:
        """获取当前日期和时间（YYYY-MM-DD HH:MM:SS）"""
        import datetime

        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @tool(group="info")
    async def scan_qrcode(self, ctx: ToolContext, url: str) -> str:
        """扫描图片中的二维码并返回其内容。

        - url: 图片的下载链接（消息上报中的图片 url）
        - 本地 OpenCV 解码优先（快速、免费）；失败时自动改用视觉模型识别
        """
        try:
            from hyperot.network import httpx_get

            resp = await httpx_get(url)
            content = resp.content
            # 1) 本地 OpenCV 解码
            import cv2
            import numpy as np

            img = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                detector = cv2.QRCodeDetector()
                data, _, _ = detector.detectAndDecode(img)
                if data:
                    return f"二维码内容: {data}"
            # 2) 视觉模型兜底
            vision = await _vision_qr(url)
            if vision:
                return "二维码内容（视觉识别）: " + vision
            return "（未能识别图片中的二维码）"
        except Exception as e:
            return f"（二维码扫描失败: {e}）"

    @tool(group="info")
    async def read_image(self, ctx: ToolContext, url: str, goal: str = "描述图片内容") -> str:
        """阅读图片并返回文字结果。

        - url: 图片的下载链接（消息上报中的图片 url）
        - goal: 阅读图片的目的，如「描述图片内容」「识别图中的文字」「提取图片中的信息」「这张图在玩什么梗」等，
          模型将按你的目的处理图片并返回对应结果
        """
        try:
            key = config.others.get("gemini_key")
            if not key:
                return "（未配置图片识别：config.others.gemini_key 为空）"
            import filetype
            from google import genai
            from google.genai import types as genai_types
            from hyperot.network import httpx_get

            resp = await httpx_get(url)
            content = resp.content
            guessed = filetype.guess(content)
            mime = "application/octet-stream" if guessed is None else guessed.mime
            cli = genai.Client(api_key=key)
            res = cli.models.generate_content(
                model=GEMINI_MODEL,
                contents=cast(
                    Any,
                    [
                        genai_types.Part.from_bytes(data=content, mime_type=mime),
                        genai_types.Part.from_text(
                            text=f"请经可能详细的描述这张图片的全部细节，精确到每一处方位。用简体中文回答，不要寒暄。在全部信息描述完成后，根据我们“{goal}”的目标做详细总结"
                        ),
                    ],
                ),
            )
            return res.text or "（模型未返回内容）"
        except Exception as e:
            return repr(e)


async def _vision_qr(url: str) -> str | None:
    """视觉模型识别二维码内容(本地解码失败的兜底)。失败返回 None。"""
    try:
        key = config.others.get("gemini_key")
        if not key:
            return None
        from typing import Any, cast

        import filetype
        from google import genai
        from google.genai import types as genai_types
        from hyperot.network import httpx_get

        resp = await httpx_get(url)
        content = resp.content
        guessed = filetype.guess(content)
        mime = "application/octet-stream" if guessed is None else guessed.mime
        cli = genai.Client(api_key=key)
        res = cli.models.generate_content(
            model=GEMINI_MODEL,
            contents=cast(
                Any,
                [
                    genai_types.Part.from_bytes(data=content, mime_type=mime),
                    genai_types.Part.from_text(
                        text="识别图片中的二维码并输出其全部内容。如果图片中没有二维码，只输出「（图中没有二维码）」，不要猜测或推断。"
                    ),
                ],
            ),
        )
        return res.text or None
    except Exception:
        return None
