"""[N-U3] Статическая гарантия полуавтомата (N1, constitution IV):
в кодовой базе нет HTTP-обращений к linkedin.com.

Строка-шаблон search_url (домен networking) и маршрутизация писем-уведомлений
(домен correspondence) — данные, не запросы; они в белом списке.
"""

import re
from pathlib import Path

APP = Path(__file__).parent.parent.parent / "app"

# файлы, где linkedin.com допустим КАК СТРОКА-ДАННЫЕ (не как цель HTTP-запроса)
ALLOWED_FILES = {
    "app/domain/networking/invites.py",  # шаблон people-search URL для владельца
    "app/domain/correspondence/inbox.py",  # маршрутизация писем-уведомлений
    "app/adapters/gmail/fake.py",  # мок-корпус: адреса отправителей — данные
}


def test_no_http_calls_to_linkedin() -> None:
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = str(path.relative_to(APP.parent))
        text = path.read_text(encoding="utf-8")
        if "linkedin.com" not in text:
            continue
        if rel in ALLOWED_FILES:
            # даже в白 списке не должно быть http-клиента рядом
            assert "httpx" not in text or "linkedin" not in _http_lines(text), (
                f"{rel}: httpx рядом с linkedin.com"
            )
            continue
        offenders.append(rel)
    assert offenders == [], f"linkedin.com вне белого списка: {offenders}"


def test_no_linkedin_client_module_exists() -> None:
    """Кода, умеющего ходить в LinkedIn, не существует как модуля."""
    assert not (APP / "adapters" / "linkedin").exists()


def _http_lines(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if re.search(r"(httpx|requests|urlopen|aiohttp)", line)
    )
