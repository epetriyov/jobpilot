# Quickstart: проверка этапа 6 руками (по под-этапам)

Проверяй под-этап за под-этапом — каждый самодостаточен.

## Предусловия

```bash
make lint && make test            # все гейты зелёные
docker compose up -d --build      # bot, worker, db, alloy
```
Секреты — только в `.env` (см. contracts/env.md). Реальные LLM-eval (`cover_letter`, `hr_extract`, сравнение селекторов) — после подключения OpenRouter; до этого CI-eval идёт в fake-режиме.

## 6A — хранилище `vacancy` + миграция

```bash
# на КОПИИ боевой БД:
psql -c "select count(*) from seen_vacancy;"   # запомнить N
make migrate                                    # 0007_stage6a_vacancy
psql -c "select count(*) from vacancy;"         # == N, потерь нет
```
Проверить: ежедневный дайджест и `/train` работают как раньше; повторный `/digest` не плодит дубли (S1); повторный `make migrate` идемпотентен.

## 6B — CRM: сохранить и двигать по воронке

Telegram: на карточке вакансии «💾 Сохранить» → `/saved` показывает заявку в `new`. Кнопками: `applied` → `interview` → раунды «hr», «tech-1» → `offer`. Проверить:
- обратный переход / повтор раунда — вежливый отказ (`IllegalTransition`);
- «🗑» удаляет заявку из любого статуса; повторное «💾» создаёт новую `new`;
- отказ требует этапа (`pre_hr/hr` из applied; `hr/tech/final` из interview);
- «➕ собес»: переслать сообщение → у заявки появились детали, **статус не изменился**.

## 6C — аналитика

```
/stats    # воронка: сколько в каждом статусе + конверсии
/costs    # сумма затрат LLM за период
/review   # 10 скоренных → ваши вердикты → agreement rate
```
Сверка `/costs`: сумма ≈ Langfuse-экспорт за тот же период ±5%. `/review`: ваши расхождения со скорингом дописались в `label` (проверить `select count(*) from labeled_vacancy;` до/после).

## 6D — семантический few-shot (pgvector)

```bash
make migrate                          # 0009 HNSW-индекс
python -m app.scripts.backfill_embeddings   # наполнить embedding историков (идемпотентно)
make eval CONTEXT=relevance           # сравнение: семантический vs «последние N»
```
Отчёт `eval/reports/relevance_<date>.md`: строка семантического селектора — agreement rate/F1 ≥ базового (иначе блок PR).

## 6E — сопроводительные письма

Telegram: на карточке «✉️» → письмо на русском, только факты из резюме, ≤2000 знаков, обращается к вакансии. «🔁» — новая версия; «✏️» — правка; отправка — **вами вручную** (система не шлёт).
```bash
make eval CONTEXT=cover_letter        # hallucinations=0 (блокер) + рубрика
```
🖐 Проверить 5 писем глазами: каждый факт есть в резюме.

## 6F — MCP из Claude Desktop через туннель

```bash
# на VPS роль mcp_ro (ops-скрипт деплоя, разово; пароль из секрета, не в репо):
psql "$POSTGRES_DSN" -v mcp_ro_password="'<secret>'" -f deploy/mcp/create_ro_role.sql
# в .env: MCP_AUTH_TOKEN=<секрет>, MCP_DB_DSN=postgresql+psycopg://mcp_ro:<secret>@db:5432/jobpilot
docker compose --profile mcp run --rm mcp   # stdio; наружу порт не публикуется
```
Claude Desktop → MCP-сервер по SSH-туннелю (stdio), `MCP_AUTH_TOKEN` из `.env` (клиент передаёт его полем `auth_token` в каждом вызове). Проверить:
- read: `list_vacancies`, `search_saved`, `get_costs`, `funnel_stats`, `get_vacancy`;
- write: `set_status` (проходит статусную машину; недопустимый переход отвергнут), `run_digest(dry_run=true)` → дайджест «ТЕСТ», внешних записей нет;
- запрос без токена → отказ; попытка write вне белого списка невозможна (не зарегистрирован).

## 6G — HR-извлечение

Переслать боту реальное сообщение HR о собесе → «➕ собес»: дата/ссылка/суть извлечены в детали заявки, статус прежний.
```bash
make eval CONTEXT=hr_extract          # accuracy по дате и ссылке ≥0.9
```

## 🖐 Закрытие этапа (SC-008)

Первый `/review` (базовый agreement rate) → 5 писем на факты → диалоговый запрос через MCP → подтверждение владельцем.
