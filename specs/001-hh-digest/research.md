# Research: Вся работа с HH (Этап 1)

## 1. HH API: доступ и OAuth

- **Decision**: авторизация OAuth2 authorization code. Владелец регистрирует приложение на dev.hh.ru (client_id/client_secret) — данные вводятся в CLI-хелпер `python -m app.cli.oauth_hh`: хелпер открывает URL авторизации, принимает redirect с кодом (локальный порт/ручная вставка кода), меняет код на access+refresh token и печатает строки для .env (`HH_CLIENT_ID`, `HH_CLIENT_SECRET`, `HH_REFRESH_TOKEN`). Access token хранится только в памяти процесса; при 401 — refresh и один повтор ([S-C2]). Требование HH: заголовок `HH-User-Agent` с именем приложения и контактом — берём из конфига.
- **Rationale**: refresh token долгоживущий; система само-обслуживается без владельца; правило PLAN §7 п.4 — креды не выдумываем, получает владелец через хелпер.
- **Alternatives**: app-token без пользователя (не даёт negotiations/избранное — отвергнуто); ручной ввод access token (протухает за часы — отвергнуто).

## 2. Эндпоинты и маппинг

- `GET /vacancies?text=<query>&search_field=name&per_page=50&order_by=publication_time` по каждому EM-запросу конфига; пагинация до разумного лимита (конфиг, по умолчанию 2 страницы/запрос).
- `GET /vacancies/{id}/similar_vacancies` для вакансий из `GET /negotiations` (отклики) и `GET /resumes/mine` избранного — по наличию ([S-C4]).
- Полный текст: `GET /vacancies/{id}` (search-выдача содержит только snippet) — дозапрос только для НЕ виденных вакансий (экономия квоты).
- `POST /resumes/{resume_id}/publish` — поднятие; 429/`{"errors":[{"type":"resumes","value":"touch_limit_exceeded"}]}` → штатный skip ([S-C3]). resume_id владелец выбирает в хелпере (`GET /resumes/mine`).
- `GET /negotiations?order_by=updated_at` + непрочитанные сообщения за 24ч → секция дайджеста.
- **Маппинг** ([S-C1]): id→SourceRef(hh, external_id), name→title, employer.name→company, alternate_url→url, salary{from,to,currency}→Salary (все опциональны), snippet/description→description_raw (HTML чистится доменом S3), area.name→location.

## 3. Скор и R1 (не скорить повторно)

- **Decision**: скор храним рядом с реестром seen (миграция 0002: колонки score, score_reason, prompt_version, model, scored_at в seen_vacancy, NULL для нескоренных) + снапшот title/company/url/description_text (для разметки из карточки и построения labeled_vacancy без похода в HH).
- **Rationale**: минимальный слой хранения (DOMAIN §4) не расширяется новой сущностью; R1 — простой WHERE prompt_version; разметка старой карточки работает даже если вакансия удалена с HH (edge case спеки). Полное `vacancy` — этап 6, seen остаётся «реестром виденных + рабочие поля этапа».
- **Alternatives**: отдельная таблица score (нормальнее, но это шаг к полному vacancy — целево на этапе 6); скор только в памяти (теряем R1 между прогонами — отвергнуто).

## 4. Карточки и колбэки

- **Decision**: карточка = отдельное сообщение с InlineKeyboard (👍 `label:relevant:<ref>`, 👎 `label:irrelevant:<ref>`, 🔗 URL-кнопка). Колбэк → use case LabelVacancy: upsert labeled_vacancy по source_ref (повторное нажатие обновляет вердикт), ответ — `answerCallbackQuery` («Записал 👍») + смена разметки кнопок. callback_data ≤64 байта — используем `hh:<external_id>`.
- **Alternatives**: один длинный дайджест-пост (нельзя кнопки на вакансию); reply-клавиатура (замусоривает чат).

## 5. Few-shot «последние N»

- R3: до 10 последних labeled_vacancy (уже есть `LabelRepository.recent(10)`); формат примера: усечённый текст вакансии (лимит конфиг, 800 знаков) → assistant-ответ `{"score": 85, "reason": "..."}` для 👍 (score-якорь 85) и `{"score": 15, ...}` для 👎. Семантический подбор — этап 6 (R3).

## 6. Eval `relevance` и сравнение моделей

- **Decision**: каждая разметка 👍/👎 дописывает строку в `eval/datasets/relevance/v1.jsonl` (`{"id": source_ref, "input": {"vacancy_text": ...}, "expected": {"verdict": relevant|irrelevant}}`) — append-only, дубликаты по id игнорируются при прогоне (последний вердикт побеждает).
- Раннер: прогоняет скоринг по датасету (реальная модель локально; в CI — записанные ответы), verdict = score ≥ порога; метрики precision/recall/F1; пороги ≥0.7 — assertions ([R-E1]).
- Сравнение моделей: `make eval CONTEXT=relevance MODEL_B=google/gemini-2.5-flash` — прогон обеих, отчёт с ΔF1; критерий «незначимо» — |ΔF1| ≤ 0.05 (порог регресса из [R-E1]) → остаёмся на Lite.
- **Rationale**: датасет и разметка — один поток данных; CI без ключей — записанные ответы как в [R-C2].

## 7. Расписание

- daily_digest: cron 10:00 Europe/Moscow (worker, run_job). publish_resume: interval 4h, тоже через run_job — статусы job_run видны в Grafana; 429 → items_out=0 + метрика publish_skipped, статус success.
- `/digest`, `/publish` — те же use cases из бота (без дублирования логики).

## 8. Секреты

- Новые env: `HH_CLIENT_ID`, `HH_CLIENT_SECRET`, `HH_REFRESH_TOKEN`, `HH_RESUME_ID`, `HH_USER_AGENT`; `HH_CLIENT_SECRET`/`HH_REFRESH_TOKEN` — SecretStr, добавляются в `secret_values()` (санитайзер логов [X-U1] закрывает их автоматически).

---

## Пересмотр источников (2026-07-15): API → userbot + web-scrape

**Причина**: HH API для проекта недоступен (нет доступа к выдаче рекомендаций через API). Данные берём двумя способами, оба за существующим `VacancySourcePort` — домен, дедуп, скоринг, дайджест не меняются.

### Источник 1 — HH-бот в Telegram (userbot, Telethon)
- Официальный HH-бот шлёт вакансии в личку. Читаем **входящие сообщения** userbot'ом на втором аккаунте (Telethon). Это чтение своих сообщений, не скрейп сайта HH — низкий ToS-риск. Инфраструктура общая с GetMatch (этап 4): userbot-контейнер выносится вперёд.
- `HhTelegramSource(VacancySourcePort)`: парс сообщений бота → VacancyDTO (title/company/url регулярками по формату); непарсенное → raw-секция ([S-C4]/S-C6). Golden — записанные тексты сообщений.
- Доступ: `HH_USERBOT_API_ID/API_HASH` (my.telegram.org) + разовый вход по коду → session-файл (CLI `login_userbot`).

### Источник 2 — рекомендации с сайта (Playwright)
- Playwright + Chromium по **авторизованной сессии** (сохранённый браузер-профиль в volume). Владелец один раз входит вручную через headful-хелпер `hh_login` (и решает капчу, если будет); дальше переиспользуются куки.
- `HhWebSource(VacancySourcePort)`: страница рекомендаций → карточки → VacancyDTO; 1 rps, честный User-Agent; golden — HTML-снапшоты, изменение структуры ловится diff-тестом ([S-C1]/[S-C2]).
- Капча/логин-стена в рабочем прогоне → `SourceFetchFailed(hh_web)` + эскалация владельцу, **без обхода капчи** (S5, constitution IV). Автоматический ввод логина/пароля не делается — только ручной вход в профиль.

### Поднятие резюме — Playwright-клик (API нет)
- `HhWebPublisher(PublisherPort)`: открыть резюме, нажать «поднять»; лимит «ещё рано» → publish_skipped (не ошибка, [S-C3]); DRY_RUN → клик не выполняется. Осознанное решение владельца (2026-07-15): авто-запись на сайт; каждое действие логируется.

### Зависимости и контейнеры
- Новые пакеты: `telethon` (userbot), `playwright` (+ `playwright install chromium`). Playwright тяжёлый (~1 ГБ) — отдельный сервис `scraper`, чтобы не раздувать bot; userbot — сервис `userbot`. VPS: повод для 4 ГБ RAM.
- Тесты без живого HH: userbot — golden текстов (respx не нужен, парсинг чистый); web — Playwright против сохранённого HTML (file://), не против живого сайта; CI без сети и кредов.
