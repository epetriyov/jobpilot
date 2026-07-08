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


def test_grafana_cloud_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Телеметрия в облако опциональна: без кредов сервис стартует (contracts/env.md)."""
    _clear_env(monkeypatch)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GRAFANA_CLOUD_OTLP_ENDPOINT", raising=False)

    settings = Settings.load(env_file=None)

    assert settings.grafana_cloud_otlp_endpoint is None
