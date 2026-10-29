"""EP01：最小 Agent 循环 —— 工具 + 工具说明 + 循环。

模型只会输出文字，真正的读写文件、跑命令由这里的代码执行；
执行结果作为 tool 消息追加回 messages，再交给模型，直到它不再请求工具。
"""

import json
import os
import subprocess
import sys

from openai import OpenAI

BASE_URL = os.environ.get("BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("MODEL", "deepseek-chat")
MAX_STEPS = 20  # 防止死循环：Agent 最多转 20 圈

SYSTEM = (
    "你是一个能操作本地文件和命令行的编程助手。"
    "需要时调用工具，完成任务后直接用文字总结，不要再调用工具。"
)

# ---------------------------------------------------------------- 1. 工具


def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"已写入 {path}（{len(content)} 字符）"


def run_shell(command: str) -> str:
    """第 1 课先用最朴素的权限控制：每条命令人工确认。"""
    if not sys.stdin.isatty():
        return "用户拒绝执行该命令（非交互环境无法确认）"
    try:
        answer = input(f"\n[需要确认] 执行命令：{command}\n允许？(y/n) ")
    except (EOFError, KeyboardInterrupt):  # 提示符出现后读不到输入
        return "用户拒绝执行该命令（未获得确认）"
    if answer.strip().lower() != "y":
        return "用户拒绝执行该命令"
    try:
        p = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return "命令超时（60 秒）"
    return (p.stdout + p.stderr)[-4000:] or "(无输出)"  # 截断，避免撑爆上下文


TOOL_FUNCS = {"read_file": read_file, "write_file": write_file, "run_shell": run_shell}

# ------------------------------------------------------------ 2. 工具说明


def _tool(name: str, desc: str, props: dict[str, str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {
                    k: {"type": "string", "description": v} for k, v in props.items()
                },
                "required": list(props),
            },
        },
    }


TOOLS = [
    _tool("read_file", "读取文件内容", {"path": "文件路径"}),
    _tool(
        "write_file",
        "写入文件（覆盖）",
        {"path": "文件路径", "content": "完整文件内容"},
    ),
    _tool("run_shell", "执行 shell 命令并返回输出", {"command": "要执行的命令"}),
]


def _client() -> OpenAI:
    """延迟构造，避免 import 阶段就要求 API_KEY。"""
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("缺少环境变量 API_KEY（以及可选的 BASE_URL / MODEL）")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


# --------------------------------------------------------------- 3. 循环


def run(task: str) -> None:
    client = _client()
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]
    for step in range(1, MAX_STEPS + 1):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # 模型没有要调用工具 = 它认为任务做完了，循环结束
        if not msg.tool_calls:
            print(f"\n[完成，共 {step} 步]\n{msg.content}")
            return

        # 模型要调用工具：执行，并把结果作为 tool 消息喂回去
        for call in msg.tool_calls:
            name = call.function.name
            print(f"[第 {step} 步] {name}({call.function.arguments[:80]})")
            try:
                args = json.loads(call.function.arguments)
                result = TOOL_FUNCS[name](**args)
            except Exception as e:  # 工具出错也要告诉模型，让它自己修正
                result = f"工具执行出错：{type(e).__name__}: {e}"
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    print(f"\n[达到 {MAX_STEPS} 步上限，已停止]")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        sys.exit('用法：uv run agent-from-zero "你的任务"')
    run(" ".join(argv))
