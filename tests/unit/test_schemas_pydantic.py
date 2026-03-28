"""
Unit тесты для app/models/schemas.py

Покрываем: Pydantic-модели на валидацию входных данных.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatOut,
    MessageOut,
    Token,
    UploadResponse,
    UserCreate,
    UserOut,
)


class TestUserCreate:
    def test_valid_user(self):
        user = UserCreate(email="test@example.com", password="password123")
        assert user.email == "test@example.com"
        assert user.password == "password123"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(email="not-an-email", password="password123")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("email",) for e in errors)

    def test_empty_email_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="", password="password123")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="test@example.com")

    def test_email_normalization(self):
        """pydantic EmailStr нормализует домен к нижнему регистру (RFC-совместимо).
        Локальная часть email регистрозависима по RFC 5321 и не нормализуется."""
        user = UserCreate(email="TEST@EXAMPLE.COM", password="pass")
        # Домен нормализуется к нижнему регистру, локальная часть сохраняется
        assert user.email == "TEST@example.com"


class TestUserOut:
    def test_valid_user_out(self):
        user = UserOut(id=1, email="user@example.com")
        assert user.id == 1
        assert user.email == "user@example.com"

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            UserOut(email="user@example.com")


class TestAnalyzeRequest:
    def test_question_only(self):
        req = AnalyzeRequest(question="Сколько заказов за месяц?")
        assert req.question == "Сколько заказов за месяц?"
        assert req.thread_id is None

    def test_with_thread_id(self):
        req = AnalyzeRequest(question="Test", thread_id="thread-abc-123")
        assert req.thread_id == "thread-abc-123"

    def test_missing_question_raises(self):
        with pytest.raises(ValidationError):
            AnalyzeRequest()

    def test_thread_id_optional(self):
        """thread_id — необязательное поле."""
        req = AnalyzeRequest(question="Test")
        assert req.thread_id is None


class TestAnalyzeResponse:
    def test_valid_response(self):
        resp = AnalyzeResponse(answer="Всего 100 заказов.")
        assert resp.answer == "Всего 100 заказов."

    def test_missing_answer_raises(self):
        with pytest.raises(ValidationError):
            AnalyzeResponse()


class TestChatOut:
    def test_valid_chat(self):
        now = datetime(2024, 1, 15, 12, 0, 0)
        chat = ChatOut(id=1, title="Мой чат", created_at=now)
        assert chat.id == 1
        assert chat.title == "Мой чат"
        assert chat.created_at == now

    def test_missing_fields_raise(self):
        with pytest.raises(ValidationError):
            ChatOut(id=1)  # нет title и created_at


class TestMessageOut:
    def test_valid_message(self):
        now = datetime.now()
        msg = MessageOut(role="user", content="Привет!", created_at=now)
        assert msg.role == "user"
        assert msg.content == "Привет!"

    def test_agent_role(self):
        msg = MessageOut(role="agent", content="Ответ", created_at=datetime.now())
        assert msg.role == "agent"


class TestUploadResponse:
    def test_valid_upload_response(self):
        resp = UploadResponse(
            table_name="csv_u1",
            columns=["id", "name", "price"],
            row_count=150,
            message="Файл загружен.",
        )
        assert resp.table_name == "csv_u1"
        assert resp.row_count == 150
        assert len(resp.columns) == 3

    def test_missing_fields_raise(self):
        with pytest.raises(ValidationError):
            UploadResponse(table_name="csv_u1")
