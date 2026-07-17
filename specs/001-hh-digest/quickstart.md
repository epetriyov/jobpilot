# Quickstart: проверка этапа 1 руками

> Пересмотр 2026-07-15: API HH недоступен. Источники — userbot HH-бота (Telethon) + web-скрейпер (Playwright). До подключения всё работает на моках (`HH_MODE=auto` без доступа → fake).

## Предусловия для реального HH (данные владельца; до них — моки)

1. **userbot** (второй Telegram-аккаунт, подписанный на HH-бота):
   - my.telegram.org → `HH_USERBOT_API_ID`, `HH_USERBOT_API_HASH` в `.env`;
   - `uv run python -m app.cli.login_userbot` → вход по номеру+коду → session-файл.
2. **web-профиль** (рекомендации + поднятие резюме):
   - `uv run python -m app.cli.hh_login` → откроется браузер → войти на hh.ru руками (капчу решаете вы; система не обходит) → профиль сохранён;
   - `HH_RESUME_URL` в `.env` — ссылка на резюме для поднятия.
3. Образ с Chromium (только для web на VPS): `INSTALL_BROWSERS=true docker compose build`.
4. DRY_RUN=true (боевое поднятие включается только в п.7).

## 1. Гейты

```bash
make lint && make test          # разделы 1–2 TEST_CASES зелёные
make migrate                    # 0002_stage1 применяется идемпотентно
```

## 2. Дайджест в DRY_RUN

```bash
docker compose up -d --build
# в Telegram: /digest
```
Ожидаемо: подборка «🧪 ТЕСТ» ≤50 карточек с реального поиска HH, скор по убыванию, у каждой 👍/👎/🔗; при повторном /digest те же вакансии не приходят.

## 3. Разметка и /train

- Нажать 👍 на 2–3 релевантных и 👎 на паре мусорных → бот подтверждает.
- `/train` → счётчик «размечено X (👍 a / 👎 b), до цели 30 осталось Y».
- Проверка few-shot: следующие скоринги в логах имеют fewshot_size > 0.

## 4. Publish и 429

```bash
# в Telegram: /publish
```
- DRY_RUN: «поднятие пропущено (ТЕСТ)».
- Боевой (после п.7): первое — «поднято»; повторное сразу — «лимит HH, следующий слот в HH:MM» (не ошибка, job_run success, метрика publish_skipped).

## 5. Секция «Переписка HH»

При наличии непрочитанных сообщений в HH секция в дайджесте со ссылками на диалоги; без сообщений секции нет.

## 6. Eval relevance (после ≥30 размеченных)

```bash
make eval CONTEXT=relevance
# сравнение моделей:
make eval CONTEXT=relevance MODEL_B=google/gemini-2.5-flash
```
- precision ≥0.7 и recall ≥0.7 (иначе FAIL);
- отчёт `eval/reports/relevance_<дата>.md` + сравнение ΔF1 закоммичены; |ΔF1| ≤ 0.05 → остаёмся на Flash-Lite.

## 7. Канареечный период и включение боевого режима

- 3 дня подряд дайджест в 10:00 приходит без падений (job_run success/partial, алертов нет).
- Разметка ≥30 достигнута, eval пройден.
- Владелец переключает `DRY_RUN=false` в `.env` на VPS → `docker compose up -d` → этап закрыт ручным подтверждением.

## Дашборд

На дашборде этапа 0 наполняются: Job-прогоны (daily_digest, publish_resume), Вакансии по источникам (hh), LLM-токены/стоимость (purpose=scoring).
