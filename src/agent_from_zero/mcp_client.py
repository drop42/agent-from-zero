"""EP08：MCP 客户端 —— 不装 SDK，用标准库把协议写一遍。

MCP 把"工具的执行"标准化：工具跑在另一个进程里，Agent 通过 JSON-RPC
问它有哪些工具、请它执行。客户端的本质是翻译：把 tools/list 的结果翻译进注册表。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading

from .context import STATE_DIR  # 配置放在工作区之外：command 是一条会被执行的命令
from .permissions import TOOL_RISK, Risk
from .tools import TOOLS

PROTOCOL_VERSION = "2025-11-25"
TIMEOUT = 30  # 读一行的超时（秒）
CONFIG_FILE = STATE_DIR / "mcp.json"

SERVERS: dict[str, "MCPServer"] = {}


class MCPError(RuntimeError):
    pass


class MCPServer:
    """一个 MCP 服务器进程，以及和它说话的方法。"""

    def __init__(self, name: str, command: str, args=(), env=None):
        self.name = name
        self.proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # 服务器的日志走 stderr，这里直接丢掉
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, **(env or {})},
        )
        self.next_id = 0
        self.lock = threading.Lock()  # 子 Agent 可能并发调用

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")  # 一条消息一行
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None):
        with self.lock:
            self.next_id += 1
            rid = self.next_id
            self._send(
                {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            )
            while True:
                line = self._readline()
                msg = json.loads(line)
                if msg.get("id") != rid:  # 服务器主动发来的通知，这一版先忽略
                    continue
                if "error" in msg:
                    raise MCPError(
                        f"{msg['error'].get('code')}: {msg['error'].get('message')}"
                    )
                return msg["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        with self.lock:
            self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _readline(self) -> str:
        result: list[str] = []
        t = threading.Thread(target=lambda: result.append(self.proc.stdout.readline()))
        t.start()
        t.join(TIMEOUT)
        if not result or not result[0]:
            raise MCPError(f"MCP 服务器 {self.name} 没有响应或已退出")
        return result[0]

    # ---------- 三个动作 ----------
    def initialize(self) -> dict:
        info = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "nami-agent", "version": "0.8"},
            },
        )
        self.notify("notifications/initialized")
        return info

    def list_tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:  # 工具多时会分页
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += result.get("tools", [])
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, tool: str, arguments: dict) -> str:
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        parts = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block["text"])
            else:  # 图片、音频等，这一版只告诉模型有这么个东西
                parts.append(f"[{block.get('type')} 内容，已省略]")
        text = "\n".join(parts) or "(空结果)"
        return f"Error: {text}" if result.get("isError") else text


def register_server(server: MCPServer, safe=()) -> None:
    """把一个服务器的全部工具注册成 mcp__服务器__工具。"""
    for t in server.list_tools():
        full = f"mcp__{server.name}__{t['name']}"
        desc = (t.get("description") or "")[:1000]  # 描述也是提示词，限个长度
        TOOLS[full] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": full,
                    "description": f"[MCP:{server.name}] {desc}",
                    "parameters": t.get("inputSchema")
                    or {"type": "object", "properties": {}},
                },
            },
            # 默认参数防止闭包串味：不这么写，所有 lambda 都会指向最后一个工具
            "func": lambda _s=server, _t=t["name"], **args: _s.call_tool(_t, args),
        }
        # 默认不登记风险 = 按 CONFIRM 处理；只读的工具要在配置里点名
        if t["name"] in safe:
            TOOL_RISK[full] = Risk.SAFE
    SERVERS[server.name] = server


def load_servers(config_file=CONFIG_FILE, log=print) -> None:
    """读取 mcp.json，启动并注册里面的每个服务器。"""
    if not config_file.exists():
        return
    config = json.loads(config_file.read_text(encoding="utf-8"))
    for name, spec in config.get("servers", {}).items():
        try:
            s = MCPServer(name, spec["command"], spec.get("args", []), spec.get("env"))
            s.initialize()
            register_server(s, safe=set(spec.get("safe_tools", [])))
            log(
                f"[MCP] {name}：已接入 "
                f"{sum(k.startswith(f'mcp__{name}__') for k in TOOLS)} 个工具"
            )
        except Exception as e:  # 一个服务器起不来，不影响其他的
            log(f"[MCP] {name} 启动失败：{e}")
