from sqlalchemy import create_engine, inspect

from app.config import settings


def get_database_schema(user_id: int | None = None) -> str:
    """
    Получает схему базы данных (названия таблиц и колонок).
    Вызывается на каждый запрос агента — так агент сразу видит новые CSV-таблицы
    без перезапуска сервера.

    user_id — ID текущего пользователя. Если передан:
      - показывает его CSV-таблицу (csv_u{user_id}), если она существует
      - скрывает CSV-таблицы других пользователей (csv_u1, csv_u2...)
    """
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()

    # Имя персональной CSV-таблицы текущего пользователя (или None если user_id не передан)
    user_csv_table = f"csv_u{user_id}" if user_id is not None else None
    user_has_csv = user_csv_table and user_csv_table in all_tables

    # Системные таблицы, которые не должны попадать в схему агента
    SYSTEM_TABLES = {"users"}

    schema_description = []

    for table_name in all_tables:
        # Скрываем системные таблицы (users — там хранятся пароли)
        if table_name in SYSTEM_TABLES:
            continue

        # Скрываем CSV-таблицы других пользователей
        if table_name.startswith("csv_u") and table_name != user_csv_table:
            continue

        # Если пользователь загрузил CSV — скрываем дефолтные демо-таблицы.
        # Агент должен работать с данными пользователя, а не путаться в чужих таблицах.
        if user_has_csv and not table_name.startswith("csv_u"):
            continue

        columns = inspector.get_columns(table_name)
        col_str = ", ".join(f"{c['name']} ({c['type']})" for c in columns)
        schema_description.append(f"Таблица: {table_name}\nКолонки: {col_str}")

    return "\n\n".join(schema_description)


# Для теста можно запустить этот файл напрямую
if __name__ == "__main__":
    print("Текущая схема БД:")
    print(get_database_schema())
