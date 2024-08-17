import gc
import os
import sys
import importlib

imports = []

if getattr(sys, "frozen", False):
    path = "./_Internal/modules"
else:
    path = "modules"

for i in os.listdir(path):
    if "__init__" in i:
        continue

    if i.endswith(".py"):
        imports.append(importlib.import_module(f"modules.{i[:-3]}"))
    elif i.endswith(".pyd") or i.endswith(".pyc"):
        imports.append(importlib.import_module(f"modules.{i[:-4]}"))

del i


def reload() -> None:
    gc.collect()
    for j in imports:
        imports[imports.index(j)] = importlib.reload(j)
