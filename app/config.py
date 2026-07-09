"""Конфигурация JobPilot ([F-U1], contracts/env.md).

Секреты — только из окружения; отсутствие обязательной переменной —
понятная ошибка с её именем при старте, сервис не запускается.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Невалидная конфигурация: в сообщении — имена отсутствующих переменных."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- обязательные ---
    telegram_api_token: SecretStr = Field(alias="TELEGRAM_API_TOKEN")
    owner_chat_id: int = Field(alias="OWNER_CHAT_ID")
    openrouter_api_key: SecretStr = Field(alias="OPENROUTER_API_KEY")
    postgres_dsn: SecretStr = Field(alias="POSTGRES_DSN")

    # --- телеметрия в облако (опциональна: без неё телеметрия только локальная) ---
    grafana_cloud_otlp_endpoint: str | None = Field(None, alias="GRAFANA_CLOUD_OTLP_ENDPOINT")
    grafana_cloud_instance_id: str | None = Field(None, alias="GRAFANA_CLOUD_INSTANCE_ID")
    grafana_cloud_api_token: SecretStr | None = Field(None, alias="GRAFANA_CLOUD_API_TOKEN")

    # --- поведение ---
    dry_run: bool = Field(True, alias="DRY_RUN")
    tz_scheduler: str = Field("Europe/Moscow", alias="TZ_SCHEDULER")
    digest_score_threshold: int = Field(60, alias="DIGEST_SCORE_THRESHOLD")
    digest_max_items: int = Field(50, alias="DIGEST_MAX_ITEMS")

    # --- HH (этап 1; опциональны — без них HH-функции не активируются) ---
    hh_client_id: str | None = Field(None, alias="HH_CLIENT_ID")
    hh_client_secret: SecretStr | None = Field(None, alias="HH_CLIENT_SECRET")
    hh_refresh_token: SecretStr | None = Field(None, alias="HH_REFRESH_TOKEN")
    hh_resume_id: str | None = Field(None, alias="HH_RESUME_ID")
    hh_user_agent: str = Field("JobPilot/0.1 (jobpilot-owner)", alias="HH_USER_AGENT")
    hh_search_queries_raw: str = Field(
        "Engineering Manager;Head of Engineering;Руководитель разработки",
        alias="HH_SEARCH_QUERIES",
    )
    hh_search_pages: int = Field(2, alias="HH_SEARCH_PAGES")
    hh_request_pause_sec: float = Field(0.5, alias="HH_REQUEST_PAUSE_SEC")
    publish_interval_hours: int = Field(4, alias="PUBLISH_INTERVAL_HOURS")
    digest_cron: str = Field("0 10 * * *", alias="DIGEST_CRON")
    fewshot_limit: int = Field(10, alias="FEWSHOT_LIMIT")
    fewshot_text_limit: int = Field(800, alias="FEWSHOT_TEXT_LIMIT")

    @property
    def hh_search_queries(self) -> list[str]:
        return [q.strip() for q in self.hh_search_queries_raw.split(";") if q.strip()]

    # --- LLM (модели per-purpose — свап без кода, PLAN.md §2) ---
    llm_base_url: str = Field("https://openrouter.ai/api/v1", alias="LLM_BASE_URL")
    llm_model_scoring: str = Field("google/gemini-2.5-flash-lite", alias="LLM_MODEL_SCORING")
    llm_model_summary: str = Field("google/gemini-2.5-flash-lite", alias="LLM_MODEL_SUMMARY")
    llm_model_letters: str = Field("google/gemini-2.5-pro", alias="LLM_MODEL_LETTERS")
    llm_model_judge: str = Field("google/gemini-2.5-flash", alias="LLM_MODEL_JUDGE")
    price_per_mtok_in: float = Field(0.10, alias="PRICE_PER_MTOK_IN")
    price_per_mtok_out: float = Field(0.40, alias="PRICE_PER_MTOK_OUT")

    # --- observability ---
    otel_exporter_otlp_endpoint: str = Field(
        "http://alloy:4317", alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )

    @classmethod
    def load(cls, env_file: str | None = ".env") -> Settings:
        """Загрузить конфиг; при отсутствии обязательных переменных — ConfigError с именами."""
        try:
            return cls(_env_file=env_file)
        except ValidationError as exc:
            missing = [str(error["loc"][0]) for error in exc.errors() if error["type"] == "missing"]
            if missing:
                raise ConfigError(
                    "Отсутствуют обязательные переменные окружения: " + ", ".join(missing)
                ) from exc
            raise ConfigError(f"Невалидная конфигурация: {exc}") from exc

    def secret_values(self) -> list[str]:
        """Значения всех секретов — для санитайзера логов ([X-U1])."""
        secrets = [
            self.telegram_api_token,
            self.openrouter_api_key,
            self.postgres_dsn,
            self.grafana_cloud_api_token,
            self.hh_client_secret,
            self.hh_refresh_token,
        ]
        return [s.get_secret_value() for s in secrets if s is not None]
