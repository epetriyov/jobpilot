"""wave B: extend scraper_approval CHECK to navio/mts/rwb

Revision ID: 0011_wave_b_sites
Revises: 0010_stage6e
Create Date: 2026-08-13

Волна B добавила адаптеры navio/mts/rwb в KNOWN_SITES и SITE_ADAPTERS, но CHECK
`ck_scraper_approval_site` (миграция 0006) допускал только 7 старых сайтов —
`/approve_scraper navio|mts|rwb` падал на constraint (INSERT нарушал CHECK).
Пересоздаём CHECK по актуальному списку KNOWN_SITES. Само хранилище/домен не
меняются — расширяется только допустимое множество служебного флага источника.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_wave_b_sites"
down_revision: str | None = "0010_stage6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Держим синхронно с app.config.KNOWN_SITES (CHECK не может ссылаться на код —
# при добавлении сайта нужна новая миграция; см. тест test_known_sites_*).
_SITES_V2 = ("yandex", "vk", "avito", "tbank", "ozon", "alfa", "sber", "navio", "mts", "rwb")
_SITES_V1 = ("yandex", "vk", "avito", "tbank", "ozon", "alfa", "sber")


def _recreate_check(allowed: tuple[str, ...]) -> None:
    op.drop_constraint("ck_scraper_approval_site", "scraper_approval", type_="check")
    joined = ",".join(f"'{s}'" for s in allowed)
    op.create_check_constraint(
        "ck_scraper_approval_site", "scraper_approval", f"site_name IN ({joined})"
    )


def upgrade() -> None:
    _recreate_check(_SITES_V2)


def downgrade() -> None:
    # Строки сайтов волны B нарушили бы старый CHECK — удаляем перед сужением.
    removed = ",".join(f"'{s}'" for s in ("navio", "mts", "rwb"))
    op.execute(f"DELETE FROM scraper_approval WHERE site_name IN ({removed})")
    _recreate_check(_SITES_V1)
