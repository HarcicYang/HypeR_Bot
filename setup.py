# setup.py

from setuptools import setup

setup(
    name="hyper-bot",
    version="0.75",
    description="稳定高效、易于开发的QQ Bot框架",
    author="Harcic",
    author_email="harcic@outlook.com",
    url="https://github.com/HarcicYang/HypeR_Bot",
    packages=["Hyper", "Hyper.Adapters", "Hyper.Adapters.OneBotLib"],
    include_package_data=True,
)
