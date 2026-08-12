"""[T401][F-U1] Конфиг источника GetMatch: off-by-default, режимы, guardrail 1 rps.

Источник выключен по умолчанию (`SOURCES=email`, `GETMATCH_MODE=fake`); включается
осознанно (`SOURCES=...,getmatch` + `GETMATCH_MODE=real|auto`). Секретов нет
(публичный фид). Пауза между страницами не опускается ниже 1 c (вежливость,
scraping-risks.md).
"""

from __future__ import annotations

import pytest

from app.config import ConfigError, Settings

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test",
    "POSTGRES_DSN": "postgresql+psycopg://u:p@localhost:5432/db",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for key in ("SOURCES", "GETMATCH_MODE", "GETMATCH_REQUEST_PAUSE_SEC"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings.load(env_file=None)


def test_getmatch_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    assert settings.sources == ["email"]  # getmatch отсутствует
    assert "getmatch" not in settings.sources
    assert settings.resolved_getmatch_mode() == "fake"  # выключен → стаб/нет сети


def test_getmatch_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    assert settings.getmatch_api_url == "https://getmatch.ru/api/offers"
    assert settings.getmatch_page_limit == 20
    assert settings.getmatch_request_pause_sec == 1.0
    assert "JobPilot" in settings.getmatch_user_agent


def test_getmatch_auto_mode_follows_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, SOURCES="email,getmatch", GETMATCH_MODE="auto")
    assert settings.sources == ["email", "getmatch"]
    assert settings.resolved_getmatch_mode() == "real"  # включён в SOURCES → real


def test_getmatch_explicit_real_and_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, GETMATCH_MODE="real").resolved_getmatch_mode() == "real"
    assert (
        _settings(
            monkeypatch, SOURCES="email,getmatch", GETMATCH_MODE="fake"
        ).resolved_getmatch_mode()
        == "fake"
    )


def test_getmatch_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    # публичный фид — секретов у источника нет (contracts/env.md).
    settings = _settings(monkeypatch, SOURCES="email,getmatch", GETMATCH_MODE="real")
    assert settings.secret_values()  # чужие секреты есть, но getmatch их не добавляет
    assert settings.getmatch_user_agent not in settings.secret_values()


def test_getmatch_pause_below_one_second_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError):
        _settings(monkeypatch, GETMATCH_REQUEST_PAUSE_SEC="0.2")
