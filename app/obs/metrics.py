"""Единая точка метрик (AGENT_GUIDE.md §5): snake_case, лейблы source/site/purpose."""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("jobpilot")

job_runs_total = _meter.create_counter(
    "job_runs_total", description="Прогоны плановых задач", unit="1"
)
vacancies_discovered_total = _meter.create_counter(
    "vacancies_discovered_total", description="Обнаруженные вакансии по источникам", unit="1"
)
llm_tokens_total = _meter.create_counter(
    "llm_tokens_total", description="Токены LLM (лейблы purpose, direction)", unit="1"
)
llm_cost_usd_total = _meter.create_counter(
    "llm_cost_usd_total", description="Стоимость LLM-вызовов, USD", unit="1"
)
scraper_failures_total = _meter.create_counter(
    "scraper_failures_total", description="Сбои адаптеров-источников (лейбл site)", unit="1"
)
digest_sent_total = _meter.create_counter(
    "digest_sent_total", description="Отправленные дайджесты (алерт 10:15 МСК)", unit="1"
)
