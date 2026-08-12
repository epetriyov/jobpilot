"""HR-извлечение (data-model §5, под-этап 6G): схема результата `hr_extract`.

Чистый домен: только pydantic. Из пересланного HR-сообщения LLM извлекает
`{date?, url?, gist}`; результат дополняет `interview_url`/`notes` заявки через
`add_interview_details` (второй путь) и НИКОГДА не меняет статус (C3). Текст
сообщения — недоверенные данные (R5, экранируется адаптером); тело не логируется (M4).
"""

from __future__ import annotations

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field

# Суть встречи — короткая (совпадает с лимитом summary писем, M2): дополняет notes.
HR_GIST_MAX_CHARS = 200


class HrDetails(BaseModel):
    """Схема структурированного выхода LLM (purpose=hr_extract): дата/ссылка/суть.

    Все поля опциональны по смыслу: в сообщении может не быть даты или ссылки.
    `gist` — краткая суть (≤200), уходит в `notes`; статус заявки не трогает (C3).
    """

    model_config = ConfigDict(frozen=True)

    date: date_type | None = None
    url: str | None = None
    gist: str = Field(default="", max_length=HR_GIST_MAX_CHARS)

    @property
    def is_empty(self) -> bool:
        """Ничего полезного не извлечено → мягкий фолбэк на ручной ввод (US3)."""
        return self.date is None and self.url is None and not self.gist.strip()
