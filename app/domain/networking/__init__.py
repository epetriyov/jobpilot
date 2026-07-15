"""Контекст NETWORKING: заготовки инвайтов, полуавтомат (DOMAIN.md §3.5)."""

from app.domain.networking.invites import (
    IllegalTransition,
    InviteDraft,
    InviteStatus,
    InviteText,
    build_pairs,
    people_search_url,
)

__all__ = [
    "IllegalTransition",
    "InviteDraft",
    "InviteStatus",
    "InviteText",
    "build_pairs",
    "people_search_url",
]
