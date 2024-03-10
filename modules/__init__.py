import os
import importlib

for i in os.listdir("modules"):
    if i.endswith(".py") and i != "__init__.py":
        importlib.import_module(f"modules.{i[:-3]}")
