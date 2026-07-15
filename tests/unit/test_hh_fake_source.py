"""Мок-режим HH (спека 001: «поднять моки до кредов, потом переключить на реальный API»).

FakeHhVacancySource — реализация VacancySourcePort с реалистичными вакансиями:
механика дайджеста/разметки тестируется end-to-end без внешних вызовов.
"""

from app.adapters.hh.fake import FakeHhVacancySource
from app.adapters.llm.fake import stub_scoring_response
from app.config import Settings
from app.domain.relevance import LlmScore


async def test_fake_source_returns_realistic_pool() -> None:
    source = FakeHhVacancySource()
    vacancies = await source.fetch()

    assert source.name == "hh"
    assert len(vacancies) >= 8
    refs = [v.source_ref.as_key() for v in vacancies]
    assert len(refs) == len(set(refs))  # без дублей
    assert all(v.source_ref.source == "hh" for v in vacancies)
    # есть вилка «от X» без «до» ([S-C1]-механика на моках)
    assert any(v.salary.from_ and not v.salary.to for v in vacancies)
    # HTML из описаний вычищен доменом (S3), оригинал в raw
    assert all("<" not in v.description_text for v in vacancies)
    assert any("<" in str(v.raw.get("description", "")) for v in vacancies)


async def test_fake_source_brings_new_vacancies_each_fetch() -> None:
    """Повторный /digest должен приносить новые вакансии — иначе механику не потестить."""
    source = FakeHhVacancySource(batch_size=3)
    first = {v.source_ref.as_key() for v in await source.fetch()}
    second = {v.source_ref.as_key() for v in await source.fetch()}

    assert second - first, "второй fetch не принёс ничего нового"


def test_stub_scoring_response_is_valid_and_deterministic() -> None:
    text = "Engineering Manager — Acme\nКоманда 10 человек"
    a = stub_scoring_response(text)
    b = stub_scoring_response(text)

    assert a == b  # детерминизм: тот же текст → тот же скор
    score = LlmScore.model_validate_json(a)
    assert 0 <= score.score <= 100
    assert score.reason


def test_mode_resolution(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """HH_MODE/LLM_MODE=auto: fake без кредов, real с кредами; явное значение побеждает."""
    base = {
        "TELEGRAM_API_TOKEN": "1:t",
        "OWNER_CHAT_ID": "1",
        "OPENROUTER_API_KEY": "sk-or-x",
        "POSTGRES_DSN": "postgresql+psycopg://u:p@h/db",
    }
    for k in ("HH_MODE", "LLM_MODE", "HH_USERBOT_API_ID", "HH_RESUME_URL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in base.items():
        monkeypatch.setenv(k, v)

    s = Settings.load(env_file=None)
    assert s.resolved_hh_mode() == "fake"  # нет доступа к источникам → моки
    assert s.resolved_llm_mode() == "real"  # ключ есть → реальный LLM

    monkeypatch.setenv("HH_USERBOT_API_ID", "123456")
    assert Settings.load(env_file=None).resolved_hh_mode() == "real"

    monkeypatch.setenv("HH_MODE", "fake")
    monkeypatch.setenv("LLM_MODE", "fake")
    s = Settings.load(env_file=None)
    assert s.resolved_hh_mode() == "fake"  # явный fake важнее наличия кредов
    assert s.resolved_llm_mode() == "fake"
