# Quickstart: проверка этапа 4 руками

> GetMatch — «лёгкий» источник: публичный JSON `GET /api/offers` через httpx, **без Playwright и без логина**. Исполняется на текущем VPS (1 vCPU / ~1 GB) — апгрейд железа не требуется.

## До подключения (моки)

Пока источник выключен, весь пайплайн работает на моках: `GETMATCH_MODE=fake` отдаёт стаб из `tests/golden/getmatch/offers.json`, сеть не трогается. `make test` гоняет контракт-тесты GetMatch без сети. Дайджест работает на HH-email как раньше.

## Предусловия

В `.env` (источник по умолчанию **выключен** — включаете осознанно):
```
SOURCES=email,getmatch          # добавить getmatch к активным (или GETMATCH_MODE=real)
GETMATCH_API_URL=https://getmatch.ru/api/offers
GETMATCH_USER_AGENT=JobPilot/0.1 (personal-agent; owner-contact)
GETMATCH_REQUEST_PAUSE_SEC=1.0
```
Секретов у источника нет (публичный фид).

## 1. Гейты

```bash
make lint && make test   # unit + contract на golden JSON, миграций у этапа нет
```

## 2. Сбор в DRY_RUN

```bash
DRY_RUN=true make digest   # или /digest в боте
```
Ожидаемо: в тестовом дайджесте («ТЕСТ») — вакансии с источником GetMatch, у каждой title/company/url; открытая вилка отображается, `salary_hidden` — без вилки. Закрытые (`is_active=false`) и непарсенные — не ломают подборку (непарсенное → секция «непарсенное»).

## 3. Изоляция и деградация

- Недоступность/5xx/анти-бот GetMatch → остальные источники (HH-email) собраны, `job_run.status=partial`, эскалация владельцу; **капча/блок не обходятся** (S5).
- offer нового формата → warning-лог + raw-секция, пайплайн жив.

## 4. Eval

```bash
make eval CONTEXT=getmatch_parse   # accuracy title/company/url ≥0.95 ([S-E1])
```

## 5. ToS / robots (решение владельца)

`robots.txt` GetMatch содержит `Disallow: /api/`. JobPilot ходит как ваш персональный агент (1 прогон/сутки, 1 rps, честный User-Agent). Перед боевым включением — ваше явное решение о допустимости (research §2). Обхода блоков система не делает.

## 6. 🖐 Закрытие этапа (canary)

2 дня GetMatch идёт отдельной секцией дайджеста. Сверьте качество на реальных карточках (title/company/url/вилка) → примите ToS-решение → `/approve_scraper getmatch` включает источник в общий поток. При отказе — источник остаётся выключенным, этап помечается отложенным с обоснованием.
