"""Agent 工具包。

仿照 modules/__init__.py 的加载方式:扫描本目录所有 .py 文件(跳过 __ 开头与 .dis),
逐个导入;工具类定义于工具文件内,导入即注册进 ToolRegistry。
"""

import importlib
import os
import traceback

from hyperot import configurator, hyperogger

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)

tools_path = os.path.dirname(__file__)


def import_tools(path: str) -> None:
    for filename in os.listdir(path):
        if filename.startswith("__") or filename.endswith(".dis"):
            continue
        if not filename.endswith(".py"):
            continue
        module_name = filename[:-3]
        try:
            importlib.import_module("modules.AgentTools." + module_name)
        except Exception:
            logger.log(f"导入工具 {module_name} 时发生错误: {traceback.format_exc()}", level=hyperogger.levels.ERROR)


import_tools(tools_path)
