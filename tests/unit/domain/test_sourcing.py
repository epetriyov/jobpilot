"""Домен sourcing: инварианты S1–S4 (DOMAIN.md §3.1; кейсы [S-U1]–[S-U4])."""

from datetime import UTC, datetime, timedelta

from app.domain.shared import Source, SourceRef
from app.domain.sourcing import (
    DedupIndex,
    SourceFetchFailed,
    Vacancy,
    VacancyDiscovered,
    collect_from_sources,
    content_hash,
    normalize_company_title,
)


def make_vacancy(
    external_id: str = "1",
    source: Source = Source.HH,
    site_name: str | None = None,
    title: str = "Engineering Manager",
    company: str = "Acme",
    description: str = "Ведём команду из 10 человек",
) -> Vacancy:
    return Vacancy.create(
        source_ref=SourceRef(source=source, site_name=site_name, external_id=external_id),
        title=title,
        company=company,
        url=f"https://example.com/{external_id}",
        description_raw=description,
    )


NOW = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)


class TestS1SameSourceDedup:
    """[S-U1] Повторное обнаружение того же SourceRef не создаёт дубликат, first_seen неизменен."""

    def test_second_ingest_is_ignored(self) -> None:
        index = DedupIndex()
        first = index.ingest(make_vacancy("1"), now=NOW)
        second = index.ingest(make_vacancy("1"), now=NOW + timedelta(days=1))

        assert isinstance(first, VacancyDiscovered)
        assert second is None
        assert index.first_seen_at(make_vacancy("1").source_ref) == NOW


class TestS2CrossSourceDedup:
    """[S-U2] Та же нормализованная (company,title) из другого источника за 30 дней → duplicate_of."""

    def test_duplicate_within_30_days_marked(self) -> None:
        index = DedupIndex()
        original = make_vacancy("1", source=Source.HH, title="Engineering Manager", company="Acme")
        index.ingest(original, now=NOW)

        dup = make_vacancy(
            "77",
            source=Source.SITE,
            site_name="yandex",
            title="  engineering   MANAGER ",
            company="ACME, ООО",
        )
        event = index.ingest(dup, now=NOW + timedelta(days=10))

        assert event is None
        assert dup.duplicate_of == original.source_ref
        assert not dup.eligible_for_digest

    def test_same_pair_after_30_days_is_new(self) -> None:
        index = DedupIndex()
        index.ingest(make_vacancy("1"), now=NOW)

        late = make_vacancy("77", source=Source.SITE, site_name="yandex")
        event = index.ingest(late, now=NOW + timedelta(days=31))

        assert isinstance(event, VacancyDiscovered)
        assert late.duplicate_of is None

    def test_normalization(self) -> None:
        assert normalize_company_title(" ACME, ООО ", "Engineering  Manager!") == (
            normalize_company_title("acme ооо", "engineering manager")
        )


class TestS3HtmlCleanup:
    """[S-U3] description_text очищен от HTML/лишних переносов; raw хранит оригинал."""

    def test_html_stripped_raw_kept(self) -> None:
        raw = "<p>Мы ищем <b>EM</b>.</p><ul><li>Python</li><li>k8s</li></ul>\n\n\n🚀"
        vacancy = make_vacancy(description=raw)

        assert "<" not in vacancy.description_text
        assert "Мы ищем EM." in vacancy.description_text
        assert "Python" in vacancy.description_text
        assert vacancy.raw["description"] == raw

    def test_content_hash_stable(self) -> None:
        assert content_hash(make_vacancy("1")) == content_hash(make_vacancy("1"))
        assert content_hash(make_vacancy("1")) != content_hash(make_vacancy("1", title="Другая"))


class TestS4SourceIsolation:
    """[S-U4] Падение одного источника не прерывает сбор из остальных."""

    def test_failing_source_isolated(self) -> None:
        ok_a = [make_vacancy("a1")]
        ok_c = [make_vacancy("c1", source=Source.SITE, site_name="vk")]

        def source_a() -> list[Vacancy]:
            return ok_a

        def source_b() -> list[Vacancy]:
            raise RuntimeError("boom")

        def source_c() -> list[Vacancy]:
            return ok_c

        result = collect_from_sources(
            {"hh": source_a, "getmatch": source_b, "vk": source_c}
        )

        assert result.vacancies == ok_a + ok_c
        assert [type(e) for e in result.failures] == [SourceFetchFailed]
        assert result.failures[0].source == "getmatch"
        assert "boom" in result.failures[0].error
        assert result.partial is True
