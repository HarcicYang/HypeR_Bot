import gc
import os
import sys
import importlib
import traceback

from Hyper import Configurator, Logger

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
logger.set_level(config.log_level)
imports = []

if getattr(sys, "frozen", False):
    path = "./_Internal/modules"
else:
    path = "modules"

for i in os.listdir(path):
    if "__init__" in i:
        continue

    try:
        if i.endswith(".py"):
            imports.append(importlib.import_module(f"modules.{i[:-3]}"))
        elif i.endswith(".pyd") or i.endswith(".pyc"):
            imports.append(importlib.import_module(f"modules.{i[:-4]}"))
    except Exception as e:
        logger.log(f"没能成功导入 modules.{i[:-4]}: \n\n{traceback.format_exc()}\n\n")
del i


def reload() -> None:
    gc.collect()
    for j in imports:
        imports[imports.index(j)] = importlib.reload(j)
