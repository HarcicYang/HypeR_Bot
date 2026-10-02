import importlib
import os
import sys
import traceback
from types import ModuleType

from hyperot import configurator, hyperogger

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)
modules_path = os.path.dirname(__file__)
loaded_names: list[str] = []
import_errors: list[tuple[str, str]] = []


def import_modules(path: str) -> list[ModuleType]:
    global import_errors, loaded_names
    imports: list[ModuleType] = []
    loaded_names = []
    import_errors = []
    for filename in sorted(os.listdir(path)):
        if filename.startswith("__") or filename.endswith(".dis"):
            continue
        if os.path.isfile(os.path.join(path, filename)):
            module_name = filename[:-3] if filename.endswith(".py") else filename[:-4]
        else:
            module_name = filename

        try:
            module = importlib.import_module("modules." + module_name)
            sys.modules[module_name] = module
            loaded_names.append(module_name)
            imports.append(module)
        except Exception:
            detail = traceback.format_exc()
            import_errors.append((module_name, detail))
            logger.log(f"导入模块 {module_name} 时发生错误: {detail}", level=hyperogger.levels.ERROR)

    return imports


def load() -> list[ModuleType]:
    return import_modules(modules_path)


def unload() -> None:
    """卸载全部普通模块；先调用模块级 unload 钩子，再清理 sys.modules 别名。"""
    for name, module in list(sys.modules.items()):
        if not name.startswith(__name__ + "."):
            continue
        if "." in name[len(__name__) + 1 :]:
            continue
        hook = getattr(module, "unload", None)
        if not callable(hook):
            continue
        try:
            hook()
        except Exception:
            logger.log(f"卸载模块 {name} 时发生错误: {traceback.format_exc()}", level=hyperogger.levels.ERROR)

    for key, module in list(sys.modules.items()):
        if key == __name__ or key.startswith(__name__ + "."):
            del sys.modules[key]
            continue
        module_name = getattr(module, "__name__", "")
        if isinstance(module_name, str) and module_name.startswith(__name__ + "."):
            del sys.modules[key]

    loaded_names.clear()
    import_errors.clear()


load()
