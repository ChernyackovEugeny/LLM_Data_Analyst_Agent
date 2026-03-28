import re

from langchain_core.tools import tool
from sqlalchemy import text

# Используем read-only engine — analyst_readonly имеет только SELECT.
# admin engine намеренно НЕ импортируется: этот модуль никогда не должен
# иметь доступ к write-capable соединению.
from app.database.database import readonly_engine


# ---------------------------------------------------------------------------
# Application-layer SQL валидация (defense-in-depth, Слой 1)
# ---------------------------------------------------------------------------
# Слой 1 (эта валидация) + Слой 2 (readonly привилегии) — два независимых слоя.
# Слой 1: быстрый отказ без TCP round-trip к PostgreSQL, понятные сообщения об ошибке.
# Слой 2: отказ на уровне БД даже если Слой 1 пропустит хитрый запрос.
# Оба слоя нужны: у каждого разные failure modes.

def _strip_sql_comments(query: str) -> str:
    """
    Удаляет SQL-комментарии перед проверкой запроса.

    Без стриппинга комментарии позволяют спрятать деструктивные команды:
      SELECT 1 /* DROP TABLE users */  — regex не увидит DROP
      -- DROP TABLE; SELECT 1           — проверка первого токена не поможет

    re.DOTALL нужен чтобы /* многострочный\nкомментарий */ тоже стриппился.
    """
    # Сначала блочные комментарии (могут содержать --)
    query = re.sub(r'/\*.*?\*/', ' ', query, flags=re.DOTALL)
    # Затем строчные комментарии
    query = re.sub(r'--[^\n]*', ' ', query)
    return query.strip()


def _validate_readonly_query(query: str) -> tuple[bool, str]:
    """
    Возвращает (is_valid, error_message).

    Правило 1 — первый токен должен быть SELECT (allowlist, не blocklist):
      Blocklist никогда не полный: DROP, DELETE, INSERT, UPDATE, CREATE, ALTER,
      TRUNCATE, GRANT, REVOKE, COPY, VACUUM, DO, CALL, EXECUTE...
      Allowlist закрытый: только SELECT — всё остальное запрещено.

    Правило 2 — запрет точки с запятой (несколько statements):
      psycopg2 выполняет "SELECT 1; DROP TABLE orders" как два statement.
      Проверяем ПОСЛЕ стриппинга: ; внутри комментария не даст false positive.

    Правило 3 — запрет SELECT INTO:
      В PostgreSQL SELECT * INTO new_table FROM old_table создаёт таблицу.
      Первый токен — SELECT, поэтому правило 1 это не поймает.
    """
    clean = _strip_sql_comments(query)

    tokens = clean.upper().split()
    if not tokens:
        return False, "Пустой запрос."

    if tokens[0] != 'SELECT':
        return False, f"Разрешены только SELECT-запросы. Получено: '{tokens[0]}'."

    if ';' in clean:
        return False, "Точка с запятой запрещена — только одиночный SELECT-запрос."

    if re.search(r'\bINTO\b', clean, re.IGNORECASE):
        return False, "SELECT INTO запрещён: создаёт таблицу в PostgreSQL."

    return True, ""


@tool
def execute_sql_query(query: str) -> str:
    """
    Выполняет SQL запрос к базе данных и возвращает результат в виде текста.
    Используй этот инструмент, когда нужно получить данные из БД.

    Args:
        query: SQL SELECT запрос. Только SELECT разрешён.
    """

    # Слой 1: application-level валидация (быстро, без обращения к БД)
    is_valid, error_msg = _validate_readonly_query(query)
    if not is_valid:
        return f"Запрос отклонён политикой безопасности: {error_msg}"

    # Слой 2: выполнение через read-only соединение (роль analyst_readonly).
    # Даже если Слой 1 пропустит хитрый запрос, PostgreSQL откажет в выполнении
    # любой write/DDL операции: ERROR: permission denied for table <name>
    try:
        with readonly_engine.connect() as connection:
            result = connection.execute(text(query))

            columns_names = list(result.keys())
            rows = result.fetchall()

            if not rows:
                return "Запрос выполнен успешно, но данных не найдено."

            header = '|' + '|'.join(columns_names) + '|'
            separator = '|' + '|'.join(['---'] * len(columns_names)) + '|'
            rows_str = [
                '|' + '|'.join(str(item) for item in row) + '|'
                for row in rows
            ]
            return f'{header}\n{separator}\n' + '\n'.join(rows_str)

    except Exception as e:
        return f"Ошибка при выполнении SQL: {str(e)}"
