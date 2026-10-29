"""EP09：子 Agent 的测试 —— 结论回传、工具清单、层数限制、并行上限。"""

import copy
import json

from agent_from_zero import agent, subagent
from agent_from_zero.permissions import WORKSPACE


class _Call:
    def __init__(self, cid, name, args):
        self.id = cid
        self.function = type("F", (), {"name": name, "arguments": json.dumps(args)})()


class _Msg:
    def __init__(self, content=None, calls=None):
        self.content = content
        self.tool_calls = calls

    def model_dump(self, **kw):
        out = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            out["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in self.tool_calls
            ]
        return out


class FakeClient:
    """按顺序回放脚本：每个元素要么是 [tool_call, ...]，要么是一段文本。"""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kw):
        self.seen.append(copy.deepcopy(kw["messages"]))
        item = self.script.pop(0)
        msg = _Msg(item) if isinstance(item, str) else _Msg(None, item)
        resp = type("R", (), {})()
        resp.choices = [type("Ch", (), {"message": msg})()]
        resp.usage = type("U", (), {"prompt_tokens": 10})()
        return resp


def test_delegate_returns_only_conclusion():
    (WORKSPACE / "big.txt").write_text("x" * 5000, encoding="utf-8")
    c = FakeClient(
        [
            [_Call("p1", "delegate", {"task": "读 big.txt，告诉我它有多长", "kind": "explore"})],
            [_Call("s1", "read_file", {"path": "big.txt"})],  # 子 Agent 读文件
            "big.txt 有 5000 个字符",  # 子 Agent 的结论
            "子 Agent 说文件有 5000 个字符",  # 主 Agent 的回答
        ]
    )
    s = agent.Session("main", ask=lambda n, a: ("n", ""), persist=False)
    out = agent.run(s, "big.txt 多长？", c, log=lambda *_: None)
    assert out == "子 Agent 说文件有 5000 个字符"
    # 主 Agent 的上下文里只有结论，没有 5000 个 x
    tool_msgs = [m["content"] for m in s.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1 and "5000 个字符" in tool_msgs[0] and "xxxx" not in tool_msgs[0]
    # 子 Agent 只拿到了只读工具，而且有自己的 system prompt
    sub_request = c.seen[1]
    assert sub_request[0]["content"].startswith("你是一个子 Agent")
    assert len(sub_request) == 2  # system + 任务，没有主对话的历史


def test_explore_cannot_write_even_if_model_asks():
    c = FakeClient(
        [
            [_Call("p1", "delegate", {"task": "写个文件", "kind": "explore"})],
            [_Call("s1", "write_file", {"path": "a.txt", "content": "x"})],
            "我做不到",
            "子 Agent 说做不到",
        ]
    )
    s = agent.Session("main", ask=lambda n, a: ("y", ""), persist=False)
    agent.run(s, "写文件", c, log=lambda *_: None)
    assert len(c.seen[1]) == 2  # 子 Agent 的第一个请求只有 system + 任务
    assert "当前不能使用工具 write_file" in c.seen[2][-1]["content"]


def test_subagent_cannot_delegate_again():
    parent = agent.Session("main", ask=lambda n, a: ("n", ""), persist=False, depth=1)
    token = agent.CURRENT.set((parent, FakeClient([]), "m", print))
    try:
        out = subagent.delegate("再派一层")
    finally:
        agent.CURRENT.reset(token)
    assert out.startswith("Error: 子 Agent 不能再派子 Agent")


def test_parallel_limit_and_empty():
    parent = agent.Session("main", ask=lambda n, a: ("n", ""), persist=False)
    token = agent.CURRENT.set((parent, FakeClient([]), "m", print))
    try:
        assert subagent.delegate_parallel([]).startswith("Error: tasks 不能为空")
        out = subagent.delegate_parallel(["a", "b", "c", "d"])
        assert f"一次最多 {subagent.MAX_PARALLEL} 个" in out
    finally:
        agent.CURRENT.reset(token)


def test_toolsets():
    explore = subagent.toolset("explore")
    worker = subagent.toolset("worker")
    assert "read_file" in explore and "write_file" not in explore
    assert "write_file" in worker
    assert not ({"delegate", "delegate_parallel", "schedule_task"} & worker)


def test_delegate_outside_run_is_rejected():
    assert subagent.delegate("x").startswith("Error: delegate 只能在一次 run() 里调用")
