"""EP10：计划的测试 —— 计划模式由代码强制、清单只留最新一版、子 Agent 继承。"""

from agent_from_zero import agent, planning
from agent_from_zero.permissions import PermissionManager


def test_plan_mode_blocks_writes_even_if_user_says_yes():
    pm = PermissionManager(ask=lambda n, a: ("a", ""))
    pm.check("write_file", {"path": "x.txt", "content": ""})  # 先"一直允许"写文件
    pm.mode = "plan"
    assert not pm.check("write_file", {"path": "x.txt", "content": ""}).allowed
    assert not pm.check("run_shell", {"command": "ls"}).allowed
    assert pm.check("read_file", {"path": "x.txt"}).allowed  # 读照常
    assert pm.check("submit_plan", {"plan": "1. ..."}).allowed  # 提交计划要问人，这里人说了 a


def test_plan_mode_denial_does_not_ask():
    asked = []
    pm = PermissionManager(ask=lambda n, a: (asked.append(n), ("y", ""))[1])
    pm.mode = "plan"
    d = pm.check("write_file", {"path": "x.txt", "content": ""})
    assert not d.allowed and asked == [] and "计划模式" in d.reason


def test_update_plan_validates_and_keeps_latest():
    s = agent.Session("plan-test", persist=False)
    token = agent.CURRENT.set((s, None, "m", print))
    try:
        assert planning.update_plan([]).startswith("Error")
        assert planning.update_plan([{"step": "a", "status": "bad"}]).startswith("Error")
        assert planning.update_plan(
            [
                {"step": "a", "status": "in_progress"},
                {"step": "b", "status": "in_progress"},
            ]
        ).startswith("Error")
        first = planning.update_plan([{"step": "第一步", "status": "in_progress"}])
        assert first.startswith("[plan]") and "0/1 完成" in first
        s.messages.append({"role": "tool", "tool_call_id": "t", "content": first})
        second = planning.update_plan([{"step": "第一步", "status": "completed"}])
        assert "1/1 完成" in second
        assert s.messages[-1]["content"] == planning.OLD_PLAN  # 旧版被替换
        assert s.plan == [{"step": "第一步", "status": "completed"}]
    finally:
        agent.CURRENT.reset(token)


def test_submit_plan_requires_plan_mode_and_approval():
    s = agent.Session("submit-test", ask=lambda n, a: ("y", ""), persist=False)
    token = agent.CURRENT.set((s, None, "m", print))
    try:
        assert planning.submit_plan("x").startswith("Error: 当前不在计划模式")
        s.perms.mode = "plan"
        out = planning.submit_plan("1. 改 scheduler.py")
        assert "批准" in out and s.perms.mode == "normal"
    finally:
        agent.CURRENT.reset(token)


def test_render_call_shows_whole_plan():
    from agent_from_zero.permissions import render_call

    text = render_call("submit_plan", {"plan": "1. 做这个\n2. 做那个"})
    assert "1. 做这个" in text and "2. 做那个" in text


def test_subagent_inherits_plan_mode():
    parent = agent.Session("main", ask=lambda n, a: ("y", ""), persist=False)
    parent.perms.mode = "plan"
    token = agent.CURRENT.set((parent, None, "m", print))
    try:
        from agent_from_zero import subagent

        assert "submit_plan" in subagent.NEVER_FOR_SUB
    finally:
        agent.CURRENT.reset(token)
