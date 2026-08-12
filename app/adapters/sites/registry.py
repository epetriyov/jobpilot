"""Реестр по-сайтовых адаптеров (этап 5): site_name → фабрика SiteAdapter.

Пуст в фундаменте — off-by-default. По-сайтовые задачи (T510+: yandex/vk/avito/…)
регистрируют сюда фабрику своего адаптера. Композиция собирает источники по
конфигу (SITES_ACTIVE ∪ SITES_CANARY); незарегистрированный сайт → пропуск с
предупреждением (не роняет сбор из остальных, S4).
"""

from __future__ import annotations

from collections.abc import Callable

from app.adapters.sites.base import EscalateFn, SiteAdapter
from app.config import Settings

# Фабрика адаптера сайта: получает конфиг и опциональный колбэк эскалации анти-бота.
SiteFactory = Callable[[Settings, EscalateFn | None], SiteAdapter]

SITE_ADAPTERS: dict[str, SiteFactory] = {}
