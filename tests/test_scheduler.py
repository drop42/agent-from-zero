"""EP07：定时任务与心跳的测试 —— 时间规则、不补跑、预授权、无人值守限制。"""

from datetime import datetime, timedelta

import pytest

from agent_from_zero import scheduler
from agent_from_zero.permissions import PermissionManager


def test_next_run():
    t = datetime(2026, 10, 28, 10, 0)
    assert scheduler.next_run("every 30m", t) == t + timedelta(minutes=30)
    assert scheduler.next_run("daily 09:00", t) == datetime(2026, 10, 29, 9, 0)
    assert scheduler.next_run("daily 11:30", t) == datetime(2026, 10, 28, 11, 30)
    for bad in ("every 1m", "daily 25:00", "每天九点"):
        with pytest.raises(ValueError):
            scheduler.next_run(bad, t)


def test_no_catch_up_and_preauth(tmp_path):
    now = [datetime(2026, 10, 28, 8, 0)]
    s = scheduler.Scheduler(tmp_path / "t.json", now=lambda: now[0])
    task = s.add("every 1h", "看看", chat_id=1, allow={"fetch_url"})
    with pytest.raises(ValueError):
        s.add("every 1h", "x", 1, allow={"run_shell"})  # run_shell 不能预授权
    now[0] = datetime(2026, 10, 28, 13, 5)  # 停机 5 小时
    assert len(s.due()) == 1  # 只到期一次，不是五次
    s.mark_started(task)
    assert s.due() == [] and task["next_run"] == "2026-10-28T14:05:00"


def test_task_cannot_schedule_tasks_or_shell():
    pm = PermissionManager(ask=scheduler.make_task_ask({"allow": ["fetch_url"]}))
    assert pm.check("fetch_url", {"url": "https://x"}).allowed  # 预授权过
    assert not pm.check("run_shell", {"command": "ls"}).allowed  # 没有人能确认
    assert not pm.check(
        "schedule_task", {"spec": "every 5m", "prompt": "x"}
    ).allowed
    assert pm.check("read_file", {"path": "a.txt"}).allowed  # SAFE 照常放行


def test_max_tasks_and_remove(tmp_path):
    s = scheduler.Scheduler(tmp_path / "t.json", now=lambda: datetime(2026, 10, 28))
    for i in range(scheduler.MAX_TASKS):
        s.add("every 1h", f"task {i}", chat_id=1)
    with pytest.raises(ValueError):
        s.add("every 1h", "over", chat_id=1)
    tid = s.tasks[0]["id"]
    assert s.remove(tid, chat_id=1) and not s.remove(tid, chat_id=1)


def test_task_input_marks_unattended_and_heartbeat():
    task = {"id": "abc123", "kind": "task", "prompt": "看网页"}
    assert "无人值守" in scheduler.task_input(task)
    hb = {"id": "abc124", "kind": "heartbeat", "prompt": "看目录"}
    out = scheduler.task_input(hb)
    assert scheduler.HEARTBEAT_OK in out and "例行检查" in out


def test_schedule_task_requires_chat_context(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "SCHED", scheduler.Scheduler(tmp_path / "t.json"))
    scheduler.CURRENT["chat_id"] = None
    assert scheduler.schedule_task("every 1h", "x").startswith("Error")
    scheduler.CURRENT["chat_id"] = 7
    msg = scheduler.schedule_task("every 1h", "x", allow="fetch_url")
    assert msg.startswith("已创建任务")
    assert len(scheduler.get_scheduler().tasks) == 1
    scheduler.CURRENT["chat_id"] = None


class _Msg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None

    def model_dump(self, **kw):
        return {"role": "assistant", "content": self.content}


class _Client:
    def __init__(self, content):
        self.content = content
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kw):
        resp = type("R", (), {})()
        resp.choices = [type("Ch", (), {"message": _Msg(self.content)})()]
        resp.usage = type("U", (), {"prompt_tokens": 5})()
        return resp


def test_heartbeat_silent_when_ok(tmp_path, monkeypatch):
    from agent_from_zero import bot

    s = scheduler.Scheduler(tmp_path / "t.json", now=lambda: datetime(2026, 10, 28, 12, 0))
    s.add("every 1h", "检查目录", chat_id=1, kind="heartbeat")
    s.add("every 1h", "总结网页", chat_id=1)
    for t in s.tasks:
        t["next_run"] = "2026-10-28T11:00:00"
    s._save()
    monkeypatch.setattr(scheduler, "SCHED", s)

    sent = []

    class FakeTG:
        def send(self, chat_id, text):
            sent.append((chat_id, text))

    bot.run_due_tasks(FakeTG(), _Client(scheduler.HEARTBEAT_OK))
    # 心跳无事不发消息，普通任务照发
    assert len(sent) == 1 and "总结网页" not in sent[0][1]
