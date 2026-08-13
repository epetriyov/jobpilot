"""Реестр по-сайтовых адаптеров (этап 5): site_name → фабрика SiteAdapter.

Пуст в фундаменте — off-by-default. По-сайтовые задачи (T510+: yandex/vk/avito/…)
регистрируют сюда фабрику своего адаптера. Композиция собирает источники по
конфигу (SITES_ACTIVE ∪ SITES_CANARY); незарегистрированный сайт → пропуск с
предупреждением (не роняет сбор из остальных, S4).
"""

from __future__ import annotations

from collections.abc import Callable

from app.adapters.sites.avito import avito_factory
from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.adapters.sites.mts import mts_factory
from app.adapters.sites.navio import navio_factory
from app.adapters.sites.rwb import rwb_factory
from app.adapters.sites.sber import sber_factory
from app.adapters.sites.tbank import tbank_factory
from app.adapters.sites.vk import vk_factory
from app.adapters.sites.yandex import yandex_factory
from app.config import Settings

# Фабрика адаптера сайта: получает конфиг и опциональный колбэк эскалации анти-бота.
SiteFactory = Callable[[Settings, EscalateFn | None], SiteAdapter]

# Волна A (лёгкие, httpx, текущее железо): подключение источника — off-by-default,
# только через SITES_ACTIVE/SITES_CANARY владельца (guardrail scraping-risks.md).
# Ozon (🔴) не реализуется; Альфа — после XHR-спайка владельца.
# ⚠️ tbank: тело POST-запроса (source) требует подтверждения браузерным XHR перед
# включением в SITES_ACTIVE (см. docstring tbank.py) — парсер/golden от этого не зависят.
SITE_ADAPTERS: dict[str, SiteFactory] = {
    "yandex": yandex_factory,
    "vk": vk_factory,
    "avito": avito_factory,
    "sber": sber_factory,
    "tbank": tbank_factory,
    # Волна B (2026-08-13): публичные JSON/встроенные фиды карьерных порталов.
    "navio": navio_factory,  # Gatsby window.pageData (встроенный JSON)
    "mts": mts_factory,  # публичный каталог /api/v2/catalog/v1/vacancies
    "rwb": rwb_factory,  # публичный /crm-api/api/v1/pub/vacancies (RWB/WB)
}
