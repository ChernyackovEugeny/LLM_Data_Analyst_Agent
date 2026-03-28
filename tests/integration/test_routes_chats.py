"""
Интеграционные тесты для маршрутов чатов:
  POST   /api/v1/chats
  GET    /api/v1/chats
  DELETE /api/v1/chats/{chat_id}
  GET    /api/v1/chats/{chat_id}/messages
"""
from datetime import datetime

import pytest


FIXED_DT = datetime(2024, 6, 15, 10, 30, 0)


class TestCreateChat:
    def test_create_chat_unauthenticated(self, app_client):
        response = app_client.post("/api/v1/chats")
        assert response.status_code == 401

    def test_create_chat_success(self, authenticated_client, mock_db):
        """Создание чата → 200, возвращает ChatOut."""
        mock_db.execute.return_value.fetchone.return_value = (
            1,
            "Новый чат",
            FIXED_DT,
        )

        response = authenticated_client.post("/api/v1/chats")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Новый чат"
        assert "created_at" in data

    def test_create_chat_calls_db_commit(self, authenticated_client, mock_db):
        """После создания чата должен вызываться db.commit()."""
        mock_db.execute.return_value.fetchone.return_value = (2, "Новый чат", FIXED_DT)

        authenticated_client.post("/api/v1/chats")

        mock_db.commit.assert_called()


class TestListChats:
    def test_list_chats_unauthenticated(self, app_client):
        response = app_client.get("/api/v1/chats")
        assert response.status_code == 401

    def test_list_chats_empty(self, authenticated_client, mock_db):
        """Нет чатов → пустой список."""
        mock_db.execute.return_value.fetchall.return_value = []

        response = authenticated_client.get("/api/v1/chats")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_chats_returns_all_user_chats(self, authenticated_client, mock_db):
        """Список чатов возвращается в правильном формате."""
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "Первый чат", FIXED_DT),
            (2, "Второй чат", FIXED_DT),
        ]

        response = authenticated_client.get("/api/v1/chats")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["title"] == "Первый чат"
        assert data[1]["id"] == 2


class TestDeleteChat:
    def test_delete_chat_unauthenticated(self, app_client):
        response = app_client.delete("/api/v1/chats/1")
        assert response.status_code == 401

    def test_delete_chat_success(self, authenticated_client, mock_db):
        """Удаление существующего чата → 200."""
        # SELECT → чат найден
        mock_db.execute.return_value.fetchone.return_value = (1,)

        response = authenticated_client.delete("/api/v1/chats/1")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()

    def test_delete_nonexistent_chat_returns_404(self, authenticated_client, mock_db):
        """Удаление несуществующего чата → 404."""
        mock_db.execute.return_value.fetchone.return_value = None

        response = authenticated_client.delete("/api/v1/chats/999")

        assert response.status_code == 404

    def test_delete_chat_calls_commit(self, authenticated_client, mock_db):
        """После удаления должен вызываться db.commit()."""
        mock_db.execute.return_value.fetchone.return_value = (1,)

        authenticated_client.delete("/api/v1/chats/1")

        mock_db.commit.assert_called()


class TestGetChatMessages:
    def test_get_messages_unauthenticated(self, app_client):
        response = app_client.get("/api/v1/chats/1/messages")
        assert response.status_code == 401

    def test_get_messages_chat_not_found(self, authenticated_client, mock_db):
        """Чат не найден → 404."""
        mock_db.execute.return_value.fetchone.return_value = None

        response = authenticated_client.get("/api/v1/chats/999/messages")
        assert response.status_code == 404

    def test_get_messages_returns_message_list(self, authenticated_client, mock_db):
        """Список сообщений возвращается в правильном формате."""
        # Первый execute (проверка владения) — fetchone возвращает чат
        # Второй execute (получение сообщений) — fetchall возвращает список
        mock_db.execute.return_value.fetchone.return_value = (1,)
        mock_db.execute.return_value.fetchall.return_value = [
            ("user", "Сколько заказов?", FIXED_DT),
            ("agent", "Всего 500 заказов.", FIXED_DT),
        ]

        response = authenticated_client.get("/api/v1/chats/1/messages")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[0]["content"] == "Сколько заказов?"
        assert data[1]["role"] == "agent"

    def test_get_messages_empty_chat(self, authenticated_client, mock_db):
        """Чат без сообщений → пустой список."""
        mock_db.execute.return_value.fetchone.return_value = (1,)
        mock_db.execute.return_value.fetchall.return_value = []

        response = authenticated_client.get("/api/v1/chats/1/messages")

        assert response.status_code == 200
        assert response.json() == []


class TestHealthCheck:
    def test_health_check_returns_ok(self, app_client):
        """GET /health → статус ok без авторизации."""
        response = app_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "model" in data
