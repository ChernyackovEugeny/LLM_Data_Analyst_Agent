"""
Фикстуры для интеграционных тестов.

Стратегия мокирования:
  - AsyncPostgresSaver патчится, чтобы lifespan не подключался к реальному PostgreSQL.
  - raw_graph патчится, чтобы lifespan скомпилировал мок-граф вместо реального.
  - get_db переопределяется через dependency_overrides — все маршруты получают mock_db.

Порядок инициализации при каждом тесте:
  1. patch('app.app.AsyncPostgresSaver')  ← lifespan не падает
  2. patch('app.core.graph.raw_graph')    ← lifespan получает mock_compiled
  3. app.dependency_overrides[get_db] = mock_db
  4. with TestClient(app) as client       ← lifespan запускается, app_graph = mock_compiled
"""
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# Убеждаемся, что тестовые env vars выставлены до импорта app
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-api-key-for-testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/testdb")
os.environ.setdefault("READONLY_DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/testdb")
os.environ.setdefault("USE_SANDBOX", "false")


def make_mock_db():
    """Создаёт мок SQLAlchemy-сессии с настроенными дефолтными возвратами."""
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    db.execute.return_value.fetchall.return_value = []
    return db


def make_mock_compiled_graph():
    """Создаёт мок скомпилированного LangGraph."""
    mock_compiled = MagicMock()

    # Синхронный invoke (используется в /analyze)
    final_msg = MagicMock()
    final_msg.content = "Тестовый ответ агента."
    mock_compiled.invoke.return_value = {"messages": [final_msg]}

    # Асинхронный ainvoke
    mock_compiled.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    # astream — по умолчанию пустой, переопределяется в конкретных тестах
    async def default_astream(*args, **kwargs):
        final_msg_stream = MagicMock()
        final_msg_stream.content = "Ответ агента."
        final_msg_stream.tool_calls = []
        yield {"agent": {"messages": [final_msg_stream]}}

    mock_compiled.astream = default_astream

    return mock_compiled


@pytest.fixture
def mock_db():
    return make_mock_db()


@pytest.fixture
def mock_graph():
    return make_mock_compiled_graph()


@pytest.fixture
def app_client(mock_db, mock_graph):
    """
    TestClient с полностью замоканной инфраструктурой.

    Возвращает TestClient — куки и заголовки выставляются в конкретных тестах.
    """
    from unittest.mock import patch

    from app.app import app
    from app.database.database import get_db

    # Мокируем checkpointer
    mock_checkpointer = MagicMock()
    mock_checkpointer.setup = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_checkpointer)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.app.AsyncPostgresSaver") as MockSaver,
        patch("app.core.graph.raw_graph") as mock_raw_graph,
    ):
        MockSaver.from_conn_string.return_value = mock_ctx
        mock_raw_graph.compile.return_value = mock_graph

        # Гарантируем создание директории (StaticFiles требует её наличия)
        os.makedirs("static/plots", exist_ok=True)

        app.dependency_overrides[get_db] = lambda: mock_db

        with TestClient(app, raise_server_exceptions=True) as client:
            yield client

        app.dependency_overrides.clear()


@pytest.fixture
def auth_token():
    """Создаёт валидный access_token для тестового пользователя (user_id=1)."""
    from app.auth.auth import create_access_token
    from datetime import timedelta

    return create_access_token(
        {"sub": "testuser@example.com", "user_id": 1},
        expires_delta=timedelta(hours=1),
    )


@pytest.fixture
def authenticated_client(app_client, auth_token):
    """TestClient с предустановленным access_token cookie."""
    app_client.cookies.set("access_token", auth_token)
    return app_client
