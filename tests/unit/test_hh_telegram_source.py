"""[S-C4] Парсер сообщений HH-бота (userbot-источник, пересмотр 2026-07-15).

Golden — синтетические плейсхолдеры (tests/golden/hh_telegram), заменяются
реальными обезличенными сообщениями. Парсер чистый; чтение диалога — фейковый reader.
"""

from pathlib import Path

from app.adapters.hh.telegram_source import HhTelegramSource, parse_hh_bot_message

GOLDEN = Path(__file__).parent.parent / "golden" / "hh_telegram"


def golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


class FakeReader:
    """TelegramMessageReaderPort: отдаёт заранее заданные тексты сообщений."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self.requested_peer: str | None = None

    async def recent_messages(self, peer: str, limit: int = 100) -> list[str]:
        self.requested_peer = peer
        return self._texts


class TestParser:
    def test_standard_message(self) -> None:
        v = parse_hh_bot_message(golden("msg_01_standard.txt"))
        assert v is not None
        assert v.source_ref.as_key() == "hh:91000001"
        assert v.title == "Engineering Manager"
        assert v.company == "Ромашка Технологии"
        assert v.url == "https://hh.ru/vacancy/91000001"
        assert v.salary.from_ == 350_000
        assert v.salary.to == 450_000

    def test_from_only_salary(self) -> None:
        """[S-C1]-механика: «от X» без «до» → Salary(from=X, to=None)."""
        v = parse_hh_bot_message(golden("msg_02_from_only.txt"))
        assert v is not None
        assert v.salary.from_ == 500_000
        assert v.salary.to is None

    def test_no_salary(self) -> None:
        v = parse_hh_bot_message(golden("msg_03_no_salary.txt"))
        assert v is not None
        assert v.salary.from_ is None and v.salary.to is None
        assert v.title == "Руководитель группы разработки"

    def test_unparsed_returns_none(self) -> None:
        assert parse_hh_bot_message(golden("msg_04_unparsed_summary.txt")) is None
        assert parse_hh_bot_message(golden("msg_05_unparsed_greeting.txt")) is None


class TestSource:
    async def test_fetch_parses_and_collects_unparsed(self) -> None:
        texts = [golden(f) for f in sorted(p.name for p in GOLDEN.glob("msg_*.txt"))]
        reader = FakeReader(texts)
        source = HhTelegramSource(reader=reader, bot_username="hh_ru_bot")

        vacancies = await source.fetch()

        assert source.name == "hh"
        assert reader.requested_peer == "hh_ru_bot"
        assert [v.source_ref.as_key() for v in vacancies] == [
            "hh:91000001",
            "hh:91000002",
            "hh:91000003",
        ]
        # непарсенное сохранено для raw-секции (S-C6), не роняет пайплайн
        assert len(source.unparsed) == 2

    async def test_parse_accuracy_at_least_95_percent_on_vacancy_messages(self) -> None:
        """[S-C4]: среди сообщений-вакансий title/company/url извлечены в ≥95%."""
        vacancy_msgs = [
            golden(f"msg_0{i}_{s}.txt")
            for i, s in ((1, "standard"), (2, "from_only"), (3, "no_salary"))
        ]
        parsed = [parse_hh_bot_message(t) for t in vacancy_msgs]
        ok = [p for p in parsed if p and p.title and p.company and p.url]
        assert len(ok) / len(vacancy_msgs) >= 0.95
