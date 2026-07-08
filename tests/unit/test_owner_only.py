"""[F-U2] Чужой chat_id → молчаливый игнор + warning; бот отвечает только владельцу."""

import io

import pytest
import structlog

from app.bot.middleware import OwnerOnlyMiddleware
from app.obs.logging import configure_logging

OWNER = 100500
STRANGER = 999


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class FakeMessage:
    def __init__(self, chat_id: int) -> None:
        self.chat = FakeChat(chat_id)


@pytest.fixture()
def log_output() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(secret_values=[], stream=stream)
    yield stream
    structlog.reset_defaults()


async def test_owner_passes_through() -> None:
    mw = OwnerOnlyMiddleware(owner_chat_id=OWNER)
    called = {"n": 0}

    async def handler(event: object, data: dict) -> str:
        called["n"] += 1
        return "handled"

    result = await mw(handler, FakeMessage(OWNER), {})

    assert result == "handled"
    assert called["n"] == 1


async def test_stranger_is_silently_ignored(log_output: io.StringIO) -> None:
    mw = OwnerOnlyMiddleware(owner_chat_id=OWNER)
    called = {"n": 0}

    async def handler(event: object, data: dict) -> str:
        called["n"] += 1
        return "handled"

    result = await mw(handler, FakeMessage(STRANGER), {})

    assert result is None  # молчаливый игнор — хендлер не вызван
    assert called["n"] == 0
    text = log_output.getvalue()
    assert "foreign_chat_ignored" in text
    assert '"level": "warning"' in text
