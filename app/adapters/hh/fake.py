"""Мок HH-источника: механика этапа 1 без кредов (спека 001, решение владельца).

Реализует тот же VacancySourcePort, что и будущий HhVacancySource (T107) —
переключение на реальный API = HH_MODE=real в конфиге, код не меняется.
Каждый fetch добавляет к базовому пулу немного новых вакансий, чтобы
повторные /digest приносили свежие карточки.
"""

from __future__ import annotations

from app.domain.shared import Salary, Source, SourceRef
from app.domain.sourcing import Vacancy

# Базовый пул: реалистичные EM-вакансии + заведомо мусорные (для 👎 и порога R4).
_BASE_POOL: list[dict[str, object]] = [
    {
        "id": "9001",
        "title": "Engineering Manager (Platform)",
        "company": "Ромашка Технологии",
        "salary": Salary(from_=350_000, to=450_000, currency="RUR"),
        "description": "<p>Ищем EM в платформенную команду (12 инженеров).</p>"
        "<ul><li>Python, Go, k8s</li><li>Процессы: скрам, найм, 1:1</li></ul>",
    },
    {
        "id": "9002",
        "title": "Head of Engineering",
        "company": "Финтех Плюс",
        "salary": Salary(from_=500_000, to=None, currency="RUR"),  # «от X» без «до»
        "description": "<p>Руководство разработкой (3 команды, 25 человек), стратегия, найм.</p>",
    },
    {
        "id": "9003",
        "title": "Руководитель группы разработки",
        "company": "Маркетплейс Юг",
        "salary": Salary(),
        "description": "<p>Группа из 6 разработчиков, стек Java/Kotlin, микросервисы.</p>",
    },
    {
        "id": "9004",
        "title": "Engineering Manager (ML Platform)",
        "company": "Дата Системы",
        "salary": Salary(from_=400_000, to=520_000, currency="RUR"),
        "description": "<p>ML-платформа, команда 9 человек, Python, MLOps, менторинг лидов.</p>",
    },
    {
        "id": "9005",
        "title": "Менеджер по продажам IT-услуг",
        "company": "Продажи Про",
        "salary": Salary(from_=80_000, to=120_000, currency="RUR"),
        "description": "<p>Холодные звонки, план продаж, CRM. Опыт в IT не обязателен.</p>",
    },
    {
        "id": "9006",
        "title": "Delivery Manager",
        "company": "Аутсорс Гигант",
        "salary": Salary(from_=280_000, to=350_000, currency="RUR"),
        "description": "<p>Ведение проектов заказной разработки, команда до 15 человек.</p>",
    },
    {
        "id": "9007",
        "title": "Тестировщик ПО (junior)",
        "company": "Стартап Ноль",
        "salary": Salary(from_=60_000, to=90_000, currency="RUR"),
        "description": "<p>Ручное тестирование мобильного приложения.</p>",
    },
    {
        "id": "9008",
        "title": "Head of Backend",
        "company": "Логистика 24",
        "salary": Salary(from_=450_000, to=None, currency="RUR"),
        "description": "<p>Backend-направление (4 команды), Python/Go, highload, найм лидов.</p>",
    },
    {
        "id": "9009",
        "title": "CTO / Технический директор",
        "company": "МедТех Сервис",
        "salary": Salary(),
        "description": "<p>Технологическая стратегия, команда 30+, продуктовая разработка.</p>",
    },
    {
        "id": "9010",
        "title": "Engineering Manager (Mobile)",
        "company": "Банк Диджитал",
        "salary": Salary(from_=380_000, to=470_000, currency="RUR"),
        "description": "<p>Две мобильные команды (iOS/Android), релизный цикл, найм, метрики.</p>",
    },
]

_EXTRA_TITLES = [
    ("Engineering Manager (Data)", "Аналитика Плюс"),
    ("Руководитель разработки (e-com)", "Торговая Сеть"),
    ("Team Lead → EM", "Облако Технологии"),
    ("Head of Platform Engineering", "Телеком Нео"),
    ("Менеджер проектов 1С", "Интегратор Классик"),
]


class FakeHhVacancySource:
    """VacancySourcePort: детерминированный пул + новые вакансии на каждый fetch."""

    name = "hh"

    def __init__(self, *, batch_size: int = 3) -> None:
        self._batch_size = batch_size
        self._fetches = 0

    async def fetch(self) -> list[Vacancy]:
        vacancies = [self._build(item) for item in _BASE_POOL]
        # каждый повторный fetch докидывает свежие id — имитация новых публикаций
        for n in range(self._fetches * self._batch_size):
            title, company = _EXTRA_TITLES[n % len(_EXTRA_TITLES)]
            salary = Salary(from_=300_000 + (n % 5) * 20_000, to=None, currency="RUR")
            vacancies.append(
                self._build(
                    {
                        "id": str(9100 + n),
                        "title": title,
                        "company": company,
                        "salary": salary,
                        "description": f"<p>Команда {5 + n % 10} человек, найм, delivery.</p>",
                    }
                )
            )
        self._fetches += 1
        return vacancies

    @staticmethod
    def _build(item: dict[str, object]) -> Vacancy:
        external_id = str(item["id"])
        return Vacancy.create(
            source_ref=SourceRef(source=Source.HH, external_id=external_id),
            title=str(item["title"]),
            company=str(item["company"]),
            url=f"https://hh.ru/vacancy/{external_id}",
            description_raw=str(item["description"]),
            salary=item["salary"] if isinstance(item["salary"], Salary) else Salary(),
        )
