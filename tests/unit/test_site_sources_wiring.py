"""[T507] Композиция: активные+canary сайты подключаются по конфигу; пропуск незарег.

Реестр пуст в фундаменте (off-by-default) → источников сайтов нет. По-сайтовые
задачи регистрируют фабрики; незарегистрированный сайт пропускается с warning —
не роняет сбор из остальных (S4).
"""

from __future__ import annotations

import pytest

from app.adapters.sites.base import SiteAdapter
from app.config import Settings
from app.runtime.composition import build_site_sources

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test",
    "POSTGRES_DSN": "postgresql+psycopg://u:p@localhost:5432/db",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **sites: str) -> Settings:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for key in ("SITES_ACTIVE", "SITES_CANARY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in sites.items():
        monkeypatch.setenv(key, value)
    return Settings.load(env_file=None)


class FakeTransport:
    async def fetch(self) -> str:
        return "<html/>"


def _factory(settings: Settings, escalate: object) -> SiteAdapter:
    return SiteAdapter(
        site_name="yandex",
        transport=FakeTransport(),  # type: ignore[arg-type]
        parse_fn=lambda _: [],
        keywords=[],
    )


def test_empty_registry_yields_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, SITES_CANARY="yandex;vk")
    assert build_site_sources(settings, registry={}) == []


def test_registered_site_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, SITES_CANARY="yandex")
    sources = build_site_sources(settings, registry={"yandex": _factory})
    assert [s.name for s in sources] == ["yandex"]


def test_unregistered_site_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, SITES_ACTIVE="sber", SITES_CANARY="yandex")
    # только yandex зарегистрирован → sber пропущен, yandex собран
    sources = build_site_sources(settings, registry={"yandex": _factory})
    assert [s.name for s in sources] == ["yandex"]


def test_active_and_canary_union_deduped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, SITES_ACTIVE="yandex", SITES_CANARY="yandex")
    sources = build_site_sources(settings, registry={"yandex": _factory})
    assert len(sources) == 1  # один и тот же сайт не дублируется
