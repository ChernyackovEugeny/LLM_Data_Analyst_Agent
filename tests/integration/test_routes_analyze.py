"""
Интеграционные тесты для маршрутов агента:
  POST /api/v1/analyze
  GET  /api/v1/analyze/stream
  POST /api/v1/upload-csv
"""
import io
import json

import pytest


class TestAnalyzeEndpoint:
    def test_analyze_unauthenticated_returns_401(self, app_client):
        response = app_client.post(
            "/api/v1/analyze",
            json={"question": "Сколько заказов?"},
        )
        assert response.status_code == 401

    def test_analyze_success(self, authenticated_client, mock_graph):
        """Авторизованный запрос → агент возвращает ответ."""
        from unittest.mock import AsyncMock, MagicMock

        final_msg = MagicMock()
        final_msg.content = "Всего 500 заказов."
        # Эндпоинт /analyze использует ainvoke (async), не синхронный invoke
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

        response = authenticated_client.post(
            "/api/v1/analyze",
            json={"question": "Сколько заказов в базе?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Всего 500 заказов."

    def test_analyze_missing_question_returns_422(self, authenticated_client):
        response = authenticated_client.post("/api/v1/analyze", json={})
        assert response.status_code == 422


class TestAnalyzeStreamEndpoint:
    def test_stream_unauthenticated_returns_401(self, app_client):
        response = app_client.get(
            "/api/v1/analyze/stream",
            params={"question": "test", "chat_id": 1},
        )
        assert response.status_code == 401

    def test_stream_chat_not_found_returns_404(self, authenticated_client, mock_db):
        """Если чат не найден → 404 до начала стриминга."""
        mock_db.execute.return_value.fetchone.return_value = None  # чат не найден

        response = authenticated_client.get(
            "/api/v1/analyze/stream",
            params={"question": "test", "chat_id": 999},
        )
        assert response.status_code == 404

    def test_stream_returns_sse_events(self, authenticated_client, mock_db, mock_graph):
        """При наличии чата → SSE-поток с событиями."""
        from unittest.mock import MagicMock

        # Чат существует
        mock_db.execute.return_value.fetchone.return_value = (1, "Тестовый чат")

        # astream возвращает финальный ответ агента
        async def mock_astream(*args, **kwargs):
            msg = MagicMock()
            msg.content = "Тестовый ответ"
            msg.tool_calls = []
            yield {"agent": {"messages": [msg]}}

        mock_graph.astream = mock_astream

        response = authenticated_client.get(
            "/api/v1/analyze/stream",
            params={"question": "Сколько клиентов?", "chat_id": 1},
        )

        assert response.status_code == 200
        # SSE content-type
        assert "text/event-stream" in response.headers.get("content-type", "")
        # Поток содержит SSE-данные
        assert "data:" in response.text

    def test_stream_contains_done_event(self, authenticated_client, mock_db, mock_graph):
        """Поток должен содержать событие type=done с ответом агента."""
        from unittest.mock import MagicMock

        mock_db.execute.return_value.fetchone.return_value = (1, "Новый чат")

        async def mock_astream(*args, **kwargs):
            msg = MagicMock()
            msg.content = "42 клиента."
            msg.tool_calls = []
            yield {"agent": {"messages": [msg]}}

        mock_graph.astream = mock_astream

        response = authenticated_client.get(
            "/api/v1/analyze/stream",
            params={"question": "Сколько клиентов?", "chat_id": 1},
        )

        assert response.status_code == 200
        # Парсим SSE-события из ответа
        events = []
        for line in response.text.splitlines():
            if line.startswith("data:"):
                raw = line[len("data:"):].strip()
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass

        event_types = [e.get("type") for e in events]
        assert "done" in event_types

        done_event = next(e for e in events if e.get("type") == "done")
        assert done_event["answer"] == "42 клиента."

    def test_stream_contains_thinking_event(self, authenticated_client, mock_db, mock_graph):
        """Агент должен отправлять событие type=thinking перед ответом."""
        from unittest.mock import MagicMock

        mock_db.execute.return_value.fetchone.return_value = (1, "Новый чат")

        async def mock_astream(*args, **kwargs):
            msg = MagicMock()
            msg.content = "Ответ"
            msg.tool_calls = []
            yield {"agent": {"messages": [msg]}}

        mock_graph.astream = mock_astream

        response = authenticated_client.get(
            "/api/v1/analyze/stream",
            params={"question": "test", "chat_id": 1},
        )

        events = []
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass

        assert any(e.get("type") == "thinking" for e in events)


class TestUploadCsv:
    def test_upload_unauthenticated_returns_401(self, app_client):
        csv_bytes = b"id,name\n1,Alice\n2,Bob"
        response = app_client.post(
            "/api/v1/upload-csv",
            files={"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert response.status_code == 401

    def test_upload_non_csv_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/upload-csv",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 400

    def test_upload_valid_csv_success(self, authenticated_client):
        """Валидный CSV → 200 с метаданными таблицы."""
        from unittest.mock import patch

        csv_content = "id,name,city\n1,Иван,Москва\n2,Мария,СПБ\n3,Пётр,Казань"
        csv_bytes = csv_content.encode("utf-8")

        # Мокируем pandas to_sql чтобы не писать в реальную БД
        with patch("app.api.routes.pd.DataFrame.to_sql"):
            response = authenticated_client.post(
                "/api/v1/upload-csv",
                files={
                    "file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["table_name"] == "csv_u1"
        assert "id" in data["columns"]
        assert "name" in data["columns"]
        assert data["row_count"] == 3

    def test_upload_empty_csv_returns_422(self, authenticated_client):
        """Пустой CSV-файл → 422."""
        from unittest.mock import patch

        csv_bytes = b"id,name\n"  # только заголовок, нет строк

        with patch("app.api.routes.pd.DataFrame.to_sql"):
            response = authenticated_client.post(
                "/api/v1/upload-csv",
                files={"file": ("empty.csv", io.BytesIO(csv_bytes), "text/csv")},
            )
        assert response.status_code == 422

    def test_upload_windows1252_csv(self, authenticated_client):
        """CSV в кодировке Windows-1252 должен декодироваться."""
        from unittest.mock import patch

        # cp1252 — западноевропейская кодировка (не поддерживает кириллицу).
        # Используем символы западноевропейских языков: é, ü, ñ — типичный Excel из Европы.
        csv_content = "city,population\nMünchen,1500000\nParis,2200000\nMadrid,3300000"
        csv_bytes = csv_content.encode("cp1252")

        with patch("app.api.routes.pd.DataFrame.to_sql"):
            response = authenticated_client.post(
                "/api/v1/upload-csv",
                files={
                    "file": ("windows.csv", io.BytesIO(csv_bytes), "text/csv")
                },
            )

        assert response.status_code == 200
