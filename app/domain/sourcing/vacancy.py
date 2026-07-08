"""Агрегат Vacancy и функции нормализации (DOMAIN.md §3.1)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.shared import Salary, SourceRef

_BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "br", "h1", "h2", "h3", "h4", "tr"}

# юр-формы, не влияющие на идентичность компании при кросс-дедупе (S2)
_LEGAL_FORMS = {"ооо", "оао", "зао", "пао", "ао", "ип", "llc", "inc", "ltd", "gmbh"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_html(raw: str) -> str:
    """S3: очистка описания от HTML с сохранением абзацев; оригинал остаётся в raw."""
    parser = _TextExtractor()
    parser.feed(raw)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def normalize_company_title(company: str, title: str) -> tuple[str, str]:
    """Нормализованная пара (company, title) для кросс-источникового дедупа (S2)."""

    def norm(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold()
        value = re.sub(r"[^\w\s]", " ", value)
        words = [w for w in value.split() if w not in _LEGAL_FORMS]
        return " ".join(words)

    return norm(company), norm(title)


class Vacancy(BaseModel):
    """Объявление о работе из любого источника; уникальна по SourceRef (S1)."""

    model_config = ConfigDict(validate_assignment=True)

    source_ref: SourceRef
    title: str
    company: str
    url: str
    description_text: str
    raw: dict[str, Any]
    salary: Salary = Salary()
    location: str | None = None
    duplicate_of: SourceRef | None = None

    @classmethod
    def create(
        cls,
        *,
        source_ref: SourceRef,
        title: str,
        company: str,
        url: str,
        description_raw: str,
        salary: Salary | None = None,
        location: str | None = None,
        extra_raw: dict[str, Any] | None = None,
    ) -> Vacancy:
        raw: dict[str, Any] = {"description": description_raw, **(extra_raw or {})}
        return cls(
            source_ref=source_ref,
            title=title,
            company=company,
            url=url,
            description_text=clean_html(description_raw),
            raw=raw,
            salary=salary or Salary(),
            location=location,
        )

    @property
    def eligible_for_digest(self) -> bool:
        """S2: дубликаты в дайджест не идут."""
        return self.duplicate_of is None

    def normalized_key(self) -> str:
        company, title = normalize_company_title(self.company, self.title)
        return f"{company}|{title}"

    def mark_duplicate_of(self, original: SourceRef) -> None:
        self.duplicate_of = original


def content_hash(vacancy: Vacancy) -> str:
    """Стабильный хеш содержимого — детект изменений вакансии."""
    payload = "\x1f".join(
        [
            vacancy.source_ref.as_key(),
            vacancy.title,
            vacancy.company,
            vacancy.description_text,
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()
