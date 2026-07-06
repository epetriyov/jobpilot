# DOMAIN.md — доменная модель JobPilot (DDD)

> Источник истины о предметной области. Любой coding-агент обязан прочитать этот файл до написания кода и обновлять его при уточнении домена. Термины единого языка используются в коде дословно (англ. эквиваленты в скобках — имена классов/полей).

---

## 1. Единый язык (Ubiquitous Language)

| Термин | Код | Определение |
|---|---|---|
| Вакансия | `Vacancy` | Объявление о работе из любого источника. Уникальна в рамках (source, site_name, external_id). |
| Источник | `Source` | Откуда пришла вакансия: `hh`, `getmatch`, `site` (+имя сайта), `manual`. |
| Обнаружение | `VacancyDiscovered` | Первое появление вакансии в системе (после дедупликации). |
| Скор | `Score` | Оценка релевантности 0–100 относительно резюме EM + причина (`reason` ≤200 знаков) + `prompt_version`. |
| Разметка | `Label` | Ручной вердикт пользователя: `relevant` (👍) / `irrelevant` (👎). Топливо для few-shot и eval. |
| Дайджест | `Digest` | Ежедневная подборка (10:00 МСК): карточки вакансий + секции «Почта», «LinkedIn», «На проверку» (canary). |
| Карточка | — | Представление вакансии в Telegram с кнопками. UI-термин, не доменная сущность. |
| Отклик-заявка | `Application` | Сохранённая пользователем вакансия, движущаяся по воронке. Агрегат CRM. |
| Воронка | `Funnel` | Последовательность статусов Application. |
| Статус | `ApplicationStatus` | `new` → `applied` → `interview` → `offer` \| `rejected`. |
| Раунд собеса | `InterviewRound` | Упорядоченный этап внутри `interview`: `hr`, `tech-1`, `tech-2`, …, `final`. |
| Этап отказа | `RejectStage` | Где случился отказ: `pre_hr`, `hr`, `tech`, `final`. |
| Поднятие | `ResumePublish` | Публикация резюме в HH (раз в 4 часа) и «поднятие» в GetMatch (раз в день). |
| Входящее письмо | `InboxMessage` | Письмо/сообщение о работе из Gmail или переписки HH. Имеет summary. |
| Сопроводительное | `CoverLetter` | Сгенерированное письмо под конкретную вакансию. Содержит только факты из резюме. |
| Заготовка инвайта | `InviteDraft` | Персона (роль+компания) + текст инвайта + search-URL. Статусы: `proposed` → `sent` → `accepted`. |
| Прогон задачи | `JobRun` | Запись о запуске планового job: статус, ошибки, счётчики, trace_id. |
| Вызов LLM | `LlmCall` | Учётная запись обращения к LLM: модель, prompt_version, токены, стоимость, латентность. |
| Минимальный слой хранения | — | Этапы 0–5: только `seen_vacancy` (дедуп), `labeled_vacancy` (снапшоты размеченных 👍/👎 для few-shot), `llm_call`, `job_run`. Полное хранилище вакансий и `Application` — финальная фича (этап 6). |
| MCP-инструмент | MCP tool | Функция MCP-сервера поверх use case (read по умолчанию, write — по белому списку) для диалогового доступа к системе из Claude Desktop/Code. |
| Сухой прогон | `DRY_RUN` | Режим: пайплайн выполняется полностью, внешние записи (publish, боевой дайджест) не производятся, дайджест помечен «ТЕСТ». |
| Канарейка | canary | Новый источник 2–3 дня шлёт результаты отдельной секцией до явного одобрения `/approve_scraper`. |
| Согласие | agreement rate | Доля совпадений вердиктов пользователя (из `/review`) с решениями скоринга. Главная метрика качества подбора. |

## 2. Карта контекстов (Context Map)

```
                    ┌────────────────────┐
   HH / GetMatch /  │      SOURCING      │  VacancyDiscovered
   Site adapters ──▶│  вакансии, дедуп   │────────┐
                    └────────────────────┘        ▼
                    ┌────────────────────┐  ┌───────────────┐
   Gmail / HH msgs ▶│  CORRESPONDENCE    │  │   RELEVANCE   │ Score, Label,
                    │ inbox + cover ltr  │  │ скоринг, eval │ few-shot
                    └────────────────────┘  └───────┬───────┘
                    ┌────────────────────┐          ▼ VacancyScored
   LinkedIn (semi) ▶│    NETWORKING      │  ┌───────────────┐
                    │  invite drafts     │  │  DELIVERY(UI) │ Digest, карточки,
                    └────────────────────┘  │ bot+scheduler │ команды
                    ┌────────────────────┐  └───────┬───────┘
                    │        CRM         │◀─────────┘ VacancySaved
                    │ Application funnel │
                    └────────────────────┘
   Shared kernel: Vacancy(id), Money/Salary, PromptVersion, TraceId, DomainEvent
   Generic subdomain: OBSERVABILITY (JobRun, LlmCall, OTel, Langfuse)
```

Отношения: Sourcing → Relevance → Delivery — конвейер (upstream/downstream, контракт `Vacancy`); CRM — downstream от Delivery (customer/supplier); Correspondence и Networking — независимые контексты, публикуют секции в Digest.

## 3. Контексты: агрегаты, инварианты, события, порты

### 3.1 SOURCING
**Агрегат** `Vacancy` (root). VO: `SourceRef(source, site_name?, external_id)`, `Salary(from?, to?, currency?)` — все поля опциональны (вилка публикуется не везде).
**Инварианты:**
- S1. Уникальность по `SourceRef`: повторное обнаружение не создаёт дубликат.
- S2. Кросс-источниковый дедуп: нормализованная пара (company, title) уже видена за 30 дней → пометка `duplicate_of`, в дайджест не идёт.
- S3. `description_text` очищен от HTML; `raw` хранит оригинал.
- S4. Падение одного адаптера-источника не прерывает сбор из остальных.
**События:** `VacancyDiscovered`, `SourceFetchFailed(source, error)`.
**Порты:** `VacancySourcePort.fetch() -> list[VacancyDTO]` (реализации: hh, getmatch, 7 sites), `VacancyRepositoryPort`.

### 3.2 RELEVANCE
**Сущности/VO:** `Score(value 0..100, reason, prompt_version, model)`, `Label(verdict, embedding)`.
**Инварианты:**
- R1. Скорится только вакансия без актуального скора текущей prompt_version (пересчёт — явной командой).
- R2. Выход LLM валидируется схемой `{score:int 0..100, reason:str<=200}`; невалидный → 1 retry → skip с логом уровня warning (пайплайн не падает).
- R3. Few-shot: до 10 примеров из Label; при <10 размеченных — все имеющиеся; при наличии pgvector-эмбеддингов — семантический подбор ближайших (этап 6), иначе последние N.
- R4. В дайджест попадают score ≥ threshold (конфиг, 60) в порядке убывания, максимум 50.
- R5. Тексты вакансий — недоверенные данные: оборачиваются в промпте как данные, не инструкции.
**События:** `VacancyScored`, `LabelAdded`.
**Порты:** `LlmPort.score(profile, fewshot, vacancy_text) -> Score`, `EmbeddingPort`, `LabelRepositoryPort`.

### 3.3 CRM
**Агрегат** `Application` (root): vacancy_id, status, interview_rounds[], reject_stage?, interview_url?, notes.
**Статусная машина (единственный источник истины):**
```
new ──▶ applied ──▶ interview ──▶ offer        (терминальный)
 │         │            │
 └────────▶└───────────▶└───────▶ rejected(stage) (терминальный)
interview: раунды строго по возрастанию (hr → tech-1 → tech-2 → … → final),
           добавление раунда допустимо только в статусе interview.
rejected: stage обязателен; из new/applied stage ∈ {pre_hr, hr}; из interview — {hr, tech, final}.
Переходы назад запрещены; удаление Application допустимо из любого статуса (это не переход).
```
**Инварианты:** C1. Один активный Application на вакансию. C2. Недопустимый переход → доменная ошибка `IllegalTransition`, состояние не меняется. C3. Извлечение из пересланного сообщения HR (дата/ссылка/суть) только дополняет `interview_url/notes`, никогда не меняет статус автоматически.
**События:** `VacancySaved`, `StatusChanged(from, to)`, `InterviewScheduled`.

### 3.4 CORRESPONDENCE
**Сущности:** `InboxMessage(source: gmail|hh|linkedin_gmail, subject, summary, url, received_at)`, `CoverLetter(vacancy_id, text, prompt_version)`.
**Инварианты:**
- M1. Классификация «про работу?» — сначала эвристика (домены/ключевые слова), LLM только для прошедших префильтр (экономия токенов).
- M2. Summary ≤ 2 строк, содержит действие/суть (кто, о чём, что требуется).
- M3. CoverLetter (реализуется в финальной фиче, этап 6): русский язык; каждый факт присутствует в резюме EM (hallucination-check в eval); отправка — только вручную пользователем.
- M4. Тела писем не пишутся в логи.
**События:** `InboxDigestReady`, `CoverLetterGenerated`.
**Порты:** `InboxPort.fetch_since(dt)`, `LlmPort.classify_and_summarize`, `LlmPort.generate_letter`.

### 3.5 NETWORKING
**Агрегат** `InviteDraft(title, company, search_url, invite_text, status)`.
**Инварианты:** N1. Только полуавтомат: система никогда не отправляет инвайты и не читает LinkedIn напрямую. N2. invite_text ≤ 300 знаков, персонализирован (роль+компания), без штампов. N3. Статусы только вперёд: proposed → sent → accepted.
**События:** `InviteBatchReady` (еженедельно).

### 3.6 OBSERVABILITY (generic)
`JobRun` — каждый плановый запуск: имя, статус, items_in/out, error, trace_id. `LlmCall` — каждый вызов LLM: purpose(scoring|letter|summary|extract|judge), model, prompt_version, input/output tokens, cost_usd, latency_ms, trace_id. Инвариант O1: нет LLM-вызова без записи `LlmCall` и трейса Langfuse. O2: каждый этап use case = OTel child span.

### 3.7 MCP-СЕРВЕР (интерфейсный слой, этап 6)
Не отдельный домен — второй интерфейс (наряду с ботом) поверх тех же use cases из `application/`.
**Инварианты:** MCP1. Инструменты вызывают только use cases — никакого прямого SQL. MCP2. Write-инструменты — исчерпывающий белый список: `set_status`, `run_digest(dry_run)`; всё остальное read-only. MCP3. Обязательный auth-токен; доступ только localhost/SSH-туннель. MCP4. Отдельная ограниченная роль Postgres; нулевой доступ к секретам интеграций.

## 4. Модель данных (Postgres)

**Этапы 0–5 (минимальный слой):** `seen_vacancy(source_ref unique, content_hash, first_seen_at, digest_sent_at)` — дедуп и защита от повторов; `labeled_vacancy(id, source_ref, title, company, url, description_text, verdict, embedding vector(768), created_at)` — снапшоты размеченных для few-shot и eval; `inbox_message`; `linkedin_target`; `job_run`; `llm_call`.
**Этап 6 (финальная фича):** полное `vacancy` (поля агрегата §3.1 + `raw jsonb`, `duplicate_of`, `canary bool`; миграция: seen/labeled переезжают поверх), `application` (+child `interview_round`), `cover_letter`. Время в БД — UTC. Миграции — Alembic, по одной на этап.

## 5. Как расширять домен (для будущих агентов)

- Новый источник вакансий = новый адаптер `VacancySourcePort` + golden-тесты + canary. Домен Sourcing не меняется.
- Новый статус воронки = изменение статусной машины §3.3 + property-тесты переходов + миграция enum. Сначала обнови этот файл.
- Новая LLM-задача = новый метод `LlmPort` + версия промпта + датасет в `eval/datasets/` + метрика в раннере. Без датасета фича не считается готовой.
- Смена LLM-провайдера = новый instructor-адаптер `LlmPort` + конфиг + полный eval-прогон всех контекстов; домен и use cases не трогаются.
- Новый MCP-инструмент = обёртка над существующим use case; write-инструмент — только через явное расширение белого списка (MCP2) с тестом.
