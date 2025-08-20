<div align="center">
<h1><img src="logo.ico" alt="icon" width="32px"> HypeR Bot</h1>
</div>
<p align="center">适配OneBot v11协议、功能模块化、易于扩展、高效的QQ机器人及框架</p>
<div align="center">
<img src="https://img.shields.io/badge/OneBot-11-black?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAHAAAABwCAMAAADxPgR5AAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAAxQTFRF////29vbr6+vAAAAk1hCcwAAAAR0Uk5T////AEAqqfQAAAKcSURBVHja7NrbctswDATQXfD//zlpO7FlmwAWIOnOtNaTM5JwDMa8E+PNFz7g3waJ24fviyDPgfhz8fHP39cBcBL9KoJbQUxjA2iYqHL3FAnvzhL4GtVNUcoSZe6eSHizBcK5LL7dBr2AUZlev1ARRHCljzRALIEog6H3U6bCIyqIZdAT0eBuJYaGiJaHSjmkYIZd+qSGWAQnIaz2OArVnX6vrItQvbhZJtVGB5qX9wKqCMkb9W7aexfCO/rwQRBzsDIsYx4AOz0nhAtWu7bqkEQBO0Pr+Ftjt5fFCUEbm0Sbgdu8WSgJ5NgH2iu46R/o1UcBXJsFusWF/QUaz3RwJMEgngfaGGdSxJkE/Yg4lOBryBiMwvAhZrVMUUvwqU7F05b5WLaUIN4M4hRocQQRnEedgsn7TZB3UCpRrIJwQfqvGwsg18EnI2uSVNC8t+0QmMXogvbPg/xk+Mnw/6kW/rraUlvqgmFreAA09xW5t0AFlHrQZ3CsgvZm0FbHNKyBmheBKIF2cCA8A600aHPmFtRB1XvMsJAiza7LpPog0UJwccKdzw8rdf8MyN2ePYF896LC5hTzdZqxb6VNXInaupARLDNBWgI8spq4T0Qb5H4vWfPmHo8OyB1ito+AysNNz0oglj1U955sjUN9d41LnrX2D/u7eRwxyOaOpfyevCWbTgDEoilsOnu7zsKhjRCsnD/QzhdkYLBLXjiK4f3UWmcx2M7PO21CKVTH84638NTplt6JIQH0ZwCNuiWAfvuLhdrcOYPVO9eW3A67l7hZtgaY9GZo9AFc6cryjoeFBIWeU+npnk/nLE0OxCHL1eQsc1IciehjpJv5mqCsjeopaH6r15/MrxNnVhu7tmcslay2gO2Z1QfcfX0JMACG41/u0RrI9QAAAABJRU5ErkJggg==" alt="Badge">
<img src="https://img.shields.io/static/v1?label=LICENSE&message=GPL-3.0&color=lightrey" alt="Badge">
</div>

## 概览

HypeR Bot是一个适配OneBot协议的机器人框架，旨在提供一个简洁、高效、可扩展的机器人运行结构。

~~[点我跳转详细文档](https://harcicyang.github.io/hyper-bot/)~~ 文档已经严重过时，以后重写吧（）

## 使用 `hytil` 快速开始

`hytil` 于 HypeR Bot 0.81.0 版本加入，是一个支持您快速配置完整 HypeR Bot 的实用工具。

### 安装 HypeR Bot
```shell
pip install hyper_bot
```

### 使用 `hytil`

```shell
$ python -m hytil
usage: hytil.py [-h] [-v] [-i] [-p PATH]

HypeR Bot Utils 版本 0.0.1

options:
  -h, --help            show this help message and exit
  -v, --version         显示版本信息
  -i, --install         安装完整的HypeR Bot到本地
  -p PATH, --path PATH  指定操作路径

```

在开始前，确认一个空文件夹，该文件夹将用于安装 HypeR Bot。
```shell
$ mkdir bot
$ ls
bot ...
```

现在，使用如下命令将完整的 HypeR Bot 下载到本地：

```shell
python -m hytil -i -p ./bot
```

下载完成后，您将会收到运行 `main.py` 的提示，此时，请您进入安装目录，在该目录下执行`python main.py`，配置文件 `config.json`将随后创建，请根据下方指引编辑配置文件。

## 配置文件

`config.json`:

```json
{
  "protocol": "OneBot",
  "owner": [],
  "black_list": [],
  "silents": [],
  "connection": {
    "mode": "FWS",
    "ob_auto_startup": false,
    "ob_exec": "./Lagrange.OneBot/Lagrange.OneBot",
    "ob_startup_path": "./Lagrange.OneBot/",
    "host": "127.0.0.1",
    "port": 5004
  },
  "log_level": "INFO",
  "log_use_nf": true,
  "uin": 0,
  "max_workers": 25,
  "others": { ... }
}

```

其中：

- `owner`：机器人主人的QQ号，填写在这个列表中的QQ号所发送的消息会被标记`is_owner = True`；
- `black_list`：黑名单，填写在这个列表中的QQ号所发送的的消息会被标记 `blocked = True`；
- `connection`：连接信息，包括主机地址、端口以及自动启动OneBot实现的配置；
- `log_level`：日志等级，可选值为`DEBUG`、`TRACE`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`；
- `others`：其他配置项；
- `log_use_nf`：是否为日志输出启用NerdFont;
- `protocol`：适配的协议，目前仅支持OneBot.

若您正在使用完整的 HypeR Bot 安装，您需要如下设置 `others` 部分以正常使用 AI 聊天功能：

```json
"others": {
    "enable": "gemini",
    "gemini_key": "",
    "ds_ck": "",
    "ds_auth": "",
    "white": []
  }
```
_~~直接注册个 [AI Studio](https://aistudio.google.com) 用gemini得了，ds我自己逆向的，懒得写文档了（~~_

## 环境

> 本人开发和测试均在Python 3.11.7环境进行，其他版本未经测试，理论上支持 Python 3.9 及以上版本。

所需的第三方库陈列在[`requirements.txt`](/requirements.txt)中，使用`pip install -r requirements.txt`即可。

[`requirements_optional.txt`](/requirements_optional.txt)中包含部分模块所需的其他依赖，可视情况安装。