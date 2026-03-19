from langchain_core.tools import tool
from sqlalchemy import create_engine, text

from app.database.database import engine
from app.config import settings

@tool
def execute_sql_query(query: str) -> str:
    """
    Выполняет SQL запрос к базе данных и возвращает результат в виде текста.
    Используй этот инструмент, когда нужно получить данные из БД.
    
    Args:
        query: SQL запрос (SELECT). Не используйте запросы на изменение данных (INSERT, UPDATE, DELETE).
    """

    try:
        with engine.connect() as connection:
            
            # Используем text для безопасного выполнения сырых SQL запросов
            result = connection.execute(text(query))

            # названия колонок
            columns_names = result.keys()

            # строки
            rows = result.fetchall()

            if not rows:
                return "Запрос выполнен успешно, но данных не найдено."

            # Форматируем вывод в читаемый вид (markdown таблица)
            header = '|' + '|'.join(columns_names) + '|'
            separator = '|' + '|'.join(['---'] * len(columns_names)) + '|'

            # строки
            rows_str = []
            for row in rows:
                row_text = '|' + '|'.join(str(item) for item in row) + '|'
                rows_str.append(row_text)
            
            return f'{header}\n{separator}\n' + '\n'.join(rows_str)
    
    except Exception as e:
        # Если произошла ошибка, возвращаем её агенту, чтобы он мог исправить SQL
        return f"Ошибка при выполнении SQL: {str(e)}"
