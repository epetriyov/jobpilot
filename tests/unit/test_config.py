"""[F-U1] Конфиг без обязательной переменной → понятная ошибка с её именем, сервис не стартует."""

from pathlib import Path

import pytest

from app.config import ConfigError, Settings

REQUIRED = {
    "TELEGRAM_API_TOKEN": "123456:test-telegram-token",
    "OWNER_CHAT_ID": "100500",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "POSTGRES_DSN": "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot",
}


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)


def test_full_config_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)

    settings = Settings.load(env_file=None)

    assert settings.owner_chat_id == 100500
    assert settings.dry_run is True  # DRY_RUN по умолчанию включён
    assert settings.llm_model_scoring == "google/gemini-2.5-flash-lite"


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_missing_required_var_names_it(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        if name != missing:
            monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError) as exc_info:
        Settings.load(env_file=None)

    assert missing in str(exc_info.value)


def test_hh_settings_optional_and_secret(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Этап 1 (пересмотр): HH-источники опциональны (сервис стартует без доступа);
    userbot api_hash попадает в secret_values() → санитайзер логов ([X-U1])."""
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for name in ("HH_MODE", "HH_USERBOT_API_ID", "HH_USERBOT_API_HASH", "HH_RESUME_URL"):
        monkeypatch.delenv(name, raising=False)
    # изоляция от реального браузер-профиля (несуществующий путь → нет web-доступа)
    monkeypatch.setenv("HH_WEB_PROFILE_DIR", str(tmp_path / "no_profile"))

    settings = Settings.load(env_file=None)
    assert settings.resolved_hh_mode() == "fake"  # без доступа — моки
    assert settings.hh_sources == ["telegram", "web"]

    monkeypatch.setenv("HH_USERBOT_API_ID", "123456")
    monkeypatch.setenv("HH_USERBOT_API_HASH", "hh-userbot-hash-value")
    settings = Settings.load(env_file=None)

    assert settings.resolved_hh_mode() == "real"  # есть доступ к userbot
    assert "hh-userbot-hash-value" in settings.secret_values()


def test_gmail_settings_optional_and_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Этап 2 [X-U1]: Gmail-переменные опциональны; секреты — в санитайзер; режим auto→fake."""
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for name in ("GMAIL_MODE", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.load(env_file=None)
    assert settings.resolved_gmail_mode() == "fake"  # без кредов — мок-корпус

    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "gmail-secret-value")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "gmail-refresh-value")
    monkeypatch.setenv("MAIL_WHITELIST_DOMAINS", "corp.example.com;jobs.example.org")
    settings = Settings.load(env_file=None)

    assert settings.resolved_gmail_mode() == "real"
    assert settings.mail_whitelist_domains == ("corp.example.com", "jobs.example.org")
    secrets = settings.secret_values()
    assert "gmail-secret-value" in secrets
    assert "gmail-refresh-value" in secrets


def test_grafana_cloud_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Телеметрия в облако опциональна: без кредов сервис стартует (contracts/env.md)."""
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GRAFANA_CLOUD_OTLP_ENDPOINT", raising=False)

    settings = Settings.load(env_file=None)

    assert settings.grafana_cloud_otlp_endpoint is None
