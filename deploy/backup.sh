#!/usr/bin/env bash
# Бэкап/восстановление Postgres JobPilot (X-I2). Ежедневный pg_dump + ротация 14 дней.
#
# Использование:
#   deploy/backup.sh                       # создать дамп в backups/
#   deploy/backup.sh restore <файл.sql.gz> # восстановить БД из дампа
#
# Режим — BACKUP_MODE (по умолчанию auto):
#   compose       — через `docker compose exec db` (штатный случай VPS/локали:
#                   Postgres в compose, порт наружу не публикуется).
#   direct        — pg_dump/psql хоста по POSTGRES_DSN (нужен установленный клиент).
#   client-docker — клиент в одноразовом контейнере postgres:16-alpine по POSTGRES_DSN
#                   (localhost в DSN переписывается на host.docker.internal).
#   auto          — compose, если сервис db запущен; иначе direct при наличии pg_dump;
#                   иначе client-docker. USE_DOCKER=1 — синоним BACKUP_MODE=compose.
#
# На VPS ставится в cron ежедневно; ротация удаляет дампы старше 14 дней.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
CLIENT_IMAGE="${CLIENT_IMAGE:-postgres:16-alpine}"

MODE="${BACKUP_MODE:-auto}"
[[ "${USE_DOCKER:-}" == "1" ]] && MODE="compose"

pg_url() {
  local dsn="${POSTGRES_DSN:?нужен POSTGRES_DSN для режима $1}"
  # pg_dump/psql понимают libpq-URL; убираем SQLAlchemy-суффикс драйвера.
  dsn="${dsn/+psycopg/}"
  echo "${dsn/+asyncpg/}"
}

docker_url() {
  # изнутри контейнера localhost хоста доступен как host.docker.internal
  local url
  url="$(pg_url client-docker)"
  url="${url/@localhost/@host.docker.internal}"
  echo "${url/@127.0.0.1/@host.docker.internal}"
}

compose_db_running() {
  command -v docker >/dev/null 2>&1 \
    && docker compose ps --status running --services 2>/dev/null | grep -qx db
}

if [[ "$MODE" == "auto" ]]; then
  if compose_db_running; then
    MODE="compose"
  elif command -v pg_dump >/dev/null 2>&1 && [[ -n "${POSTGRES_DSN:-}" ]]; then
    MODE="direct"
  elif command -v docker >/dev/null 2>&1 && [[ -n "${POSTGRES_DSN:-}" ]]; then
    MODE="client-docker"
  else
    echo "❌ Не найден способ подключения: нет запущенного compose-сервиса db," >&2
    echo "   нет pg_dump на хосте и/или не задан POSTGRES_DSN." >&2
    exit 1
  fi
fi
echo "→ Режим: $MODE"

dump_cmd() {
  case "$MODE" in
    compose) docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' ;;
    direct) pg_dump "$(pg_url direct)" ;;
    client-docker)
      docker run --rm --add-host=host.docker.internal:host-gateway \
        "$CLIENT_IMAGE" pg_dump "$(docker_url)"
      ;;
    *) echo "❌ Неизвестный BACKUP_MODE: $MODE" >&2; exit 1 ;;
  esac
}

restore_cmd() {
  case "$MODE" in
    compose) docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' ;;
    direct) psql "$(pg_url direct)" ;;
    client-docker)
      docker run -i --rm --add-host=host.docker.internal:host-gateway \
        "$CLIENT_IMAGE" psql "$(docker_url)"
      ;;
    *) echo "❌ Неизвестный BACKUP_MODE: $MODE" >&2; exit 1 ;;
  esac
}

mkdir -p "$BACKUP_DIR"

cmd="${1:-backup}"

if [[ "$cmd" == "restore" ]]; then
  FILE="${2:?укажите файл дампа}"
  echo "→ Восстановление из $FILE"
  gunzip -c "$FILE" | restore_cmd
  echo "✅ Восстановление завершено"
  exit 0
fi

# Дата берётся из системы во время запуска (cron/ручной), не хардкодится.
STAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT="$BACKUP_DIR/jobpilot_${STAMP}.sql.gz"
echo "→ Дамп в $OUT"
dump_cmd | gzip > "$OUT"

echo "→ Ротация: удаляю дампы старше ${RETENTION_DAYS} дней"
find "$BACKUP_DIR" -name 'jobpilot_*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

echo "✅ Бэкап готов: $OUT"
