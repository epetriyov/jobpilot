# Quickstart: проверка этапа 1 руками

> Пересмотр 2026-07-17: основной источник HH — **email** (письма «Вакансии по подписке» из Gmail). userbot и web заблокированы (см. research.md); до подключения Gmail всё работает на моках (`HH_MODE=auto` без доступа → fake).

## Предусловия для реального HH (данные владельца; до них — моки)

1. **email** (основной путь): подписаться на рассылку вакансий на hh.ru (письма «Вакансии по подписке» приходят на почту) и подключить Gmail этапа 2 (`GMAIL_CLIENT_ID`/`GMAIL_CLIENT_SECRET`/`GMAIL_REFRESH_TOKEN`, см. `app.cli.oauth_gmail`). `HH_SOURCES=email` (дефолт) → `resolved_hh_mode`=real. Больше ничего не нужно: ни браузера, ни второго аккаунта.
2. _(опционально, если каналы разблокируются)_ **userbot** — my.telegram.org → `HH_USERBOT_API_ID/API_HASH` + `app.cli.login_userbot`; **web-профиль** — `app.cli.hh_login` (ручной вход, капчу решаете вы) + `HH_RESUME_URL`; образ с Chromium `INSTALL_BROWSERS=true docker compose build`. Добавить нужные адаптеры в `HH_SOURCES` (`email,telegram,web`).
3. DRY_RUN=true (боевое поднятие включается только в п.7).

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
Ожидаемо: подборка «🧪 ТЕСТ» ≤50 карточек из писем HH «Вакансии по подписке», скор по убыванию, у каждой 👍/👎/🔗; при повторном /digest те же вакансии не приходят.

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
