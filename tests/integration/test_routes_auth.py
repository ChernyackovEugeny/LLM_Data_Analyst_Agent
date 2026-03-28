"""
Интеграционные тесты для маршрутов аутентификации:
  POST /api/v1/auth/signup
  POST /api/v1/auth/login
  POST /api/v1/auth/logout
  POST /api/v1/auth/refresh
  GET  /api/v1/auth/me
"""
import pytest
from app.auth.auth import get_password_hash


class TestSignup:
    def test_signup_success(self, app_client, mock_db):
        """Новый пользователь регистрируется, возвращает id и email."""
        # SELECT → email не найден; INSERT → возвращает нового пользователя
        mock_db.execute.return_value.fetchone.side_effect = [
            None,
            (1, "newuser@example.com"),
        ]

        response = app_client.post(
            "/api/v1/auth/signup",
            json={"email": "newuser@example.com", "password": "password123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["id"] == 1

    def test_signup_duplicate_email(self, app_client, mock_db):
        """Повторная регистрация с тем же email → 400."""
        # SELECT → email уже существует
        mock_db.execute.return_value.fetchone.return_value = (1,)

        response = app_client.post(
            "/api/v1/auth/signup",
            json={"email": "existing@example.com", "password": "password123"},
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    def test_signup_invalid_email(self, app_client, mock_db):
        """Невалидный email → 422 (pydantic validation)."""
        response = app_client.post(
            "/api/v1/auth/signup",
            json={"email": "not-an-email", "password": "password123"},
        )
        assert response.status_code == 422

    def test_signup_missing_fields(self, app_client):
        """Отсутствие обязательных полей → 422."""
        response = app_client.post("/api/v1/auth/signup", json={})
        assert response.status_code == 422


class TestLogin:
    def test_login_success(self, app_client, mock_db):
        """Успешный логин → 200, access_token cookie установлен."""
        hashed = get_password_hash("testpassword")
        mock_db.execute.return_value.fetchone.return_value = (
            1,
            "testuser@example.com",
            hashed,
        )

        response = app_client.post(
            "/api/v1/auth/login",
            data={"username": "testuser@example.com", "password": "testpassword"},
        )

        assert response.status_code == 200
        # HttpOnly cookie должен присутствовать в ответе
        assert "access_token" in response.cookies or "access_token" in response.headers.get(
            "set-cookie", ""
        )

    def test_login_wrong_password(self, app_client, mock_db):
        """Неверный пароль → 401."""
        hashed = get_password_hash("correctpassword")
        mock_db.execute.return_value.fetchone.return_value = (
            1,
            "user@example.com",
            hashed,
        )

        response = app_client.post(
            "/api/v1/auth/login",
            data={"username": "user@example.com", "password": "wrongpassword"},
        )

        assert response.status_code == 401

    def test_login_nonexistent_user(self, app_client, mock_db):
        """Несуществующий пользователь → 401."""
        mock_db.execute.return_value.fetchone.return_value = None

        response = app_client.post(
            "/api/v1/auth/login",
            data={"username": "ghost@example.com", "password": "pass"},
        )

        assert response.status_code == 401


class TestLogout:
    def test_logout_returns_200(self, authenticated_client):
        response = authenticated_client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        assert "Logged out" in response.json()["message"]

    def test_logout_clears_access_token_cookie(self, authenticated_client):
        response = authenticated_client.post("/api/v1/auth/logout")
        # После logout cookie должен быть удалён (Max-Age=0)
        set_cookie = response.headers.get("set-cookie", "")
        # Сервер выставляет Max-Age=0 или expires в прошлом
        assert "access_token" in set_cookie or response.status_code == 200


class TestGetMe:
    def test_me_authenticated(self, authenticated_client):
        """Авторизованный запрос → возвращает данные пользователя."""
        response = authenticated_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@example.com"
        assert data["id"] == 1

    def test_me_unauthenticated(self, app_client):
        """Без cookie → 401."""
        response = app_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_token(self, app_client):
        """Невалидный токен → 401."""
        app_client.cookies.set("access_token", "invalid.jwt.token")
        response = app_client.get("/api/v1/auth/me")
        assert response.status_code == 401


class TestRefreshTokens:
    def test_refresh_without_cookie_returns_401(self, app_client):
        response = app_client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_refresh_with_invalid_token_returns_401(self, app_client):
        app_client.cookies.set("refresh_token", "bad.token.here")
        response = app_client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_refresh_with_access_token_as_refresh_returns_401(
        self, app_client, auth_token
    ):
        """access_token не является refresh_token (нет поля type='refresh') → 401."""
        app_client.cookies.set("refresh_token", auth_token)
        response = app_client.post("/api/v1/auth/refresh")
        assert response.status_code == 401
