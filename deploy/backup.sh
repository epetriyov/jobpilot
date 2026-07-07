#!/usr/bin/env bash
# Бэкап/восстановление Postgres JobPilot (X-I2). Ежедневный pg_dump + ротация 14 дней.
#
# Использование:
#   deploy/backup.sh                       # создать дамп в backups/
#   deploy/backup.sh restore <файл.sql.gz> # восстановить на БД из POSTGRES_DSN
#
# Требуется: POSTGRES_DSN (postgresql://user:pass@host:port/db) в окружении.
# На VPS ставится в cron ежедневно; ротация удаляет дампы старше 14 дней.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DSN="${POSTGRES_DSN:?нужен POSTGRES_DSN}"

# pg_dump/psql понимают libpq-URL; убираем SQLAlchemy-суффикс драйвера.
PG_URL="${DSN/+psycopg/}"
PG_URL="${PG_URL/+asyncpg/}"

mkdir -p "$BACKUP_DIR"

cmd="${1:-backup}"

if [[ "$cmd" == "restore" ]]; then
  FILE="${2:?укажите файл дампа}"
  echo "→ Восстановление из $FILE"
  gunzip -c "$FILE" | psql "$PG_URL"
  echo "✅ Восстановление завершено"
  exit 0
fi

# Дата берётся из системы во время запуска (cron/ручной), не хардкодится.
STAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT="$BACKUP_DIR/jobpilot_${STAMP}.sql.gz"
echo "→ Дамп в $OUT"
pg_dump "$PG_URL" | gzip > "$OUT"

echo "→ Ротация: удаляю дампы старше ${RETENTION_DAYS} дней"
find "$BACKUP_DIR" -name 'jobpilot_*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

echo "✅ Бэкап готов: $OUT"
