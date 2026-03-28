"""
Root conftest.py — устанавливает переменные окружения ДО импорта любого модуля приложения.

Pydantic-settings при создании Settings() читает (в порядке убывания приоритета):
  1. os.environ  ← мы выставляем здесь тестовые значения
  2. .env файл

Поскольку этот модуль импортируется pytest'ом раньше тестовых модулей,
settings = Settings() получит наши тестовые значения.
"""
import os

# Выставляем только те переменные, которые отсутствуют в os.environ.
# Если у разработчика уже выставлены переменные окружения — не перезаписываем.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-api-key-for-testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/testdb")
os.environ.setdefault("READONLY_DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/testdb")
os.environ.setdefault("USE_SANDBOX", "false")
