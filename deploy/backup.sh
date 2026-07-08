#!/usr/bin/env bash
# Бэкап/восстановление Postgres JobPilot (X-I2). Ежедневный pg_dump + ротация 14 дней.
#
# Использование:
#   deploy/backup.sh                       # создать дамп в backups/
#   deploy/backup.sh restore <файл.sql.gz> # восстановить БД из дампа
#
# Два режима (выбирается автоматически):
#   1. Прямой: есть pg_dump/psql и задан POSTGRES_DSN — подключение по DSN.
#   2. Docker: pg_dump на хосте нет (типичный VPS: Postgres в контейнере,
#      порт наружу не публикуется) — дамп через `docker compose exec db`.
#      Принудительно: USE_DOCKER=1.
#
# На VPS ставится в cron ежедневно; ротация удаляет дампы старше 14 дней.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

use_docker() {
  [[ "${USE_DOCKER:-}" == "1" ]] && return 0
  ! command -v pg_dump >/dev/null 2>&1
}

pg_url() {
  local dsn="${POSTGRES_DSN:?нужен POSTGRES_DSN (или установите USE_DOCKER=1)}"
  # pg_dump/psql понимают libpq-URL; убираем SQLAlchemy-суффикс драйвера.
  dsn="${dsn/+psycopg/}"
  echo "${dsn/+asyncpg/}"
}

mkdir -p "$BACKUP_DIR"

cmd="${1:-backup}"

if [[ "$cmd" == "restore" ]]; then
  FILE="${2:?укажите файл дампа}"
  echo "→ Восстановление из $FILE"
  if use_docker; then
    gunzip -c "$FILE" | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
  else
    gunzip -c "$FILE" | psql "$(pg_url)"
  fi
  echo "✅ Восстановление завершено"
  exit 0
fi

# Дата берётся из системы во время запуска (cron/ручной), не хардкодится.
STAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT="$BACKUP_DIR/jobpilot_${STAMP}.sql.gz"
echo "→ Дамп в $OUT"
if use_docker; then
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$OUT"
else
  pg_dump "$(pg_url)" | gzip > "$OUT"
fi

echo "→ Ротация: удаляю дампы старше ${RETENTION_DAYS} дней"
find "$BACKUP_DIR" -name 'jobpilot_*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

echo "✅ Бэкап готов: $OUT"
