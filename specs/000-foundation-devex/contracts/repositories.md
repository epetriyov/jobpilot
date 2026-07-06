# Contract: Repository-порты (этап 0)

Интерфейсы в `app/ports/repositories.py` (Protocol); реализации — `app/adapters/persistence/`. Домен про них не знает; application получает их через DI (конструктор use case).

## SeenVacancyRepositoryPort

- `async is_seen(ref: SourceRef) -> bool`
- `async mark_seen(vacancy: Vacancy) -> None` — идемпотентно: повторный вызов не меняет `first_seen_at` (S1)
- `async find_duplicate(normalized_key: str, within_days: int = 30) -> str | None` — source_ref оригинала для S2
- `async mark_digest_sent(refs: Sequence[SourceRef], at: datetime) -> None`

## LabelRepositoryPort

- `async add(labeled: LabeledVacancy) -> None`
- `async recent(limit: int = 10) -> list[LabeledVacancy]` — few-shot «последние N» (R3)

## LlmCallRepositoryPort

- `async record(call: LlmCallRecord) -> None` — вызывается адаптерами LlmPort (O1)

## JobRunRepositoryPort

- `async start(job_name: str, trace_id: str) -> int` — создаёт запись status=running
- `async finish(run_id: int, *, status: Literal["success","partial","error"], items_in: int, items_out: int, error: str | None) -> None` — [F-I3]

## Гарантии

- Все таймстемпы — UTC.
- Реализации не выбрасывают доменные типы наружу — конверсия ORM ↔ домен внутри адаптера.
- Integration-тесты гоняются на реальном Postgres (testcontainers) после `alembic upgrade head` ([F-I1]).
