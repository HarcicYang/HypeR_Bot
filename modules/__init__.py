import os
import sys
import importlib.util
import traceback

from Hyper import Configurator, Logger

config = Configurator.BotConfig.get("hyper-bot")
logger = Logger.Logger()
logger.set_level(config.log_level)
modules_path = os.path.dirname(__file__)


def import_modules(path):
    global imports
    imports = []
    for filename in os.listdir(path):
        if filename.startswith("__"):
            continue

        module_name = filename[:-3] if filename.endswith(".py") else filename[:-4]
        module_path = os.path.join(path, filename)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None:
            # logger.log(f"无法导入模块: {module_name}")
            continue

        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            imports.append(module)
        except Exception as e:
            logger.log(f"导入模块 {module_name} 时发生错误: {traceback.format_exc()}", level=Logger.levels.ERROR)

    return imports


def load():
    import_modules(modules_path)


load()
