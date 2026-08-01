# AGENTS.md

## Project

HypeR Bot — a Python QQ bot framework implementing OneBot v11 protocol.
Core library: `hyperot` (pip: `hyper-bot`), using `cfgr` (pip: `ucfgr`) for config management.

**HypeR Bot ≠ HyperBotCore (`hyperot`).** They originated from the same project but are now split into separate repos. This repo's public mirror is no longer updated; the canonical `hyperot` source is at <https://github.com/HarcicYang/HyperotBotCore>.

### Documentation status

`documents/` and `readme.md` are **outdated** — do not rely on them. The source code (especially `ModuleClass.py`, `main.py`, and modules under `modules/`) is the only current reference. When in doubt about `hyperot` APIs, consult the HyperotBotCore repo above.

### Functional modules

"Functional modules" (`modules/`) are the bot's feature implementations. They depend on both `hyperot` and `ModuleClass.py`.

## Entry point & startup

```shell
uv run python main.py
```

- On first run, `config.json` is auto-created; edit it before restarting.
- Config must exist **before** importing `hyperot.adapters` — the import order in `main.py` is intentional.
- Dependency management uses **uv**: `uv sync` (installs runtime + dev deps into `.venv`, Python 3.12).
  Versions are locked in `uv.lock`; `pyproject.toml` is the single source of dependency truth.

## Module system

Modules live in `modules/` and are auto-discovered by `modules/__init__.py`.
Both `.py` files and subdirectories (packages, e.g. `GuesserTools/`) are imported as modules.
Disabled modules: rename from `.py` to `.dis`.

### Two module base classes

**`ModuleClass.Module`** — handles events directly. Override `handle()`.

**`ModuleClass.CommandHandler`** (extends `Module`) — routes subcommands via `@command` decorator.
Parses `self.event.message` with `String.cmdl_parse()`, then dispatches to matching handler methods.

```python
@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class MyCommands(ModuleClass.CommandHandler):
    @ModuleClass.command([".cmd", "sub"], mapping={2: "arg_name"})
    async def handle_sub(self, arg_name: str = "default"):
        await self.actions.send_msg(group_id=self.event.group_id, user_id=self.event.user_id, ...)
```

### Module skeleton (standard Module)

```python
from typing import override

from hyperot.events import *
from hyperot import common, segments
import ModuleClass


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Example",
            desc="Short description",
            helps="Full help text",
        )

    @staticmethod
    def filter(event, allowed) -> bool:
        # Optional: custom filtering beyond the registered event types.
        # Called by main.py before spawning the task.
        # Return False to skip this event entirely.
        return ModuleClass.Module.filter(event, allowed)

    @override
    async def handle(self): ...
```

### Gotchas

- **`Module` is generic over the event type** — declare `ModuleClass.Module[GroupMessageEvent]` (matching the types passed to `register()`). `self.event` then has that precise type inside `handle()`. For mixed types, use the `|` union or `isinstance()` narrowing.
- **`@override` required** — pyrefly (strict preset) requires the `typing.override` decorator on `handle()`/`filter()`/`info()` overrides.
- **`HyperNotify` events** — `HyperListenerStartNotify`/`HyperListenerStopNotify` fire on startup/shutdown. Most modules should filter them out in `filter()`.
- **`send_msg` is canonical** — use `self.actions.send_msg(group_id=..., user_id=..., message=...)`. Note: `self.actions.send(...)` does **not** exist in hyperot 1.0.0's `ActionsBase`.
- **`group_id`/`user_id` are `int | None`** — narrow with `if self.event.group_id is None: return` before passing them to actions like `set_group_ban`/`get_stranger_info`. `del_msg`/`get_msg`/`set_essence_msg` take `int` message ids — cast with `int(...)`.

### Reloading modules

`ModuleClass.load()` clears all registered modules, then `importlib.reload()`s the `modules` package. No hot-reload at runtime.

### Command / DSL parsing

`ModuleClass.String(cmd).cmdl_parse()` parses space-delimited commands with `"quoted args"` and `key=value` pairs. Returns a list of `String` and `dict` items.

## Configuration

- File: `config.json` (gitignored)
- Access: `configurator.BotConfig.get("hyper-bot")`
- Write: `config.write()`
- Custom keys under `config.others` dict (e.g. AI keys, feature flags).

## Key APIs

- **Event**: `self.event.message`, `.group_id`, `.user_id`, `.blocked`, `.is_owner`, `.message_id`, `.time`
- **Actions**: `self.actions.send_msg(...)`, `.set_group_ban(...)`, `.del_msg(info)`, `.get_version_info()`
- **Message construction**: `common.Message(segments.Text("..."), segments.Image(path), segments.At(qq), segments.Reply(msg_id))`
- **Segments in messages**: iterate `self.event.message` for typed segments

## Environment

- Python 3.12 (locked via `.python-version`; `requires-python = ">=3.12,<3.13"` in `pyproject.toml`)
- Virtualenv: `.venv/` (managed by uv; old `active/`/`venvback/` removed)
- Dependencies: declared in `pyproject.toml`, locked in `uv.lock` — no `requirements*.txt` files
- Linting/formatting: **ruff** (`uv run ruff check` / `uv run ruff format`, line-length 120, config in `pyproject.toml`)
- Type checking: **pyrefly** strict preset (`uv run pyrefly check`, config in `pyproject.toml`)
- No CI, no test suite — `tester.py` and `test2.py` are ad-hoc scripts
- Editor: Zed configured in `.zed/settings.json` (pyrefly + ruff LSPs from `.venv/bin`)
- **pyrefly 用项目模式**:`uv run pyrefly check`(无参数)。显式传路径(如 `pyrefly check .`)会进入单文件模式,配置里的 `project-excludes` 与 `.gitignore` 均不生效,会把 vendored 目录(`lagrange/`、`lgr.kritor/` 等)一并扫描报错——那是第三方旧代码,不是本 bot 的问题
