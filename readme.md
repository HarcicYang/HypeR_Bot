![banner](./ban.png)

<div align="center">
<h1>HypeR Bot</h1>
</div>
<p align="center">适配OneBot v11协议、功能模块化、易于扩展、高效的QQ机器人及框架</p>
<div align="center">
<img src="https://img.shields.io/badge/OneBot-11-black?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAHAAAABwCAMAAADxPgR5AAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAAxQTFRF////29vbr6+vAAAAk1hCcwAAAAR0Uk5T////AEAqqfQAAAKcSURBVHja7NrbctswDATQXfD//zlpO7FlmwAWIOnOtNaTM5JwDMa8E+PNFz7g3waJ24fviyDPgfhz8fHP39cBcBL9KoJbQUxjA2iYqHL3FAnvzhL4GtVNUcoSZe6eSHizBcK5LL7dBr2AUZlev1ARRHCljzRALIEog6H3U6bCIyqIZdAT0eBuJYaGiJaHSjmkYIZd+qSGWAQnIaz2OArVnX6vrItQvbhZJtVGB5qX9wKqCMkb9W7aexfCO/rwQRBzsDIsYx4AOz0nhAtWu7bqkEQBO0Pr+Ftjt5fFCUEbm0Sbgdu8WSgJ5NgH2iu46R/o1UcBXJsFusWF/QUaz3RwJMEgngfaGGdSxJkE/Yg4lOBryBiMwvAhZrVMUUvwqU7F05b5WLaUIN4M4hRocQQRnEedgsn7TZB3UCpRrIJwQfqvGwsg18EnI2uSVNC8t+0QmMXogvbPg/xk+Mnw/6kW/rraUlvqgmFreAA09xW5t0AFlHrQZ3CsgvZm0FbHNKyBmheBKIF2cCA8A600aHPmFtRB1XvMsJAiza7LpPog0UJwccKdzw8rdf8MyN2ePYF896LC5hTzdZqxb6VNXInaupARLDNBWgI8spq4T0Qb5H4vWfPmHo8OyB1ito+AysNNz0oglj1U955sjUN9d41LnrX2D/u7eRwxyOaOpfyevCWbTgDEoilsOnu7zsKhjRCsnD/QzhdkYLBLXjiK4f3UWmcx2M7PO21CKVTH84638NTplt6JIQH0ZwCNuiWAfvuLhdrcOYPVO9eW3A67l7hZtgaY9GZo9AFc6cryjoeFBIWeU+npnk/nLE0OxCHL1eQsc1IciehjpJv5mqCsjeopaH6r15/MrxNnVhu7tmcslay2gO2Z1QfcfX0JMACG41/u0RrI9QAAAABJRU5ErkJggg==" alt="Badge">
<img src="https://img.shields.io/static/v1?label=LICENSE&message=GPL-3.0&color=lightrey" alt="Badge">
</div>

---

## 项目状态

- 框架（即 [hyper-bot](https://pypi.org/project/hyper-bot/) / `hyperot` 核心）已在 [HyperBotCore](https://github.com/HarcicYang/HyperBotCore) 仓库继续独立维护，本仓库不再包含框架源码，仅作为 bot 本体使用。
- 本仓库已迁移至 **uv** 管理依赖（Python 3.12。

---

## 概览

HypeR Bot是一个适配 OneBot 和 Milky 协议并支持拓展自定义协议的机器人框架，旨在提供一个简洁、高效、可扩展的机器人运行结构。

## 快速开始

### 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)（依赖管理，`uv.lock` 锁定全部版本）

### 安装与运行

```shell
uv sync          # 安装运行时与开发依赖到 .venv
uv run python main.py
```

首次运行会自动生成 `config.json`，编辑后重启即可。

### 开发工具

```shell
uv run ruff check       # lint
uv run ruff format      # 格式化
uv run pyrefly check    # 类型检查（strict 预设，无参数的项目模式）
```

### 模块系统

功能模块位于 `modules/` 目录，由 `modules/__init__.py` 自动发现加载（`.py` 文件与子目录均可）。禁用模块：将 `.py` 重命名为 `.dis`。

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

AI 聊天模块（`.chat`）需要在 `others` 中配置后端：

```json
"others": {
    "enable": "gemini",
    "gemini_key": "",
    "ds_ck": "",
    "ds_auth": "",
    "white": []
  }
```

`enable` 可选 `gemini` / `deepseek` / `openai`；`white` 为聊天白名单。

## 环境

- Python 3.12（`.python-version` 锁定；`pyproject.toml` 声明 `requires-python = ">=3.12,<3.13"`）
- 依赖声明于 `pyproject.toml`，版本锁定于 `uv.lock`
- 代码质量：ruff（lint + format）与 pyrefly（strict 类型检查），配置均在 `pyproject.toml`
