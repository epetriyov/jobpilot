"""stage5: scraper_approval (specs/005-sites/data-model.md)

Revision ID: 0006_stage5
Revises: 0004_stage3
Create Date: 2026-08-12

Персист факта `/approve_scraper <site>`: сайт из SITES_CANARY без строки →
секция «На проверку (canary)»; строка есть → основной поток (FR-007). Домен
SOURCING не меняется — это служебный флаг источника, не агрегат.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_stage5"
down_revision: str | None = "0004_stage3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWN_SITES = ("yandex", "vk", "avito", "tbank", "ozon", "alfa", "sber")


def upgrade() -> None:
    allowed = ",".join(f"'{s}'" for s in _KNOWN_SITES)
    op.create_table(
        "scraper_approval",
        sa.Column("site_name", sa.Text(), primary_key=True),
        sa.Column(
            "approved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("approved_by_chat_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(f"site_name IN ({allowed})", name="ck_scraper_approval_site"),
    )


def downgrade() -> None:
    op.drop_table("scraper_approval")
