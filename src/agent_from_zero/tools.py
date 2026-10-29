"""EP02：工具系统 —— 注册表 + 统一执行器。

加一个工具只需写一个函数、套一个 @tool 装饰器，主循环不用动。
所有错误都在 execute() 里转成字符串结果返回给模型，让它自己修正。
"""

import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

MAX_OUTPUT = 8000  # 工具返回给模型的最大字符数

# 注册表：name -> {"schema": ..., "func": ...}
TOOLS: dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict) -> Callable:
    """装饰器：把一个函数注册为工具"""

    def decorator(func: Callable) -> Callable:
        TOOLS[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "func": func,
        }
        return func

    return decorator


def get_schemas() -> list[dict]:
    """返回给模型看的全部工具说明书"""
    return [t["schema"] for t in TOOLS.values()]


def _params(**props: str) -> dict:
    """简写：所有参数都是必填的字符串"""
    return {
        "type": "object",
        "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
        "required": list(props),
    }


# ------------------------------------------------------------- 五个实用工具


@tool("list_dir", "列出某个目录下的文件和子目录。", _params(path="目录路径，当前目录写 ."))
def list_dir(path: str = ".") -> str:
    p = Path(path)
    return (
        "\n".join(
            sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
        )
        or "(空目录)"
    )


@tool("read_file", "读取一个文本文件的内容。", _params(path="文件路径"))
def read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


@tool(
    "write_file",
    "把内容写入文件，已存在则覆盖，目录不存在会自动创建。",
    _params(path="文件路径", content="要写入的完整内容"),
)
def write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {path}（{len(content)} 字符）"


@tool(
    "run_shell",
    "在当前目录执行一条 shell 命令，返回退出码、标准输出和错误输出。",
    _params(command="要执行的命令"),
)
def run_shell(command: str) -> str:
    p = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # Windows 控制台可能输出非 UTF-8 字节，避免解码崩溃
        timeout=30,
    )
    return f"[exit {p.returncode}]\n{p.stdout}{p.stderr}"


@tool(
    "fetch_url",
    "抓取一个网页或接口的文本内容。url 必须以 http 或 https 开头。",
    _params(url="完整的 URL"),
)
def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "nami-agent"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ----------------------------------------------------------- 统一执行器


def execute(name: str, args: dict) -> str:
    """执行工具，永远返回字符串，永远抛异常"""
    if name not in TOOLS:
        return f"Error: 不存在工具 '{name}'，可用工具：{', '.join(TOOLS)}"
    try:
        result = str(TOOLS[name]["func"](**args))
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
    if len(result) > MAX_OUTPUT:
        result = result[:MAX_OUTPUT] + f"\n...（已截断，共 {len(result)} 字符）"
    return result
