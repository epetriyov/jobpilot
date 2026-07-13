"""[F-U1] Конфиг без обязательной переменной → понятная ошибка с её именем, сервис не стартует."""

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


def test_hh_settings_optional_and_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Этап 1: HH-переменные опциональны (сервис стартует без них);
    заданные HH-секреты попадают в secret_values() → санитайзер логов ([X-U1])."""
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for name in ("HH_CLIENT_ID", "HH_CLIENT_SECRET", "HH_REFRESH_TOKEN", "HH_RESUME_ID"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.load(env_file=None)
    assert settings.hh_client_id is None  # без HH-кредов старт не блокируется

    monkeypatch.setenv("HH_CLIENT_ID", "app-id-1")
    monkeypatch.setenv("HH_CLIENT_SECRET", "hh-secret-value")
    monkeypatch.setenv("HH_REFRESH_TOKEN", "hh-refresh-value")
    monkeypatch.setenv("HH_RESUME_ID", "resume-42")
    settings = Settings.load(env_file=None)

    assert settings.hh_client_id == "app-id-1"
    assert settings.hh_search_queries[0] == "Engineering Manager"
    secrets = settings.secret_values()
    assert "hh-secret-value" in secrets
    assert "hh-refresh-value" in secrets


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
