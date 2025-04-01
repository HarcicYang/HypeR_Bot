import os
import sys
import importlib.util
import traceback

from hyperot import configurator, hyperogger

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)
modules_path = os.path.dirname(__file__)


def import_modules(path):
    imports = []
    for filename in os.listdir(path):
        if filename.startswith("__") or filename.endswith(".dis"):
            continue
        if os.path.isfile(os.path.join(path, filename)):
            module_name = filename[:-3] if filename.endswith(".py") else filename[:-4]
        else:
            module_name = filename

        try:
            module = importlib.import_module("modules." + module_name)
            sys.modules[module_name] = module
            imports.append(module)
        except Exception as e:
            logger.log(f"导入模块 {module_name} 时发生错误: {traceback.format_exc()}", level=hyperogger.levels.ERROR)

    return imports


def load():
    import_modules(modules_path)


load()
