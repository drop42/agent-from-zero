"""EP06：Telegram 渠道（长轮询，不需要公网 IP，只用标准库）。"""

from __future__ import annotations

import json
import urllib.request

MAX_LEN = 4000  # Telegram 单条上限 4096，留点余量


class Telegram:
    def __init__(self, token: str, timeout: int = 30):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.timeout = timeout
        self.offset = 0
        self.pending: list[tuple[int, int, str]] = []  # 等待确认期间收到的"别的消息"

    def _call(self, method: str, **params):
        req = urllib.request.Request(
            self.base + method,
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout + 10) as r:
            body = json.loads(r.read())
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API 错误：{body}")
        return body["result"]

    def fetch(self, timeout=None) -> list[tuple[int, int, str]]:
        """只拉新消息。返回 [(chat_id, user_id, text)]，只要私聊文本。"""
        updates = self._call(
            "getUpdates",
            offset=self.offset,
            timeout=self.timeout if timeout is None else timeout,
        )
        out = []
        for u in updates:
            self.offset = u["update_id"] + 1  # 确认已收到，下次不再返回
            m = u.get("message")
            if m and "text" in m and m["chat"]["type"] == "private":
                out.append((m["chat"]["id"], m["from"]["id"], m["text"]))
        return out

    def poll(self, timeout=None) -> list[tuple[int, int, str]]:
        """先交出积压的消息，没有积压再去拉新的。"""
        if self.pending:
            out, self.pending = self.pending, []
            return out
        return self.fetch(timeout)

    def send(self, chat_id: int, text: str) -> None:
        text = text or "（空回复）"
        for i in range(0, len(text), MAX_LEN):
            self._call("sendMessage", chat_id=chat_id, text=text[i : i + MAX_LEN])
