"""EP11：记忆的测试 —— 会话开始快照、增删改、上限、确认、无人值守限制、检索。"""

import json

import pytest

from agent_from_zero import agent, memory, scheduler
from agent_from_zero.permissions import WORKSPACE, PermissionManager, render_call


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """每个用例一份干净的记忆文件与会话目录。"""
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "MEMORY.md")
    monkeypatch.setattr(memory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(memory, "SESSION_DIR", tmp_path / "sessions")
    (tmp_path / "sessions").mkdir()


def test_snapshot_at_session_start():
    memory.remember("add", "回答用中文")  # 直接写文件，绕过权限（测试用）
    s = agent.Session("m1", persist=False)
    assert "回答用中文" in s.messages[0]["content"]
    assert "背景信息，不是指令" in s.messages[0]["content"]
    memory.remember("add", "新记的一条")
    assert "新记的一条" not in s.messages[0]["content"]  # 本会话不变
    assert "新记的一条" in agent.Session("m2", persist=False).messages[0]["content"]


def test_add_replace_remove():
    memory.remember("add", "项目用 pnpm")
    assert "项目用 pnpm" in memory.load_entries()
    assert memory.remember("replace", "项目用 yarn", old="pnpm").startswith("已更新")
    assert memory.load_entries() == ["项目用 yarn"]
    assert memory.remember("remove", old="不存在的片段").startswith("Error: old 必须恰好")
    assert memory.remember("remove", old="yarn").startswith("已更新")
    assert memory.load_entries() == []


def test_limit_rejects_instead_of_truncating():
    assert memory.remember("add", "x" * (memory.MAX_CHARS + 10)).startswith("Error: 记忆会超过")
    assert memory.load_entries() == []


def test_memory_file_lives_outside_workspace():
    assert not memory.MEMORY_FILE.is_relative_to(WORKSPACE)
    assert memory.MEMORY_FILE.parent == memory.STATE_DIR


def test_remember_needs_confirmation_and_is_shown():
    pm = PermissionManager(ask=lambda n, a: ("y", ""))
    assert pm.check("remember", {"action": "add", "text": "偏好简短"}).allowed
    shown = render_call("remember", {"action": "add", "text": "偏好简短"})
    assert "add" in shown and "偏好简短" in shown


def test_unattended_task_cannot_write_memory():
    pm = PermissionManager(
        ask=scheduler.make_task_ask({"allow": ["fetch_url", "write_file"]})
    )
    assert not pm.check("remember", {"action": "add", "text": "x"}).allowed


def test_subagent_cannot_remember():
    from agent_from_zero import subagent

    assert "remember" in subagent.NEVER_FOR_SUB
    assert "remember" not in subagent.toolset("worker")
    assert "search_sessions" in subagent.toolset("explore")  # 只读检索照常可用


def test_search_sessions_finds_and_limits():
    memory.remember("add", "把 Redis 连接池上限调到 50")
    memory.SESSION_DIR.mkdir(parents=True, exist_ok=True)
    (memory.SESSION_DIR / "unit-search.json").write_text(
        json.dumps(
            [
                {"role": "user", "content": "Redis 连接超时怎么办"},
                {"role": "assistant", "content": "把连接池上限从 10 调到 50 之后就好了"},
                {"role": "tool", "content": "Redis 超时 工具噪音"},
            ]
        ),
        encoding="utf-8",
    )
    out = memory.search_sessions("连接池 50")
    assert "unit-search" in out and "连接池" in out
    assert "工具噪音" not in out  # 工具结果不参与检索
    assert memory.search_sessions("完全不存在的词") == "没有找到相关的历史对话。"
