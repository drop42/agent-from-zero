"""EP08：MCP 客户端的测试 —— 真的启动 demo 服务器进程，不调用模型。"""

import json
import sys
from pathlib import Path

import pytest

from agent_from_zero import mcp_client
from agent_from_zero.context import STATE_DIR
from agent_from_zero.permissions import TOOL_RISK, Risk
from agent_from_zero.tools import TOOLS, execute

DEMO = str(Path(__file__).resolve().parent.parent / "examples" / "demo_mcp_server.py")


@pytest.fixture
def server():
    s = mcp_client.MCPServer("demo", sys.executable, [DEMO])
    s.initialize()
    yield s
    s.proc.kill()


def test_handshake_and_list_tools(server):
    names = {t["name"] for t in server.list_tools()}
    assert names == {"now", "word_count"}


def test_register_and_execute_through_registry(server):
    mcp_client.register_server(server, safe={"now"})
    try:
        assert "mcp__demo__word_count" in TOOLS
        # 通过第 2 课的统一执行器调用，和本地工具没有区别
        out = execute("mcp__demo__word_count", {"text": "你好\n世界"})
        assert out == "5 个字符，2 行"
        assert TOOL_RISK["mcp__demo__now"] is Risk.SAFE
        # 未点名 safe 的工具不登记风险 -> 默认 CONFIRM
        assert "mcp__demo__word_count" not in TOOL_RISK
    finally:
        for k in list(TOOLS):
            if k.startswith("mcp__demo__"):
                TOOLS.pop(k)
        mcp_client.SERVERS.pop("demo", None)


def test_iserror_is_translated(server):
    out = server.call_tool("word_count", {"text": ""})
    assert out.startswith("Error: text 不能为空")


def test_unknown_method_raises(server):
    with pytest.raises(mcp_client.MCPError):
        server.request("no/such/method", {})


def test_bad_server_does_not_block_others(tmp_path, capsys):
    config = {
        "servers": {
            "broken": {"command": "definitely-not-a-real-binary-xyz"},
            "demo": {"command": sys.executable, "args": [DEMO], "safe_tools": ["now"]},
        }
    }
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    logs = []
    mcp_client.load_servers(path, log=logs.append)
    try:
        assert any("broken" in line and "启动失败" in line for line in logs)
        assert any("demo" in line and "已接入" in line for line in logs)
        assert "mcp__demo__now" in TOOLS
    finally:
        for k in list(TOOLS):
            if k.startswith("mcp__demo__"):
                TOOLS.pop(k)
        mcp_client.SERVERS.pop("demo", None)


def test_config_lives_outside_workspace():
    from agent_from_zero.permissions import WORKSPACE

    assert not mcp_client.CONFIG_FILE.parent.is_relative_to(WORKSPACE)
    assert mcp_client.CONFIG_FILE.parent == STATE_DIR
