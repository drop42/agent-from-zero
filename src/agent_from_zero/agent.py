"""EP06：核心逻辑与 I/O 分离 —— 一个会话 = messages + 权限 + 上一次 token 数。"""

import json
import os
import sys

from openai import OpenAI

from . import scheduler  # noqa: F401 导入即注册 plan/schedule 相关工具
from .context import (
    clear_old_tool_results,
    compact,
    load_session,
    save_session,
    truncate_tool_result,
)
from .permissions import PermissionManager
from .tools import execute, get_schemas

BASE_URL = os.environ.get("BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("MODEL", "deepseek-chat")
MAX_STEPS = 20  # 防止模型陷入无限循环

# 超过 SOFT_LIMIT：清理旧工具结果；超过 HARD_LIMIT：摘要压缩。
SOFT_LIMIT = int(os.environ.get("NAMI_SOFT_LIMIT", 16000))
HARD_LIMIT = int(os.environ.get("NAMI_HARD_LIMIT", 24000))

SYSTEM = (
    "你是一个能使用工具的助手，在用户当前目录下完成任务。"
    "必要时调用工具，完成后用简洁的语言汇报结果。"
)


def build_system() -> str:
    """基础说明 + AGENTS.md（常驻）+ 技能目录（只有名字和一句话用途）。"""
    from . import skills  # noqa: F401 导入即注册 load_skill

    return SYSTEM + skills.project_notes() + skills.skills_section()


def make_client() -> OpenAI:
    """延迟构造，避免 import 阶段就要求 API_KEY。"""
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("缺少环境变量 API_KEY（以及可选的 BASE_URL / MODEL）")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


class Session:
    """一个会话 = 一份 messages + 一个权限管理器 + 上一次的 token 数。"""

    def __init__(self, name: str, ask=None, persist: bool = True):
        self.name = name
        self.persist = persist
        saved = load_session(name) if persist else None
        self.messages = saved or [{"role": "system", "content": ""}]
        # 会话里存的是旧 system prompt，每次用最新的技能列表覆盖第一条
        self.messages[0] = {"role": "system", "content": build_system()}
        self.perms = PermissionManager(ask=ask)
        self.prompt_tokens = 0

    def save(self) -> None:
        if self.persist:
            save_session(self.name, self.messages)


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


def run(session: Session, user_input: str, client, model: str = MODEL, log=print) -> str:
    messages = session.messages
    messages.append({"role": "user", "content": user_input})

    for _ in range(MAX_STEPS):
        # 用上一次调用的真实 token 数决定这一轮要不要处理
        if session.prompt_tokens > HARD_LIMIT:
            messages[:] = compact(client, model, messages)
        elif session.prompt_tokens > SOFT_LIMIT:
            clear_old_tool_results(messages)

        resp = client.chat.completions.create(
            model=model, messages=messages, tools=get_schemas()
        )
        session.prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        # 没有工具调用，说明模型给出了最终回答
        if not msg.tool_calls:
            return msg.content or ""

        # 模型可能一轮里请求多个工具，每个都必须回应
        for call in msg.tool_calls:
            log(f"🔧 {call.function.name}({call.function.arguments[:80]})")
            result = handle_call(call, session.perms)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    # 第 1 层：进入 messages 前再截断一次，头尾都留
                    "content": truncate_tool_result(result),
                }
            )

    return "（达到最大步数，已停止）"


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    client = make_client()
    session = Session("default")  # ask 不传，默认还是终端确认

    # 带参数 = 单次任务（便于脚本化）；不带参数 = 交互式对话
    if argv:
        print("\n" + run(session, " ".join(argv), client) + "\n")
        session.save()
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
        print("\n" + run(session, q, client) + "\n")
        session.save()
