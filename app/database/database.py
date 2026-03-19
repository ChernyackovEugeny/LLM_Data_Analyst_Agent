from sqlalchemy import create_engine
from app.config import settings

# Создаем engine один раз для всего приложения
engine = create_engine(settings.DATABASE_URL)

def get_db():
    """Зависимость для FastAPI (yield connection)"""
    with engine.connect() as conn:
        yield conn