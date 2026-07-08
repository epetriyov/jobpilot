"""Домен shared: SourceRef, Salary (DOMAIN.md §3.1, data-model.md)."""

import pytest
from pydantic import ValidationError

from app.domain.shared import Salary, Source, SourceRef


class TestSourceRef:
    def test_site_source_requires_site_name(self) -> None:
        with pytest.raises(ValidationError):
            SourceRef(source=Source.SITE, external_id="123")

    def test_non_site_source_forbids_site_name(self) -> None:
        with pytest.raises(ValidationError):
            SourceRef(source=Source.HH, site_name="yandex", external_id="123")

    def test_as_key_is_canonical(self) -> None:
        assert SourceRef(source=Source.HH, external_id="42").as_key() == "hh:42"
        assert (
            SourceRef(source=Source.SITE, site_name="yandex", external_id="7").as_key()
            == "site:yandex:7"
        )

    def test_is_frozen_value_object(self) -> None:
        ref = SourceRef(source=Source.HH, external_id="42")
        with pytest.raises(ValidationError):
            ref.external_id = "43"  # type: ignore[misc]
        assert ref == SourceRef(source=Source.HH, external_id="42")


class TestSalary:
    def test_all_fields_optional(self) -> None:
        salary = Salary()
        assert salary.from_ is None and salary.to is None and salary.currency is None

    def test_partial_fork_from_only(self) -> None:
        salary = Salary(from_=300_000, currency="RUR")
        assert salary.from_ == 300_000
        assert salary.to is None
