"""[T507][US3] Канарейка: разбиение карточек дайджеста на основной поток и «На проверку».

Правило (FR-007, data-model): вакансия сайта из SITES_CANARY БЕЗ строки одобрения
(scraper_approval) → секция «На проверку (canary)» с пометкой `site:<name> · canary`;
одобренный сайт → основной поток; НЕ-сайтовые источники (hh/getmatch) всегда основные.
Пометка `site:<name>` видна и в основном потоке (SC-002).
"""

from __future__ import annotations

from app.application.run_daily_digest import split_canary_cards
from app.ports.notifier import DigestCard


def card(ref_key: str) -> DigestCard:
    return DigestCard(
        ref_key=ref_key,
        title="Engineering Manager",
        company="Acme",
        url="https://example/1",
        salary_text=None,
        score=80,
        reason="матч",
    )


def test_hh_card_always_main() -> None:
    main, canary = split_canary_cards(
        [card("hh:42")], canary_sites={"yandex"}, approved_sites=set()
    )
    assert [c.ref_key for c in main] == ["hh:42"]
    assert canary == []
    assert main[0].note is None  # у не-сайтовых источников пометки нет


def test_unapproved_canary_site_goes_to_review() -> None:
    main, canary = split_canary_cards(
        [card("site:yandex:v1")], canary_sites={"yandex"}, approved_sites=set()
    )
    assert main == []
    assert [c.ref_key for c in canary] == ["site:yandex:v1"]
    assert canary[0].note == "site:yandex · canary"


def test_approved_site_goes_to_main_with_marker() -> None:
    main, canary = split_canary_cards(
        [card("site:yandex:v1")], canary_sites={"yandex"}, approved_sites={"yandex"}
    )
    assert canary == []
    assert [c.ref_key for c in main] == ["site:yandex:v1"]
    assert main[0].note == "site:yandex"  # маркер источника без · canary


def test_active_site_not_in_canary_is_main() -> None:
    """Сайт в SITES_ACTIVE (не canary) → основной поток с пометкой site:<name>."""
    main, canary = split_canary_cards(
        [card("site:sber:v9")], canary_sites=set(), approved_sites=set()
    )
    assert canary == []
    assert main[0].note == "site:sber"


def test_mixed_batch_partitioned() -> None:
    cards = [card("hh:1"), card("site:yandex:2"), card("site:vk:3"), card("site:sber:4")]
    main, canary = split_canary_cards(cards, canary_sites={"yandex", "vk"}, approved_sites={"vk"})
    assert {c.ref_key for c in main} == {"hh:1", "site:vk:3", "site:sber:4"}
    assert {c.ref_key for c in canary} == {"site:yandex:2"}
