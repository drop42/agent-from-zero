"""EP06：核心逻辑与 I/O 分离 —— 一个会话 = messages + 权限 + 上一次 token 数。"""

import contextvars
import json
import os
import sys

from openai import OpenAI

from . import scheduler  # noqa: F401 导入即注册 plan/schedule 相关工具
from . import mcp_client
from . import memory  # noqa: F401 导入即注册 remember / search_sessions
from . import planning  # noqa: F401 导入即注册 update_plan / submit_plan
from . import subagent  # noqa: F401 导入即注册 delegate 工具
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

    return (
        SYSTEM
        + skills.project_notes()
        + skills.skills_section()
        + memory.memory_section()  # 第 11 课：会话开始时的一份快照
    )


def make_client() -> OpenAI:
    """延迟构造，避免 import 阶段就要求 API_KEY。"""
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("缺少环境变量 API_KEY（以及可选的 BASE_URL / MODEL）")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


class Session:
    """一个会话 = messages + 权限管理器 + 上一次 token 数。

    tools 限定能用的工具（None 表示全部），system 可替换，depth 记录是第几层。
    """

    def __init__(
        self,
        name: str,
        ask=None,
        persist: bool = True,
        tools=None,
        system: str | None = None,
        depth: int = 0,
    ):
        self.name = name
        self.persist = persist
        self.tools = set(tools) if tools is not None else None
        self.depth = depth
        saved = load_session(name) if persist else None
        self.messages = saved or [{"role": "system", "content": ""}]
        # 会话里存的是旧 system prompt，每次用最新的技能列表覆盖第一条
        self.messages[0] = {"role": "system", "content": system or build_system()}
        self.perms = PermissionManager(ask=ask)
        self.prompt_tokens = 0
        self.plan: list[dict] = []  # 第 10 课：最近一版待办清单

    def save(self) -> None:
        if self.persist:
            save_session(self.name, self.messages)

    def schemas(self) -> list[dict]:
        all_ = get_schemas()
        if self.tools is None:
            return all_
        return [s for s in all_ if s["function"]["name"] in self.tools]


def handle_call(call, perms: PermissionManager, allowed=None) -> str:
    """解析参数 → 权限检查 → 执行。永远返回字符串。"""
    name = call.function.name
    if allowed is not None and name not in allowed:
        # 模型偶尔会编出一个没发给它的工具名；能不能用由执行层说了算
        return f"Error: 当前不能使用工具 {name}"
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Error: 参数不是合法的 JSON"
    decision = perms.check(name, args)
    if not decision.allowed:
        return f"[权限拒绝] {decision.reason}"  # 拒绝也要回传，让模型换条路
    return execute(name, args)


# 子 Agent 的工具需要知道"是谁派的我"：用 ContextVar 而不是全局变量，
# 因为并行子 Agent 会在多个线程里同时运行
CURRENT: contextvars.ContextVar = contextvars.ContextVar("current_run", default=None)


def run(
    session: Session, user_input: str, client, model: str = MODEL, log=print, max_steps: int = MAX_STEPS
) -> str:
    token = CURRENT.set((session, client, model, log))
    try:
        return _loop(session, user_input, client, model, log, max_steps)
    finally:
        CURRENT.reset(token)


def _loop(session: Session, user_input: str, client, model: str, log, max_steps: int) -> str:
    messages = session.messages
    messages.append({"role": "user", "content": user_input})

    for _ in range(max_steps):
        # 用上一次调用的真实 token 数决定这一轮要不要处理
        if session.prompt_tokens > HARD_LIMIT:
            messages[:] = compact(client, model, messages)
        elif session.prompt_tokens > SOFT_LIMIT:
            clear_old_tool_results(messages)

        resp = client.chat.completions.create(
            model=model, messages=messages, tools=session.schemas()
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
            result = handle_call(call, session.perms, session.tools)
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
    mcp_client.load_servers()  # 第 8 课：先接入 MCP 工具，再建会话
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
        if q.startswith("/plan "):  # 第 10 课：进不进计划模式，由人决定
            print("\n" + run(session, planning.enter_plan_mode(session, q[6:]), client) + "\n")
            session.save()
            continue
        print("\n" + run(session, q, client) + "\n")
        session.save()
