# HypeR Bot document

To get started, read the sections below or simply read [`readme.md` in /](../readme.md) for the method with hytil.

_~~What? WHY I AM USING ENGLISH? Good question, could you please fix my `fcitx5` for jetbrains IDEs? :)~~_

## Contents

- [Pypi package installing and developing](#pypi-package-installing-and-developing)
- [Plugin developer guides for full installations](#plugin-developer-guides-for-full-installations)
- [Plugin user guides for full installations](#plugin-user-guides-for-full-installations)

Not finished yet... :(

## Pypi package installing and developing

### Installation

HypeR Bot always updates at a unstable rate _~~(DOT BECAUSE I AM LAZY, definitely! )~~_. For previous releases, changelogs are unavailable. I'am going to writes Changelogs for the later releases (after 0.81.0).

To install HypeR Bot for your env, simply do:

```shell
pip3 install hyper_bot
```

Newer versions are suggested for I am not going to save the elder documents :)

### Start your development with `Client` 

There's a simple example below, I'm going to explain the codes for you.

```python
from hyperot import Client, configurator
from cfgr.manager import Serializers

try:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
except FileNotFoundError:
    configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
    print("No config files found, new file has been created! Please edit it and try again.")
    exit(-1)
    
from hyperot.adapters import builtins as adp

adp.load_onebot()
from hyperot import events

cli = Client()

async def test(event, actions):
    print(event)

cli.subscribe(test, events.GroupMessageEvent)
cli.run()

```
You may ask: _What's fxxking `cfgr`?_

`cfgr`, which has been writen by me, is a simple config file manager for python. I've not uploaded it to github, but you can install it from pypi using pip:

```shell
pip install ucfgr
```

Codes are available on pypi.

Then, maybe you are confused on the codes below:

```python
...

from hyperot.adapters import builtins as adp

adp.load_onebot()
from hyperot import events

...
```

We put this import below the configurations for these modules NEED the configuration badly and they are unable to work with out the configuration.

> From 0.81.0, adapters are not selected by default, you need to set the adapter by your self. More adapters will be available in the _*near future_

Now, we are going to look at these codes:

```python
...

cli = Client()

async def test(event, actions):
    print(event)

cli.subscribe(test, events.GroupMessageEvent)
cli.run()
```
create a client, bind a handler and run. And...

```shell
   2025-08-24 14:13:45.78 |  Warning  | 连接建立失败，3秒后重试(0/5)
   2025-08-24 14:13:48.78 |  Warning  | 连接建立失败，3秒后重试(1/5)
   2025-08-24 14:13:51.78 |  Warning  | 连接建立失败，3秒后重试(2/5)
   2025-08-24 14:13:54.78 |  Warning  | 连接建立失败，3秒后重试(3/5)
   2025-08-24 14:13:57.78 |  Warning  | 连接建立失败，3秒后重试(4/5)
   2025-08-24 14:14:00.78 |  Critical | 重试次数达到最大值(5)，退出
```

Why it failed?

Okay, in the codes above _(and above)_, we've set HypeR Bot to use [OneBot](https://github.com/botuniverse/onebot-11) adapter. This simply requires a OneBot implementation to be running and being able to be connected by HypeR Bot.

I recommend you use one of them:

- [Lagrange.OneBot](https://github.com/LagrangeDev/Lagrange.Core)
- [NapCat](https://github.com/NapNeko/NapCatQQ)
- [LLOneBot](https://github.com/LLOneBot/LLOneBot)

I'm going to make hytil able to setup [Lagrange.OneBot](https://github.com/LagrangeDev/Lagrange.Core) for you. _~~(Coming "SOON")~~_

Good, you've finished a simple script to log all the message events on your console. Read the documents below for further information.

- Actions & API response
- Events

Not finished yet... :(

## Full installations

```shell
$ pip install hyper_bot
$ python -m hytil -i -p ./path/for/your/bot
```

OneBot implementation auto-config isn't available at present.

### Plugin developer guides for full installations

open `/modules`, create a `.py` file, and code:

```python
import hyperot
from hyperot import events, segments, common
import ModuleClass
from hyperot.events import *


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    async def handle(self):
        ...

```

Read the documents below for further information.

- Actions & API response
- Events

Not finished yet... :(

### Plugin user guides for full installations

Old documents are enough at present. [Click me](https://harcicyang.github.io/hyper-bot/usage/qq_usage/)