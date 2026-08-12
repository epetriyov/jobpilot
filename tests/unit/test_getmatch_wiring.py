"""[T409] Композиция GetMatch: off-by-default; fake-стаб/real-httpx по конфигу.

Источник не собирается, пока getmatch не добавлен в SOURCES (constitution VI).
Включён + fake → детерминированный стаб (сеть не трогается, CI). Включён + real →
GetMatchSource поверх httpx-клиента. Падение источника изолируется в дайджесте (S4)
общим механизмом коллектора — тут проверяем только регистрацию по флагу.
"""

from __future__ import annotations

import pytest

from app.adapters.getmatch.fake import FakeGetMatchSource
from app.adapters.getmatch.source import GetMatchSource
from app.config import Settings
from app.runtime.composition import build_getmatch_sources

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test",
    "POSTGRES_DSN": "postgresql+psycopg://u:p@localhost:5432/db",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for key in ("SOURCES", "GETMATCH_MODE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings.load(env_file=None)


def test_disabled_by_default_yields_no_source(monkeypatch: pytest.MonkeyPatch) -> None:
    assert build_getmatch_sources(_settings(monkeypatch)) == []


def test_enabled_fake_uses_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = build_getmatch_sources(
        _settings(monkeypatch, SOURCES="email,getmatch", GETMATCH_MODE="fake")
    )
    assert len(sources) == 1
    assert isinstance(sources[0], FakeGetMatchSource)
    assert sources[0].name == "getmatch"


def test_enabled_real_uses_httpx_source(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = build_getmatch_sources(
        _settings(monkeypatch, SOURCES="email,getmatch", GETMATCH_MODE="real")
    )
    assert len(sources) == 1
    assert isinstance(sources[0], GetMatchSource)
    assert sources[0].name == "getmatch"


def test_in_sources_but_mode_fake_stays_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # getmatch в SOURCES, но GETMATCH_MODE=fake → стаб (canary без сети).
    sources = build_getmatch_sources(
        _settings(monkeypatch, SOURCES="email,getmatch", GETMATCH_MODE="fake")
    )
    assert isinstance(sources[0], FakeGetMatchSource)


async def test_fake_source_returns_getmatch_vacancies(monkeypatch: pytest.MonkeyPatch) -> None:
    source = FakeGetMatchSource()
    vacancies = await source.fetch()
    assert vacancies, "стаб обязан вернуть детерминированные вакансии"
    assert all(v.source_ref.source == "getmatch" for v in vacancies)
    assert all(v.url.startswith("https://getmatch.ru/") for v in vacancies)
