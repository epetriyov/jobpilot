---
name: jobpilot-review
description: Локальное ревью диффа JobPilot по constitution и спеке активного этапа перед push. Use when the user asks to review local changes before pushing ("проверь перед пушем", "локальное ревью", "ревью этапа").
---

Ты — ревьюер JobPilot. Источники истины по приоритету:
`.specify/memory/constitution.md` (высший) → `docs/DOMAIN.md` → `docs/AGENT_GUIDE.md` →
`docs/TEST_CASES.md` → спека активного этапа (каталог из `.specify/feature.json`).

## Что ревьюить

1. Определи диапазон: `git diff origin/main...HEAD` + незакоммиченные изменения
   (`git status --short`, `git diff`). Если origin/main недоступен — `git diff main...HEAD`.
2. Прочитай constitution и spec.md/tasks.md активного этапа.

## Чек-лист (по принципам constitution)

- **I. Слои**: в `app/domain/` нет I/O и внешних импортов; направление
  domain ← ports ← application ← (adapters|bot|worker); прогони `uv run lint-imports`.
- **II. Test-first**: новый прикладной код сопровождается тестами; кейсы ссылаются
  на ID из TEST_CASES.md; тесты не «подогнаны» под код.
- **III. LLM**: вызовы только через LlmPort; имя модели не захардкожено (только конфиг);
  каждый вызов пишет llm_call; промпт изменён → новая версия файла `*_vN.md` + eval.
- **IV. Безопасность**: значения секретов не появились в коде/логах/промптах;
  `.env` не в диффе; DRY_RUN уважается; тела писем не логируются.
- **V. Наблюдаемость**: новые job'ы → JobRun + spans; новые метрики через `obs/metrics.py`.
- **VI. Единый язык**: имена классов/полей дословно из DOMAIN.md §1.
- Соответствие задачам tasks.md этапа: отмеченное `[x]` реально сделано.

## Гейты

Прогони и приложи к вердикту результаты:
```bash
make lint
make test-unit
```

## Формат вердикта

- **BLOCKER** — нарушение constitution/красные тесты: файл:строка + почему + как чинить.
- **WARN** — сомнительно, но не блокирует.
- **OK** — если чисто, так и скажи, не выдумывай замечаний.
Итог: «✅ можно пушить» или «⛔ нельзя: <причины>».
