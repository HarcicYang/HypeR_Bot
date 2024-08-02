import os
# import importlib

for i in os.listdir("modules"):
    if "__init__" in i:
        continue

    if i.endswith(".py"):
        # importlib.import_module(f"modules.{i[:-3]}")
        __import__(f"modules.{i[:-3]}")
    elif i.endswith(".pyd") or i.endswith(".pyc"):
        __import__(f"modules.{i[:-4]}")

del i
