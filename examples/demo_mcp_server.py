"""示例 MCP 服务器（只用标准库，约 50 行）。

写法：一行一条 JSON-RPC 消息，日志只能写 stderr。
并用它自测第 8 课的客户端：
    python examples/demo_mcp_server.py
"""

import json
import sys
from datetime import datetime

TOOLS = [
    {
        "name": "now",
        "description": "返回当前本地时间（ISO 8601）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "word_count",
        "description": "统计一段文字的字符数和行数。",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "要统计的文字"}},
            "required": ["text"],
        },
    },
]


def text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}], "isError": False}


def handle(msg: dict) -> dict:
    method = msg.get("method")
    params = msg.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-11-25"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "demo", "version": "1.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "now":
            return text(datetime.now().isoformat(timespec="seconds"))
        if name == "word_count":
            body = str(args.get("text", ""))
            if not body:
                # 工具自己出错：照常返回 result，只是 isError 为 true
                return {"content": [{"type": "text", "text": "text 不能为空"}], "isError": True}
            return text(f"{len(body)} 个字符，{body.count(chr(10)) + 1} 行")
        return {"content": [{"type": "text", "text": f"未知工具 {name}"}], "isError": True}
    raise KeyError(method)


def main() -> None:
    for line in sys.stdin:  # 一行一条消息
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if "id" not in msg:  # 通知（比如 notifications/initialized）不需要回复
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except KeyError:
            reply = {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32601, "message": f"未知方法 {msg.get('method')}"},
            }
        print(json.dumps(reply, ensure_ascii=False), flush=True)
        print(f"[demo] 处理了 {msg.get('method')}", file=sys.stderr)  # 日志只能写 stderr


if __name__ == "__main__":
    main()
