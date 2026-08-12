"""[T501] Конфиг сайтов-скрейперов (contracts/env.md): off-by-default, валидация имён.

Активные/canary/heavy списки, паузы/лимиты (≥1 s), честный UA, EM-ключи — только из env.
Неизвестное имя сайта в любом списке → понятная ошибка конфига ([F-U1]).
"""

from __future__ import annotations

import pytest

from app.config import KNOWN_SITES, ConfigError, Settings

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test-telegram-token",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "POSTGRES_DSN": "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot",
}

SITE_VARS = (
    "SITES_ACTIVE",
    "SITES_CANARY",
    "SITES_HEAVY",
    "SITES_RATE_LIMIT_SEC",
    "SITES_USER_AGENT",
    "SITES_EM_KEYWORDS",
    "SITES_TIMEOUT_SEC",
    "SITES_ROBOTS_RESPECT",
)


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for name in SITE_VARS:
        monkeypatch.delenv(name, raising=False)


def test_known_sites_is_the_seven_portals() -> None:
    assert frozenset({"yandex", "vk", "avito", "tbank", "ozon", "alfa", "sber"}) == KNOWN_SITES


def test_sites_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guardrail (scraping-risks.md): активных сайтов по умолчанию НЕТ."""
    _base_env(monkeypatch)
    s = Settings.load(env_file=None)
    assert s.sites_active == []
    assert s.sites_canary == []
    assert s.sites_heavy == ["ozon"]  # справочный дефолт «тяжёлых»


def test_defaults_polite(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    s = Settings.load(env_file=None)
    assert s.sites_rate_limit_sec >= 1.0  # ≥1 rps
    assert s.sites_timeout_sec > 0
    assert "JobPilot" in s.sites_user_agent  # честный UA с контактом владельца
    assert s.sites_robots_respect is True
    assert "engineering manager" in [k.lower() for k in s.sites_em_keywords]


def test_lists_parse_semicolons(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("SITES_CANARY", "yandex;vk;avito")
    monkeypatch.setenv("SITES_ACTIVE", "sber")
    s = Settings.load(env_file=None)
    assert s.sites_canary == ["yandex", "vk", "avito"]
    assert s.sites_active == ["sber"]


def test_unknown_site_name_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("SITES_CANARY", "yandex;linkedin")
    with pytest.raises(ConfigError) as exc:
        Settings.load(env_file=None)
    assert "linkedin" in str(exc.value)


def test_rate_limit_below_one_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """≥1 rps — жёсткий guardrail вежливости (scraping-risks.md)."""
    _base_env(monkeypatch)
    monkeypatch.setenv("SITES_RATE_LIMIT_SEC", "0.2")
    with pytest.raises(ConfigError):
        Settings.load(env_file=None)
