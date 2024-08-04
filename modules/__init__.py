import os
import sys

if getattr(sys, "frozen", False):
    path = "./_Internal/modules"
else:
    path = "modules"

for i in os.listdir(path):
    if "__init__" in i:
        continue

    if i.endswith(".py"):
        # importlib.import_module(f"modules.{i[:-3]}")
        __import__(f"modules.{i[:-3]}")
    elif i.endswith(".pyd") or i.endswith(".pyc"):
        __import__(f"modules.{i[:-4]}")

del i
