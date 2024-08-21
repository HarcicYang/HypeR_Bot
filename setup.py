# setup.py

from setuptools import setup

import Hyper

setup(
    name="hyper-bot",
    version=Hyper.HYPER_BOT_VERSION,
    description="稳定高效、易于开发的QQ Bot框架",
    author="Harcic",
    author_email="harcic@outlook.com",
    url="https://github.com/HarcicYang/HypeR_Bot",
    packages=["Hyper", "Hyper.Adapters", "Hyper.Adapters.OneBotLib", "Hyper.Utils"],
    include_package_data=True,
)
