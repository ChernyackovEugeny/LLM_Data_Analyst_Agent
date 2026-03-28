from sqlalchemy import create_engine
from app.config import settings

# Admin engine: используется для CSV-upload (df.to_sql), аутентификации,
# инспекции схемы (schemas.py) и заполнения демо-данными (seed.py).
# Подключается как POSTGRES_USER (admin) — полные права DDL/DML.
engine = create_engine(settings.DATABASE_URL)

# Read-only engine: используется ТОЛЬКО в sql_tool.py.
# Подключается как analyst_readonly — роль с правами только на SELECT.
# Даже если LLM сгенерирует DROP TABLE или DELETE, PostgreSQL откажет
# с "permission denied" на уровне привилегий, до выполнения любых изменений.
readonly_engine = create_engine(settings.READONLY_DATABASE_URL)

def get_db():
    """Зависимость для FastAPI (yield connection) — admin подключение."""
    with engine.connect() as conn:
        yield conn