"""Сопроводительные письма (data-model §4, под-этап 6E): агрегат + схема LLM.

Чистый домен: только pydantic. Инвариант M3 — письмо ≤ COVER_LETTER_MAX_CHARS;
факты письма — исключительно из резюме (анти-галлюцинации, research §5) —
обеспечивается промптом/eval, не типом. Тела писем не логируются (M4).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# M3: жёсткий лимит письма (дублируется CHECK в БД и COVER_LETTER_MAX_CHARS env).
COVER_LETTER_MAX_CHARS = 2000


class CoverLetterOut(BaseModel):
    """Схема структурированного выхода LLM (purpose=cover): только текст письма."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=COVER_LETTER_MAX_CHARS)


class CoverLetter(BaseModel):
    """Письмо в истории вакансии: 🔁 добавляет новую версию, последняя — актуальная.

    Тело — данные владельца в его БД (не лог, M4). Отправку делает человек вручную
    (система не отправляет, M3/VI).
    """

    model_config = ConfigDict(frozen=True)

    vacancy_id: int
    text: str = Field(min_length=1, max_length=COVER_LETTER_MAX_CHARS)
    prompt_version: str
