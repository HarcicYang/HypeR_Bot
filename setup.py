# setup.py

from setuptools import setup, find_packages

import Hyper

setup(
    name="hyper-bot",
    version=Hyper.HYPER_BOT_VERSION,
    description="稳定高效、易于开发的QQ Bot框架",
    author="Harcic",
    author_email="harcic@outlook.com",
    url="https://github.com/HarcicYang/HypeR_Bot",
    packages=[
        "Hyper",
        "Hyper.Adapters",
        "Hyper.Adapters.OneBotLib",
        "Hyper.Adapters.KritorLib",
        "Hyper.Adapters.KritorLib.protos",
        "Hyper.Utils"
    ] + [
        f"Hyper.Adapters.KritorLib.protos.{i}"
        for i in find_packages("./Hyper/Adapters/KritorLib/protos")
    ],
    include_package_data=True
)
