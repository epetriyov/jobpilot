-- Read-роль Postgres для MCP-сервера (этап 6F, MCP4, [P-I1]).
-- Инфраструктурный шаг (CREATE ROLE/GRANT), НЕ миграция alembic: выполняется
-- ops-скриптом деплоя один раз. Read-инструменты MCP ходят под этой ролью
-- (MCP_DB_DSN), поэтому любая запись мимо белого списка write упирается в отказ
-- прав БД — второй рубеж поверх реестра инструментов (MCP2).
--
-- Применение (пароль передаётся из секрета окружения, не хранится в репозитории):
--   psql "$POSTGRES_DSN" -v mcp_ro_password="'<secret>'" -f deploy/mcp/create_ro_role.sql
-- затем MCP_DB_DSN = postgresql+psycopg://mcp_ro:<secret>@host:5432/jobpilot

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_ro') THEN
        CREATE ROLE mcp_ro LOGIN PASSWORD :mcp_ro_password;
    END IF;
END
$$;

-- Только чтение: доступ к схеме и всем текущим/будущим таблицам, без INSERT/UPDATE/DELETE.
GRANT CONNECT ON DATABASE jobpilot TO mcp_ro;
GRANT USAGE ON SCHEMA public TO mcp_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_ro;

-- Явный запрет записи (на случай ранее выданных прав).
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM mcp_ro;
