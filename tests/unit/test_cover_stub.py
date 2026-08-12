"""T6E-3: мок-письмо stub_letter_response — валидная схема, упоминает вакансию, ≤2000."""

from app.adapters.llm.fake import stub_letter_response
from app.domain.correspondence import CoverLetterOut


def test_stub_letter_is_valid_schema() -> None:
    raw = stub_letter_response("Вакансия: Head of Engineering\nКомпания: Ромашка\nОписание…")
    out = CoverLetterOut.model_validate_json(raw)
    assert len(out.text) <= 2000


def test_stub_letter_mentions_vacancy_and_company() -> None:
    raw = stub_letter_response("Вакансия: Head of Engineering\nКомпания: Ромашка\nОписание…")
    out = CoverLetterOut.model_validate_json(raw)
    assert "Head of Engineering" in out.text
    assert "Ромашка" in out.text


def test_stub_letter_uses_only_resume_metrics() -> None:
    """Метрики письма — из белого списка резюме (анти-галлюцинации, research §5)."""
    raw = stub_letter_response("Вакансия: EM\nКомпания: Финтех")
    out = CoverLetterOut.model_validate_json(raw)
    assert "crash-free на уровне 99%" in out.text
    assert "команду x3" in out.text
