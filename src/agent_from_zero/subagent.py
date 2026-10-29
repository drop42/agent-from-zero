"""EP09：子 Agent —— 独立上下文的帮手，用完只交回结论。

并行的只读，写入的单线程；只允许一层。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .permissions import TOOL_RISK, Risk
from .tools import TOOLS, _params, tool

MAX_DEPTH = 1  # 只允许一层：子 Agent 不能再派子 Agent
SUB_MAX_STEPS = 15
MAX_PARALLEL = 3
RESULT_LIMIT = 3000  # 子 Agent 交回来的结论最多这么长

# 这些工具子 Agent 永远拿不到：派生、定时任务都只能由主 Agent 做
NEVER_FOR_SUB = {
    "delegate",
    "delegate_parallel",
    "schedule_task",
    "cancel_task",
    "list_tasks",
}

SUB_SYSTEM = (
    "你是一个子 Agent，被主 Agent 派来完成一件具体的事。"
    "你看不到主 Agent 和用户之前的对话，只能根据下面的任务说明行动。"
    "完成后用简洁的文字汇报结论，写清楚依据（读了哪些文件、看到了什么），"
    "不要贴大段原文。做不到就直接说明原因。"
)


def toolset(kind: str) -> set[str]:
    """explore：只拿只读工具；worker：除了派生和定时之外的全部工具。"""
    names = set(TOOLS) - NEVER_FOR_SUB
    if kind == "explore":
        names = {n for n in names if TOOL_RISK.get(n) is Risk.SAFE}
    return names


def _current():
    from .agent import CURRENT

    ctx = CURRENT.get()
    if ctx is None:
        raise RuntimeError("delegate 只能在一次 run() 里调用")
    parent, client, model, log = ctx
    if parent.depth >= MAX_DEPTH:
        raise RuntimeError(f"子 Agent 不能再派子 Agent（最多 {MAX_DEPTH} 层）")
    return parent, client, model, log


def _spawn(task, kind, parent, client, model, log, idx=None) -> str:
    from .agent import Session, run  # 延迟导入，避免和 agent.py 循环引用

    tag = f"子Agent{'' if idx is None else idx}"
    sub = Session(
        f"{parent.name}/{tag}",
        ask=parent.perms.ask,  # 子 Agent 不会比派它的那个 Agent 权限更大
        persist=False,
        tools=toolset(kind),
        system=SUB_SYSTEM,
        depth=parent.depth + 1,
    )
    try:
        result = run(
            sub,
            task,
            client,
            model,
            log=lambda m: log(f"  [{tag}] {m}"),
            max_steps=SUB_MAX_STEPS,
        )
    except Exception as e:
        return f"[{tag} 出错] {type(e).__name__}: {e}"
    if len(result) > RESULT_LIMIT:
        result = result[:RESULT_LIMIT] + "\n...（子 Agent 的结论过长，已截断）"
    return f"[{tag} 的结论]\n{result}"


@tool(
    "delegate",
    "把一件边界清楚的子任务交给一个子 Agent。它有独立的上下文，看不到当前对话，"
    "所以 task 里要写清目标、范围和希望交回的格式。"
    "kind=explore 只能读（查资料、读代码、找文件），kind=worker 还能写文件和执行命令，"
    "每个有副作用的操作照样需要用户确认。适合：要读很多内容但只需要结论的任务。",
    {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "完整的任务说明"},
            "kind": {"type": "string", "enum": ["explore", "worker"]},
        },
        "required": ["task"],
    },
)
def delegate(task: str, kind: str = "explore") -> str:
    try:
        parent, client, model, log = _current()
    except RuntimeError as e:
        return f"Error: {e}"
    return _spawn(task, kind, parent, client, model, log)


@tool(
    "delegate_parallel",
    f"同时派出多个只读子 Agent（最多 {MAX_PARALLEL} 个），各自完成一件互不依赖的调查，"
    "返回所有结论。tasks 是任务说明的列表。只能读，不能写。",
    {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "任务说明列表",
            }
        },
        "required": ["tasks"],
    },
)
def delegate_parallel(tasks: list[str]) -> str:
    try:
        parent, client, model, log = _current()
    except RuntimeError as e:
        return f"Error: {e}"
    if not tasks:
        return "Error: tasks 不能为空"
    if len(tasks) > MAX_PARALLEL:
        return f"Error: 一次最多 {MAX_PARALLEL} 个子 Agent，你给了 {len(tasks)} 个"
    with ThreadPoolExecutor(MAX_PARALLEL) as pool:
        futures = [
            pool.submit(_spawn, t, "explore", parent, client, model, log, i + 1)
            for i, t in enumerate(tasks)
        ]
        return "\n\n".join(f.result() for f in futures)
