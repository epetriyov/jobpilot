"""Адаптеры карьерных порталов (этап 5): каркас site-source.

Разделение транспорт (httpx|Playwright) ↔ чистый парсер parse_<site>: golden
тестирует парсер на записанном payload и не зависит от способа добычи
(HTML→JSON, httpx→Playwright). Домен Sourcing НЕ меняется (DOMAIN.md §5).
"""
