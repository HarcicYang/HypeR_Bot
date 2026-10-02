from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Literal

from hyperot.v2.events import Event, MessageReceivedEvent
from typing_extensions import override

import ModuleClass

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_REPLY_CHARS = 1800
COMMAND_TIMEOUT = 300
UpdateAction = Literal["reload", "restart", "none"]


class UpdateError(RuntimeError):
    pass


def classify_paths(paths: list[str]) -> UpdateAction:
    """按更新后动作分类；modules/ 之外的变化一律重启。"""
    if not paths:
        return "none"
    if all(path.startswith("modules/") for path in paths):
        return "reload"
    return "restart"


def needs_sync(paths: list[str], lock_was_dirty: bool) -> bool:
    return lock_was_dirty or "pyproject.toml" in paths or "uv.lock" in paths


def clip_output(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_REPLY_CHARS:
        return text
    return text[: MAX_REPLY_CHARS - 20] + "\n...（输出已截断）"


async def run_command(command: list[str]) -> tuple[int, str]:
    executable = shutil.which(command[0])
    if executable is None:
        return 127, f"命令不存在: {command[0]}"
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    process = await asyncio.create_subprocess_exec(
        executable,
        *command[1:],
        cwd=str(REPO_ROOT),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=COMMAND_TIMEOUT)
    except TimeoutError:
        process.kill()
        await process.wait()
        return 124, f"命令超时({COMMAND_TIMEOUT}s): {' '.join(command)}"
    code = process.returncode if process.returncode is not None else -1
    return code, stdout.decode("utf-8", errors="replace")


async def git(*args: str) -> tuple[int, str]:
    return await run_command(["git", *args])


async def uv(*args: str) -> tuple[int, str]:
    return await run_command(["uv", *args])


async def dirty_paths() -> list[str]:
    code, output = await git("status", "--porcelain", "--untracked-files=no")
    if code != 0:
        raise UpdateError("读取 git 状态失败:\n" + clip_output(output))
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            paths.append(path)
    return sorted(set(paths))


async def current_branch() -> str:
    code, output = await git("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        raise UpdateError("读取当前分支失败:\n" + clip_output(output))
    branch = output.strip()
    if not branch or branch == "HEAD":
        raise UpdateError("当前处于 detached HEAD，无法在线更新")
    return branch


async def changed_paths(upstream: str) -> list[str]:
    code, output = await git("diff", "--name-only", f"HEAD..{upstream}")
    if code != 0:
        raise UpdateError("读取变更文件失败:\n" + clip_output(output))
    return [line.strip() for line in output.splitlines() if line.strip()]


async def fetch_upstream() -> None:
    code, output = await git("fetch", "--prune")
    if code != 0:
        raise UpdateError("git fetch 失败:\n" + clip_output(output))


async def upstream_is_ahead(upstream: str) -> bool:
    code, output = await git("rev-parse", "--verify", upstream)
    if code != 0:
        raise UpdateError(f"上游分支不存在: {upstream}\n" + clip_output(output))
    code, output = await git("merge-base", "--is-ancestor", "HEAD", upstream)
    if code != 0:
        raise UpdateError("本地分支不是上游祖先，拒绝非 fast-forward 更新")
    return True


@ModuleClass.ModuleRegister.register(MessageReceivedEvent)
class Module(ModuleClass.Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Update",
            desc="在线更新 Bot 代码",
            helps=(
                ".update - 检查并执行更新\n"
                ".update check - 只检查更新\n"
                ".update reload - 仅允许全量 reload 的更新\n"
                ".update restart - 强制按 restart 处理\n"
                ".update force - tracked dirty 时丢弃本地修改后继续"
            ),
        )

    @override
    @staticmethod
    def filter(event: Event, allowed: list[Any]) -> bool:
        if not isinstance(event, MessageReceivedEvent):
            return False
        if not ModuleClass.is_owner(event):
            return False
        text = str(event.message).strip().lower()
        return text == ".update" or text.startswith(".update ")

    @override
    async def handle(self) -> None:
        parts = str(self.event.message).strip().lower().split()
        if len(parts) > 2:
            await self._reply("用法: .update [check|reload|restart|force]")
            return
        mode = parts[1] if len(parts) == 2 else "auto"
        if mode not in ("auto", "check", "reload", "restart", "force"):
            await self._reply("用法: .update [check|reload|restart|force]")
            return

        force = mode == "force"
        if force:
            mode = "auto"
        try:
            if mode == "check":
                await self._check()
                return
            ModuleClass.set_maintenance(True)
            handed_off = False
            try:
                handed_off = await self._apply(mode, force)
            finally:
                if not handed_off:
                    ModuleClass.set_maintenance(False)
        except UpdateError as exc:
            await self._reply(str(exc))
        except Exception as exc:
            await self._reply(f"更新失败: {type(exc).__name__}: {exc}")

    async def _check(self) -> None:
        await fetch_upstream()
        dirty = await dirty_paths()
        branch = await current_branch()
        upstream = f"origin/{branch}"
        await upstream_is_ahead(upstream)
        paths = await changed_paths(upstream)
        action = classify_paths(paths)
        if "uv.lock" in dirty:
            action = "restart"
        lines = [f"当前分支: {branch}", f"变更文件: {len(paths)}", f"更新后动作: {action}"]
        if not paths:
            lines.append("状态: 已是最新版本")
        elif dirty == ["uv.lock"]:
            lines.append("tracked dirty: 仅 uv.lock，允许更新，merge 后执行 uv sync")
        elif dirty:
            lines.append("tracked dirty: " + ", ".join(dirty) + "；需要 .update force")
        else:
            lines.append("tracked dirty: 无")
        await self._reply("\n".join(lines))

    async def _apply(self, mode: str, force: bool) -> bool:
        await self._reply("正在检查更新...")
        await fetch_upstream()

        dirty = await dirty_paths()
        lock_was_dirty = "uv.lock" in dirty
        dirty_lock_only = dirty == ["uv.lock"]
        if dirty and not dirty_lock_only and not force:
            raise UpdateError("检测到 tracked dirty，拒绝更新:\n" + "\n".join(dirty) + "\n可使用 .update force")

        branch = await current_branch()
        upstream = f"origin/{branch}"
        await upstream_is_ahead(upstream)
        paths = await changed_paths(upstream)
        action = classify_paths(paths)
        if lock_was_dirty:
            action = "restart"
        if mode == "reload" and (not paths or action != "reload"):
            if not paths:
                await self._reply("已是最新版本")
            else:
                await self._reply("本次变更包含 modules/ 之外的文件，不能只 reload，请使用 .update restart")
            return False
        if not paths:
            if needs_sync(paths, lock_was_dirty):
                if dirty_lock_only:
                    code, output = await git("restore", "--staged", "--worktree", "--", "uv.lock")
                    if code != 0:
                        raise UpdateError("清理 uv.lock 失败:\n" + clip_output(output))
                code, output = await uv("sync")
                if code != 0:
                    raise UpdateError("uv sync 失败，已停止后续动作:\n" + clip_output(output))
                await self._reply("已是最新版本，已重新同步依赖，准备重启")
                if not ModuleClass.request_restart():
                    await self._reply("重启请求未能提交")
                    return False
                return True
            await self._reply("已是最新版本")
            return False
        if mode == "restart":
            action = "restart"

        if dirty and not dirty_lock_only:
            code, output = await git("restore", "--staged", "--worktree", "--", *dirty)
            if code != 0:
                raise UpdateError("清理 tracked dirty 失败:\n" + clip_output(output))
        elif dirty_lock_only:
            code, output = await git("restore", "--staged", "--worktree", "--", "uv.lock")
            if code != 0:
                raise UpdateError("清理 uv.lock 失败:\n" + clip_output(output))

        code, output = await git("merge", "--ff-only", upstream)
        if code != 0:
            raise UpdateError("fast-forward 更新失败:\n" + clip_output(output))

        if needs_sync(paths, lock_was_dirty):
            code, output = await uv("sync")
            if code != 0:
                raise UpdateError("uv sync 失败，已停止后续动作:\n" + clip_output(output))

        if action == "reload":
            await self._reply("更新完成，开始全量 reload")
            if not ModuleClass.request_reload():
                await self._reply("已有全量重载任务正在执行")
                return False
            return True
        else:
            await self._reply("更新完成，准备重启")
            if not ModuleClass.request_restart():
                await self._reply("重启请求未能提交")
                return False
            return True

    async def _reply(self, message: str) -> None:
        await self.api.scene(self.event.scene_type, self.event.scene_id).send(message)
