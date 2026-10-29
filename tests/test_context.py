"""EP04：上下文管理的测试 —— 截断、清理、压缩切点、会话落盘位置。"""

from agent_from_zero.context import (
    PLACEHOLDER,
    SESSION_DIR,
    check_pairing,
    clear_old_tool_results,
    load_session,
    save_session,
    split_for_compact,
    truncate_tool_result,
)
from agent_from_zero.permissions import WORKSPACE


def test_truncate_keeps_head_and_tail():
    text = "x" * 10000
    out = truncate_tool_result(text)
    assert len(out) < 4200
    assert "省略" in out
    assert out.startswith("x") and out.endswith("x")
    assert truncate_tool_result("short") == "short"


def test_clear_replaces_content_but_keeps_messages():
    messages = [{"role": "system", "content": "s"}]
    for i in range(5):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": f"c{i}", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"big{i}"})

    before = len(messages)
    clear_old_tool_results(messages, keep=3)

    assert len(messages) == before  # 只改内容，不删消息
    tools = [m for m in messages if m["role"] == "tool"]
    assert [m["content"] for m in tools] == [
        PLACEHOLDER,
        PLACEHOLDER,
        "big2",
        "big3",
        "big4",
    ]
    check_pairing(messages)


def test_split_only_cuts_at_user_messages():
    messages = [{"role": "system", "content": "s"}]
    for i in range(4):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": f"c{i}", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"r{i}"})
    messages.append({"role": "assistant", "content": "done"})

    parts = split_for_compact(messages, keep_turns=2)
    assert parts is not None
    old, recent = parts

    assert old[0]["role"] == "user" and old[0]["content"] == "u0"
    assert recent[0]["role"] == "user" and recent[0]["content"] == "u2"
    # 切点两侧各自都不产生孤立的 tool 消息
    check_pairing([messages[0], *old])
    check_pairing(recent)


def test_no_split_when_few_turns():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a0"},
    ]
    assert split_for_compact(messages, keep_turns=2) is None


def test_session_file_lives_outside_workspace():
    assert not SESSION_DIR.is_relative_to(WORKSPACE)
    save_session("unit", [{"role": "user", "content": "hi"}])
    assert load_session("unit") == [{"role": "user", "content": "hi"}]
    assert load_session("missing") is None
