"""EP06：渠道相关测试 —— 聊天确认、白名单、出错回滚。全部用假渠道 / 假客户端。"""

from unittest.mock import MagicMock

from agent_from_zero import bot
from agent_from_zero.bot import handle_message, make_chat_ask
from agent_from_zero.telegram import Telegram


class FakeChannel:
    def __init__(self, incoming=()):
        self.incoming = list(incoming)
        self.sent = []
        self.pending = []

    def fetch(self, timeout=None):
        return [self.incoming.pop(0)] if self.incoming else []

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_chat_ask_with_reason_and_buffer():
    ch = FakeChannel([(1, 1, "顺便问个问题"), (2, 2, "别的人"), (1, 1, "n 先列出来")])
    ask = make_chat_ask(ch, 1, wait=5)
    assert ask("run_shell", {"command": "rm a"}) == ("n", "先列出来")
    # 不是确认回复的消息都被留下来，没有丢、也没有被当成确认
    assert ch.pending == [(1, 1, "顺便问个问题"), (2, 2, "别的人")]
    # run_shell 不提供"一直允许"
    assert "a 本会话一直允许" not in ch.sent[0][1]


def test_chat_ask_timeout():
    ask = make_chat_ask(FakeChannel(), 1, wait=1)
    assert ask("run_shell", {"command": "ls"}) == ("n", "确认超时")


def test_whitelist_blocks_and_stays_silent():
    ch = FakeChannel()
    bot.ALLOWED = {1}
    sessions = {}
    handle_message(ch, MagicMock(), sessions, chat_id=99, user_id=99, text="你好")
    assert ch.sent == []
    assert sessions == {}


def test_rollback_on_client_failure():
    ch = FakeChannel()
    bot.ALLOWED = {1}

    call = MagicMock(id="c1")
    call.function.name = "list_dir"
    call.function.arguments = '{"path": "."}'
    msg = MagicMock(content=None, tool_calls=[call])
    msg.model_dump.return_value = {"role": "assistant", "tool_calls": []}

    ok = MagicMock()
    ok.choices = [MagicMock(message=msg)]
    ok.usage = MagicMock(prompt_tokens=10)

    client = MagicMock()
    client.chat.completions.create.side_effect = [ok, ConnectionError("断网了")]

    sessions = {}
    handle_message(ch, client, sessions, chat_id=1, user_id=1, text="列目录")

    s = sessions[1]
    # 整轮撤销：只剩 system
    assert [m["role"] for m in s.messages] == ["system"]
    assert ch.sent[-1][1].startswith("[出错，本轮已撤销] ConnectionError")


def test_telegram_parses_updates_and_advances_offset():
    tg = Telegram("token")
    tg._call = MagicMock(
        return_value=[
            {
                "update_id": 7,
                "message": {
                    "message_id": 1,
                    "text": "hi",
                    "chat": {"id": 5, "type": "private"},
                    "from": {"id": 5},
                },
            },
            {
                "update_id": 8,
                "message": {
                    "message_id": 2,
                    "text": "group msg",
                    "chat": {"id": -100, "type": "group"},
                    "from": {"id": 6},
                },
            },
        ]
    )
    assert tg.fetch() == [(5, 5, "hi")]  # 只取私聊
    assert tg.offset == 9
    tg.pending.append((5, 5, "queued"))
    assert tg.poll() == [(5, 5, "queued")]  # 先交积压，不再拉新
