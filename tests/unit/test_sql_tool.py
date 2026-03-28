"""
Unit тесты для app/tools/sql_tool.py

Покрываем:
  - _strip_sql_comments: очистка SQL-комментариев
  - _validate_readonly_query: application-level SQL валидация
  - execute_sql_query: полный путь с мокированным движком

Без реальной БД — readonly_engine мокируется там, где нужно.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.tools.sql_tool import _strip_sql_comments, _validate_readonly_query, execute_sql_query


class TestStripSqlComments:
    def test_removes_inline_comment(self):
        result = _strip_sql_comments("SELECT 1 -- this is a comment")
        assert "--" not in result
        assert "SELECT 1" in result

    def test_removes_block_comment(self):
        result = _strip_sql_comments("SELECT /* DROP TABLE users */ 1")
        assert "DROP" not in result
        assert "SELECT" in result

    def test_removes_multiline_block_comment(self):
        sql = "SELECT\n/* line 1\nline 2 */\n1"
        result = _strip_sql_comments(sql)
        assert "line 1" not in result
        assert "line 2" not in result

    def test_query_without_comments_unchanged(self):
        sql = "SELECT id, name FROM customers"
        result = _strip_sql_comments(sql)
        assert "id" in result
        assert "name" in result
        assert "customers" in result


class TestValidateReadonlyQuery:
    def test_valid_select_passes(self):
        is_valid, msg = _validate_readonly_query("SELECT * FROM customers")
        assert is_valid is True
        assert msg == ""

    def test_valid_select_with_where(self):
        is_valid, msg = _validate_readonly_query(
            "SELECT id, name FROM customers WHERE city = 'Москва'"
        )
        assert is_valid is True

    def test_valid_select_case_insensitive(self):
        is_valid, msg = _validate_readonly_query("select * from orders")
        assert is_valid is True

    def test_rejects_insert(self):
        is_valid, msg = _validate_readonly_query("INSERT INTO users VALUES (1, 'x')")
        assert is_valid is False
        assert "INSERT" in msg

    def test_rejects_update(self):
        is_valid, msg = _validate_readonly_query("UPDATE customers SET name = 'x'")
        assert is_valid is False

    def test_rejects_delete(self):
        is_valid, msg = _validate_readonly_query("DELETE FROM orders WHERE id = 1")
        assert is_valid is False

    def test_rejects_drop(self):
        is_valid, msg = _validate_readonly_query("DROP TABLE users")
        assert is_valid is False

    def test_rejects_create(self):
        is_valid, msg = _validate_readonly_query("CREATE TABLE new_table (id INT)")
        assert is_valid is False

    def test_rejects_semicolon(self):
        is_valid, msg = _validate_readonly_query("SELECT 1; DROP TABLE users")
        assert is_valid is False
        assert "запрещена" in msg.lower() or ";" in msg

    def test_rejects_select_into(self):
        is_valid, msg = _validate_readonly_query(
            "SELECT * INTO new_table FROM customers"
        )
        assert is_valid is False
        assert "INTO" in msg or "into" in msg.lower()

    def test_rejects_empty_query(self):
        is_valid, msg = _validate_readonly_query("")
        assert is_valid is False

    def test_rejects_comment_hiding_drop(self):
        """Комментарий не должен скрыть DROP."""
        # После strip_comments: "DROP TABLE users" — первый токен не SELECT
        is_valid, msg = _validate_readonly_query("-- SELECT\nDROP TABLE users")
        assert is_valid is False

    def test_strips_comments_before_validation(self):
        """Комментарий с опасным словом не должен блокировать валидный SELECT."""
        is_valid, msg = _validate_readonly_query(
            "SELECT id /* DELETE all */ FROM customers"
        )
        assert is_valid is True


class TestExecuteSqlQueryTool:
    @patch("app.tools.sql_tool.readonly_engine")
    def test_returns_markdown_table_on_success(self, mock_engine):
        """Успешный SELECT → markdown-таблица с заголовком и строками."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name"]
        mock_result.fetchall.return_value = [(1, "Иван"), (2, "Мария")]

        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result

        result = execute_sql_query.invoke({"query": "SELECT id, name FROM customers"})

        assert "|id|name|" in result
        assert "Иван" in result
        assert "Мария" in result

    @patch("app.tools.sql_tool.readonly_engine")
    def test_returns_empty_message_when_no_rows(self, mock_engine):
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchall.return_value = []

        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_result

        result = execute_sql_query.invoke({"query": "SELECT id FROM customers WHERE 1=0"})
        assert "не найдено" in result.lower() or "0" in result or "пусто" in result.lower()

    def test_rejects_non_select_query(self):
        """INSERT без обращения к БД — отклоняется на Слое 1."""
        result = execute_sql_query.invoke({"query": "DELETE FROM users"})
        assert "отклонён" in result.lower() or "запрещ" in result.lower()

    def test_rejects_query_with_semicolon(self):
        result = execute_sql_query.invoke({"query": "SELECT 1; DROP TABLE users"})
        assert "отклонён" in result.lower() or "запрещ" in result.lower()

    @patch("app.tools.sql_tool.readonly_engine")
    def test_handles_db_exception_gracefully(self, mock_engine):
        """Если БД бросила исключение — возвращаем сообщение об ошибке."""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = Exception("connection refused")

        result = execute_sql_query.invoke({"query": "SELECT * FROM customers"})
        assert "ошибка" in result.lower()
