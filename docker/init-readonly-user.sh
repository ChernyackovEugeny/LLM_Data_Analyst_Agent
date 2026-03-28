#!/bin/bash
# =============================================================
# Init script: создание read-only роли для SQL-инструмента агента.
# Запускается автоматически postgres:16-alpine при ПЕРВОМ старте
# (пустой postgres_data volume), выполняется от имени POSTGRES_USER.
#
# Пароль читается из переменной окружения READONLY_DB_PASSWORD —
# она передаётся через docker-compose.yml из .env.
# Файл не содержит секретов и безопасен для коммита в git.
#
# Для существующих деплоев (volume уже заполнен) выполнить вручную:
#   READONLY_DB_PASSWORD=<password> \
#   docker exec -i llm_agent_db bash < docker/init-readonly-user.sh
# =============================================================

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- DO \$\$ ... \$\$ делает скрипт идемпотентным:
    -- повторный запуск не выдаст ошибку "role already exists"
    DO \$\$
    BEGIN
      IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analyst_readonly'
      ) THEN
        CREATE USER analyst_readonly
          WITH PASSWORD '$READONLY_DB_PASSWORD'
          NOSUPERUSER
          NOCREATEDB
          NOCREATEROLE
          LOGIN;
      END IF;
    END
    \$\$;

    -- Разрешить подключение к базе данных.
    -- Без CONNECT аутентификация проходит, но PostgreSQL отклоняет
    -- соединение с "permission denied for database".
    GRANT CONNECT ON DATABASE $POSTGRES_DB TO analyst_readonly;

    -- Разрешить видеть объекты внутри схемы public.
    -- USAGE — обязательное условие для любых прав на объекты схемы.
    GRANT USAGE ON SCHEMA public TO analyst_readonly;

    -- Выдать SELECT на все таблицы, которые существуют ПРЯМО СЕЙЧАС.
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_readonly;

    -- КРИТИЧЕСКИ ВАЖНО для CSV-таблиц пользователей:
    -- df.to_sql() создаёт таблицы под admin после этого скрипта.
    -- ALTER DEFAULT PRIVILEGES покрывает ВСЕ БУДУЩИЕ таблицы admin-а.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
      GRANT SELECT ON TABLES TO analyst_readonly;
EOSQL