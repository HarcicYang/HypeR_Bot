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
        if filename.startswith("__"):
            continue
        if os.path.isfile(os.path.join(path, filename)):
            module_name = filename[:-3] if filename.endswith(".py") else filename[:-4]
        else:
            module_name = filename
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
            logger.log(f"导入模块 {module_name} 时发生错误: {traceback.format_exc()}", level=hyperogger.levels.ERROR)

    return imports


def load():
    import_modules(modules_path)


load()
