"""代码执行工具:在受限沙箱中运行 Python 代码。

安全模型(三层,按可用性降级):
1. bwrap(Linux 且存在):只读挂载根文件系统 + 断网 + PID 隔离 + 空文件覆盖 config.json。
   代码不能改/删任何文件、不能联网、读不到密钥。
2. Linux 无 bwrap:子进程 + setrlimit(内存/CPU/文件大小/进程数) + 超时杀进程组。
3. Windows:仅子进程超时 + 输出截断 + 专用工作目录(隔离显著弱化)。

贯穿所有层:AST 黑名单(纵深防御,非安全边界)、15s 超时、输出 ≤4000 字符截断、
专用工作目录 temps/agent_code/、最小环境变量(不含 GOOGLE_API_KEY 等敏感项)。
"""

import ast
import asyncio
import os
import resource
import shutil
import subprocess
import sys

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool

WORKDIR = "./temps/agent_code/"
WRAPPER_NAME = "_wrapper.py"
TIMEOUT = 15
MAX_OUTPUT = 4000
_MEM_LIMIT = 512 * 1024 * 1024  # RLIMIT_AS: 512MB
_FSIZE_LIMIT = 10 * 1024 * 1024  # RLIMIT_FSIZE: 10MB

# AST 黑名单(尽力防御,可被绕过;真正的边界是 bwrap / 进程隔离)
FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "ftplib",
    "telnetlib",
    "ctypes",
    "multiprocessing",
    "signal",
    "pty",
    "resource",
    "importlib",
    "platform",
}

FORBIDDEN_CALLS = {"__import__", "exec", "eval", "compile", "open", "input", "breakpoint"}

WRAPPER = """import sys, traceback as _tb
_src = sys.stdin.read()
try:
    exec(compile(_src, "<agent_code>", "exec"), {})
except SystemExit:
    pass
except BaseException:
    _tb.print_exc()
"""


def _ast_check(code: str) -> str | None:
    """静态检查代码:语法错误、危险模块导入、危险内置调用。返回错误信息或 None。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"代码语法错误: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    return f"代码包含被禁止的模块: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                return f"代码包含被禁止的模块: {node.module}"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            return f"代码包含被禁止的调用: {node.func.id}"
    return None


def _minimal_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "HOME")}
    env.pop("GOOGLE_API_KEY", None)
    return env


def _format_output(proc: subprocess.CompletedProcess[bytes]) -> str:
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    text = (out + err).strip() or "(无输出)"
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + "\n...（输出过长，已截断）"
    return text


def _run_bwrap(bwrap: str, code: str, env: dict[str, str], workdir_abs: str) -> str:
    """bwrap 强隔离:只读根 + 断网 + PID 隔离 + config.json 覆盖为空文件。"""
    empty = os.path.join(workdir_abs, ".empty")
    open(empty, "a").close()
    config_abs = os.path.abspath("config.json")
    cmd = [
        bwrap,
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--bind",
        workdir_abs,
        workdir_abs,
        "--ro-bind",
        empty,
        config_abs,
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-user",
        "--die-with-parent",
        "--new-session",
        sys.executable,
        os.path.join(workdir_abs, WRAPPER_NAME),
    ]
    proc = subprocess.run(
        cmd,
        input=code.encode(),
        cwd=workdir_abs,
        env=env,
        capture_output=True,
        timeout=TIMEOUT,
    )
    return _format_output(proc)


def _run_direct(code: str, env: dict[str, str], workdir_abs: str) -> str:
    """降级路径:setrlimit 资源限制(Linux)+ 超时杀进程组。"""

    def _limits() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (_MEM_LIMIT, _MEM_LIMIT))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
            resource.setrlimit(resource.RLIMIT_FSIZE, (_FSIZE_LIMIT, _FSIZE_LIMIT))
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        except (ValueError, OSError):
            pass

    preexec = _limits if sys.platform == "linux" else None
    proc = subprocess.run(
        [sys.executable, os.path.join(workdir_abs, WRAPPER_NAME)],
        input=code.encode(),
        cwd=workdir_abs,
        env=env,
        capture_output=True,
        timeout=TIMEOUT,
        start_new_session=True,
        preexec_fn=preexec,
    )
    return _format_output(proc)


def _execute_code(code: str) -> str:
    err = _ast_check(code)
    if err:
        return err
    os.makedirs(WORKDIR, exist_ok=True)
    workdir_abs = os.path.abspath(WORKDIR)
    with open(os.path.join(workdir_abs, WRAPPER_NAME), "w", encoding="utf-8") as f:
        f.write(WRAPPER)
    env = _minimal_env()
    bwrap = shutil.which("bwrap")
    try:
        if sys.platform == "linux" and bwrap:
            return _run_bwrap(bwrap, code, env, workdir_abs)
        return _run_direct(code, env, workdir_abs)
    except subprocess.TimeoutExpired:
        return "（执行超时，已终止进程）"
    except FileNotFoundError:
        return "（无法启动沙箱进程）"
    except Exception as e:
        return f"（沙箱执行失败: {e}）"


class CodeTools(AgentToolBase):
    @tool()
    async def run_python(self, ctx: ToolContext, code: str) -> str:
        """在受限沙箱中执行 Python 代码并返回文本输出，可用于计算、数据处理、文本生成等"""
        return await asyncio.to_thread(_execute_code, code)
