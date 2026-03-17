from sqlalchemy import create_engine, inspect

from app.config import settings


def get_database_schema() -> str:
    """
    Получает схему базы данных (названия таблиц и колонок),
    чтобы LLM могла сгенерировать корректный SQL.
    """
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    schema_description = []
    
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        column_details = []
        for col in columns:
            # Формируем строку вида: "column_name (type)"
            col_str = f"{col['name']} ({col['type']})"
            column_details.append(col_str)
        
        schema_description.append(f"Таблица: {table_name}\nКолонки: {', '.join(column_details)}")
    
    return "\n\n".join(schema_description)

# Для теста можно запустить этот файл напрямую
if __name__ == "__main__":
    print("Текущая схема БД:")
    print(get_database_schema())