"""
Unit тесты для app/auth/auth.py

Покрываем: хэширование паролей, создание и декодирование JWT токенов.
Внешних зависимостей нет — тесты работают без БД и без реальных API.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.auth.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_plain_text(self):
        password = "my_secret_password"
        hashed = get_password_hash(password)
        assert hashed != password

    def test_hash_looks_like_bcrypt(self):
        hashed = get_password_hash("password")
        # bcrypt хэши начинаются с $2b$ или $2a$
        assert hashed.startswith("$2")

    def test_verify_correct_password(self):
        password = "correct_password"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_same_password_produces_different_hashes(self):
        # bcrypt использует соль — каждый хэш уникален
        h1 = get_password_hash("password")
        h2 = get_password_hash("password")
        assert h1 != h2
        # Но оба должны верифицироваться успешно
        assert verify_password("password", h1) is True
        assert verify_password("password", h2) is True


class TestAccessToken:
    def test_access_token_is_decodable(self):
        token = create_access_token({"sub": "test@example.com", "user_id": 1})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "test@example.com"
        assert payload["user_id"] == 1

    def test_access_token_contains_exp(self):
        token = create_access_token({"sub": "test@example.com"})
        payload = decode_token(token)
        assert "exp" in payload

    def test_access_token_custom_expiry(self):
        """Токен с явно заданным сроком действия декодируется корректно."""
        token = create_access_token(
            {"sub": "test@example.com"},
            expires_delta=timedelta(hours=1),
        )
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "test@example.com"

    def test_expired_access_token_returns_none(self):
        """Просроченный токен → decode_token возвращает None."""
        token = create_access_token(
            {"sub": "test@example.com"},
            expires_delta=timedelta(seconds=-1),  # уже истёк
        )
        result = decode_token(token)
        assert result is None

    def test_tampered_token_returns_none(self):
        """Токен с изменённой подписью → None."""
        token = create_access_token({"sub": "test@example.com"})
        # Меняем символ в середине подписи (последний символ JWT-подписи содержит
        # только 4 значимых бита + 2 нулевых бита-заглушки base64url, поэтому
        # некоторые замены последнего символа декодируются в те же байты).
        # Берём позицию за 10 символов до конца — все 6 бит значимые.
        pos = -10
        original_char = token[pos]
        replacement = "A" if original_char != "A" else "B"
        tampered = token[:pos] + replacement + token[pos + 1:]
        result = decode_token(tampered)
        assert result is None

    def test_invalid_token_string_returns_none(self):
        result = decode_token("this.is.not.a.valid.token")
        assert result is None


class TestRefreshToken:
    def test_refresh_token_is_decodable(self):
        token = create_refresh_token({"sub": "test@example.com", "user_id": 42})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "test@example.com"
        assert payload["user_id"] == 42

    def test_refresh_token_has_type_field(self):
        token = create_refresh_token({"sub": "test@example.com"})
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_refresh_token_expires_later_than_access_token(self):
        """Refresh-токен живёт дольше access-токена."""
        access = create_access_token({"sub": "user"})
        refresh = create_refresh_token({"sub": "user"})

        access_payload = decode_token(access)
        refresh_payload = decode_token(refresh)

        assert refresh_payload["exp"] > access_payload["exp"]
