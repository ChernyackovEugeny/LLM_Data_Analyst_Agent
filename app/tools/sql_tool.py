import csv
import os
import re
import uuid

from langchain_core.tools import tool
from sqlalchemy import text

# Используем read-only engine — analyst_readonly имеет только SELECT.
# admin engine намеренно НЕ импортируется: этот модуль никогда не должен
# иметь доступ к write-capable соединению.
from app.database.database import readonly_engine
from app.config import settings

# Директория для сохранения CSV-результатов запросов.
# Находится внутри static/plots/ — этот каталог уже примонтирован как
# Docker volume (PLOTS_VOLUME_NAME), поэтому results/ доступен sandbox-контейнеру
# без изменений в docker-compose.
#
# Явные слэши вместо os.path.join: на Windows os.path.join даёт обратные слэши
# (static\plots\results\abc.csv). Когда LLM вставляет такой путь в Python-код,
# \r интерпретируется как carriage return, \a — как bell-символ.
# Python принимает прямые слэши на всех ОС, поэтому используем их явно.
_RESULTS_DIR = "static/plots/results"
os.makedirs(_RESULTS_DIR, exist_ok=True)

# Количество строк превью, которое LLM видит в ToolMessage.
# Полный результат сохраняется в CSV-файл — LLM получает только структуру данных.
_PREVIEW_ROWS = 10


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
    Выполняет SQL запрос к базе данных. Сохраняет полный результат в CSV-файл
    и возвращает путь к файлу и превью первых строк.
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

            total = len(rows)

            # Сохраняем полный результат в CSV-файл.
            # Полный датасет (все строки) — LLM получит только превью и путь.
            file_id = uuid.uuid4().hex
            file_name = f"{file_id}.csv"
            host_path = f"{_RESULTS_DIR}/{file_name}"

            with open(host_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns_names)
                writer.writerows(rows)

            # Путь для использования в Python-коде зависит от режима запуска.
            # В Docker sandbox файл доступен через примонтированный volume.
            # В subprocess — через относительный путь от корня проекта.
            if settings.USE_SANDBOX:
                llm_path = f"/workspace/static/plots/results/{file_name}"
            else:
                llm_path = host_path

            # Превью: только первые _PREVIEW_ROWS строк идут в ToolMessage.
            preview_rows = rows[:_PREVIEW_ROWS]
            header = '|' + '|'.join(columns_names) + '|'
            separator = '|' + '|'.join(['---'] * len(columns_names)) + '|'
            rows_str = [
                '|' + '|'.join(str(item) for item in row) + '|'
                for row in preview_rows
            ]
            preview_table = f'{header}\n{separator}\n' + '\n'.join(rows_str)

            return (
                f"Результаты сохранены в файл: {llm_path}\n"
                f"Всего строк: {total}\n\n"
                f"Превью (первые {len(preview_rows)} из {total} строк):\n"
                f"{preview_table}"
            )

    except Exception as e:
        return f"Ошибка при выполнении SQL: {str(e)}"
