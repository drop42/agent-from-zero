"""EP03：主循环接入权限检查 —— 模型提出调用，代码裁决是否执行。"""

import json
import os
import sys

from openai import OpenAI

from .permissions import PermissionManager
from .tools import execute, get_schemas

BASE_URL = os.environ.get("BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("MODEL", "deepseek-chat")
MAX_STEPS = 20  # 防止模型陷入无限循环

SYSTEM = (
    "你是一个能使用工具的助手，在用户当前目录下完成任务。"
    "必要时调用工具，完成后用简洁的语言汇报结果。"
)


def _client() -> OpenAI:
    """延迟构造，避免 import 阶段就要求 API_KEY。"""
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("缺少环境变量 API_KEY（以及可选的 BASE_URL / MODEL）")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def handle_call(call, perms: PermissionManager) -> str:
    """解析参数 → 权限检查 → 执行。永远返回字符串。"""
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Error: 参数不是合法的 JSON"
    decision = perms.check(name, args)
    if not decision.allowed:
        return f"[权限拒绝] {decision.reason}"  # 拒绝也要回传，让模型换条路
    return execute(name, args)


def run(user_input: str, messages: list[dict], perms: PermissionManager) -> str:
    client = _client()
    messages.append({"role": "user", "content": user_input})

    for _ in range(MAX_STEPS):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=get_schemas()
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # 没有工具调用，说明模型给出了最终回答
        if not msg.tool_calls:
            return msg.content or ""

        # 模型可能一轮里请求多个工具，每个都必须回应
        for call in msg.tool_calls:
            print(f"🔧 {call.function.name}({call.function.arguments[:80]})")
            result = handle_call(call, perms)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    return "（达到最大步数，已停止）"


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    messages = [{"role": "system", "content": SYSTEM}]
    perms = PermissionManager()  # 整个会话共用，"本次会话一直允许"记在它身上

    # 带参数 = 单次任务（便于脚本化）；不带参数 = 交互式对话，messages 跨轮保留
    if argv:
        print("\n" + run(" ".join(argv), messages, perms) + "\n")
        return

    while True:
        try:
            q = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q in ("exit", "quit"):
            break
        if not q:
            continue
        print("\n" + run(q, messages, perms) + "\n")
