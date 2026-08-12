"""Конфигурация JobPilot ([F-U1], contracts/env.md).

Секреты — только из окружения; отсутствие обязательной переменной —
понятная ошибка с её именем при старте, сервис не запускается.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Фиксированное множество карьерных порталов этапа 5 (contracts/env.md).
# Любое имя в SITES_* вне этого множества — ошибка конфига ([F-U1]).
KNOWN_SITES: frozenset[str] = frozenset({"yandex", "vk", "avito", "tbank", "ozon", "alfa", "sber"})
# Минимальная пауза между запросами к одному порталу — вежливость ≥1 rps
# (scraping-risks.md guardrail; жёсткий нижний предел, не настраивается вниз).
SITES_MIN_RATE_LIMIT_SEC = 1.0
# Тот же вежливый нижний предел паузы для GetMatch (`/api/offers`, 1 rps).
GETMATCH_MIN_PAUSE_SEC = 1.0


def _split_sites(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(";") if s.strip()]


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

    # --- режимы источников (спека 001: моки до кредов, свап на реальный API конфигом) ---
    hh_mode: Literal["auto", "fake", "real"] = Field("auto", alias="HH_MODE")
    llm_mode: Literal["auto", "fake", "real"] = Field("auto", alias="LLM_MODE")

    # --- Gmail (этап 2; моки до кредов — GMAIL_MODE) ---
    gmail_mode: Literal["auto", "fake", "real"] = Field("auto", alias="GMAIL_MODE")
    gmail_client_id: str | None = Field(None, alias="GMAIL_CLIENT_ID")
    gmail_client_secret: SecretStr | None = Field(None, alias="GMAIL_CLIENT_SECRET")
    gmail_refresh_token: SecretStr | None = Field(None, alias="GMAIL_REFRESH_TOKEN")
    mail_whitelist_domains_raw: str = Field("", alias="MAIL_WHITELIST_DOMAINS")
    mail_body_limit: int = Field(2000, alias="MAIL_BODY_LIMIT")

    # --- LinkedIn-нетворкинг (этап 3; кредов НЕТ по построению — N1) ---
    linkedin_companies_raw: str = Field("", alias="LINKEDIN_COMPANIES")
    linkedin_roles_raw: str = Field("CTO;CPO;HRBP;Senior IT Recruiter", alias="LINKEDIN_ROLES")
    invites_cron: str = Field("0 11 * * 1", alias="INVITES_CRON")
    invites_remind_days: int = Field(3, alias="INVITES_REMIND_DAYS")

    # --- HH (этап 1; пересмотр 2026-07-17: email HH-подписки + userbot + web, API нет) ---
    hh_sources_raw: str = Field("email", alias="HH_SOURCES")
    hh_email_since_hours: int = Field(48, alias="HH_EMAIL_SINCE_HOURS")
    hh_user_agent: str = Field("JobPilot/0.1 (jobpilot-owner)", alias="HH_USER_AGENT")
    hh_request_pause_sec: float = Field(1.0, alias="HH_REQUEST_PAUSE_SEC")
    # userbot (Telethon, второй аккаунт; общий с GetMatch этапа 4)
    hh_userbot_api_id: int | None = Field(None, alias="HH_USERBOT_API_ID")
    hh_userbot_api_hash: SecretStr | None = Field(None, alias="HH_USERBOT_API_HASH")
    hh_userbot_session: str = Field("deploy/userbot/hh.session", alias="HH_USERBOT_SESSION")
    hh_bot_username: str = Field("hh_ru_bot", alias="HH_BOT_USERNAME")
    # web-скрейпер (Playwright по авторизованной сессии)
    hh_web_profile_dir: str = Field("deploy/hh_profile", alias="HH_WEB_PROFILE_DIR")
    hh_recommendations_url: str = Field(
        "https://hh.ru/search/vacancy?order_by=relevance&items_on_page=50",
        alias="HH_RECOMMENDATIONS_URL",
    )
    hh_resume_url: str | None = Field(None, alias="HH_RESUME_URL")
    publish_interval_hours: int = Field(4, alias="PUBLISH_INTERVAL_HOURS")
    digest_cron: str = Field("0 10 * * *", alias="DIGEST_CRON")
    fewshot_limit: int = Field(10, alias="FEWSHOT_LIMIT")
    fewshot_text_limit: int = Field(800, alias="FEWSHOT_TEXT_LIMIT")

    @property
    def hh_sources(self) -> list[str]:
        return [s.strip() for s in self.hh_sources_raw.split(",") if s.strip()]

    def resolved_hh_mode(self) -> Literal["fake", "real"]:
        """auto: real при наличии доступа хотя бы к одному источнику, иначе моки.

        Признаки доступа: userbot (api_id), URL резюме или залогиненный
        браузер-профиль (непустой каталог после `hh_login`).
        """
        if self.hh_mode != "auto":
            return self.hh_mode
        from pathlib import Path

        profile = Path(self.hh_web_profile_dir)
        web_logged_in = profile.is_dir() and any(p.name != ".gitignore" for p in profile.iterdir())
        # email-источник HH едет на Gmail (этап 2): доступ = наличие Gmail-токена
        email_ready = "email" in self.hh_sources and self.gmail_refresh_token is not None
        has_access = (
            self.hh_userbot_api_id is not None
            or self.hh_resume_url is not None
            or web_logged_in
            or email_ready
        )
        return "real" if has_access else "fake"

    def resolved_llm_mode(self) -> Literal["fake", "real"]:
        """auto: real при наличии ключа OpenRouter, иначе стаб-скоринг."""
        if self.llm_mode != "auto":
            return self.llm_mode
        return "real" if self.openrouter_api_key else "fake"

    def resolved_gmail_mode(self) -> Literal["fake", "real"]:
        """auto: real при наличии refresh token Gmail, иначе мок-корпус."""
        if self.gmail_mode != "auto":
            return self.gmail_mode
        return "real" if self.gmail_refresh_token else "fake"

    @property
    def mail_whitelist_domains(self) -> tuple[str, ...]:
        return tuple(d.strip() for d in self.mail_whitelist_domains_raw.split(";") if d.strip())

    @property
    def linkedin_companies(self) -> list[str]:
        return [c.strip() for c in self.linkedin_companies_raw.split(";") if c.strip()]

    @property
    def linkedin_roles(self) -> list[str]:
        return [r.strip() for r in self.linkedin_roles_raw.split(";") if r.strip()]

    # --- LLM (модели per-purpose — свап без кода, PLAN.md §2) ---
    llm_base_url: str = Field("https://openrouter.ai/api/v1", alias="LLM_BASE_URL")
    llm_model_scoring: str = Field("google/gemini-2.5-flash-lite", alias="LLM_MODEL_SCORING")
    llm_model_summary: str = Field("google/gemini-2.5-flash-lite", alias="LLM_MODEL_SUMMARY")
    llm_model_letters: str = Field("google/gemini-2.5-pro", alias="LLM_MODEL_LETTERS")
    # инвайты (этап 3): flash-lite не тянет анти-штамп/роль-тон (eval invite_rubric) → flash
    llm_model_invite: str = Field("google/gemini-2.5-flash", alias="LLM_MODEL_INVITE")
    llm_model_judge: str = Field("google/gemini-2.5-flash", alias="LLM_MODEL_JUDGE")
    price_per_mtok_in: float = Field(0.10, alias="PRICE_PER_MTOK_IN")
    price_per_mtok_out: float = Field(0.40, alias="PRICE_PER_MTOK_OUT")

    # --- GetMatch (этап 4; публичный JSON /api/offers, off-by-default, contracts/env.md) ---
    # Единый список активных адаптеров-источников; getmatch добавляется осознанно
    # (owner-approval после canary, constitution VI). Секретов у источника нет.
    sources_raw: str = Field("email", alias="SOURCES")
    getmatch_mode: Literal["auto", "fake", "real"] = Field("fake", alias="GETMATCH_MODE")
    getmatch_api_url: str = Field("https://getmatch.ru/api/offers", alias="GETMATCH_API_URL")
    getmatch_user_agent: str = Field(
        "JobPilot/0.1 (personal-agent; owner-contact)", alias="GETMATCH_USER_AGENT"
    )
    getmatch_request_pause_sec: float = Field(1.0, alias="GETMATCH_REQUEST_PAUSE_SEC")
    getmatch_page_limit: int = Field(20, alias="GETMATCH_PAGE_LIMIT")
    getmatch_timeout_sec: float = Field(20.0, alias="GETMATCH_TIMEOUT_SEC")

    @property
    def sources(self) -> list[str]:
        return [s.strip() for s in self.sources_raw.split(",") if s.strip()]

    def resolved_getmatch_mode(self) -> Literal["fake", "real"]:
        """auto: real при включении getmatch в SOURCES, иначе стаб; выключен по умолчанию."""
        if self.getmatch_mode != "auto":
            return self.getmatch_mode
        return "real" if "getmatch" in self.sources else "fake"

    # --- сайты-скрейперы (этап 5; off-by-default guardrail, contracts/env.md) ---
    sites_active_raw: str = Field("", alias="SITES_ACTIVE")
    sites_canary_raw: str = Field("", alias="SITES_CANARY")
    sites_heavy_raw: str = Field("ozon", alias="SITES_HEAVY")
    sites_rate_limit_sec: float = Field(1.0, alias="SITES_RATE_LIMIT_SEC")
    sites_timeout_sec: float = Field(20.0, alias="SITES_TIMEOUT_SEC")
    sites_user_agent: str = Field("JobPilot/1.0 (+owner-contact)", alias="SITES_USER_AGENT")
    sites_em_keywords_raw: str = Field(
        "engineering manager;руководитель разработки;head of engineering;team lead;тимлид",
        alias="SITES_EM_KEYWORDS",
    )
    sites_robots_respect: bool = Field(True, alias="SITES_ROBOTS_RESPECT")

    @property
    def sites_active(self) -> list[str]:
        return _split_sites(self.sites_active_raw)

    @property
    def sites_canary(self) -> list[str]:
        return _split_sites(self.sites_canary_raw)

    @property
    def sites_heavy(self) -> list[str]:
        return _split_sites(self.sites_heavy_raw)

    @property
    def sites_em_keywords(self) -> list[str]:
        return [k.strip() for k in self.sites_em_keywords_raw.split(";") if k.strip()]

    @model_validator(mode="after")
    def _validate_sites(self) -> Settings:
        for raw in (self.sites_active_raw, self.sites_canary_raw, self.sites_heavy_raw):
            unknown = sorted(set(_split_sites(raw)) - KNOWN_SITES)
            if unknown:
                raise ValueError(
                    "Неизвестные сайты в SITES_*: "
                    + ", ".join(unknown)
                    + f". Допустимо: {', '.join(sorted(KNOWN_SITES))}"
                )
        if self.sites_rate_limit_sec < SITES_MIN_RATE_LIMIT_SEC:
            raise ValueError(
                f"SITES_RATE_LIMIT_SEC={self.sites_rate_limit_sec} нарушает вежливость "
                f"≥{SITES_MIN_RATE_LIMIT_SEC} s между запросами (scraping-risks.md)"
            )
        if self.getmatch_request_pause_sec < GETMATCH_MIN_PAUSE_SEC:
            raise ValueError(
                f"GETMATCH_REQUEST_PAUSE_SEC={self.getmatch_request_pause_sec} нарушает "
                f"вежливость ≥{GETMATCH_MIN_PAUSE_SEC} s между страницами (scraping-risks.md)"
            )
        return self

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
            self.hh_userbot_api_hash,
            self.gmail_client_secret,
            self.gmail_refresh_token,
        ]
        return [s.get_secret_value() for s in secrets if s is not None]
