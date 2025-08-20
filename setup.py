from setuptools import setup, find_packages

import hyperot

setup(
    name="hyper-bot",
    provides=["hyperot"],
    version=hyperot.HYPER_BOT_VERSION,
    description="稳定高效、易于开发的QQ Bot框架",
    author="Harcic",
    author_email="harcic@outlook.com",
    url="https://github.com/HarcicYang/HypeR_Bot",
    packages=[
        "hyperot",
        "hyperot.adapters",
        "hyperot.LecAdapters",
        "hyperot.LecAdapters.OneBotLib",
        "hyperot.LecAdapters.KritorLib",
        "hyperot.LecAdapters.KritorLib.protos",
        "hyperot.utils",
    ] + [
        f"hyperot.LecAdapters.KritorLib.protos.{i}"
        for i in find_packages("hyperot/LecAdapters/KritorLib/protos")
    ],
    py_modules=["hytil"],
    install_requires=["ucfgr"],
    include_package_data=True
)
