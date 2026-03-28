"""
Unit тесты для app/core/edges.py

Покрываем: should_continue(state) — условная маршрутизация в LangGraph.
"""
from unittest.mock import MagicMock

import pytest

from app.core.edges import should_continue


class TestShouldContinue:
    def test_routes_to_tools_when_tool_calls_present(self):
        """Если у последнего сообщения есть tool_calls → маршрут на 'tools'."""
        mock_message = MagicMock()
        mock_message.tool_calls = [
            {"name": "execute_sql_query", "args": {"query": "SELECT 1"}, "id": "call_1"}
        ]
        state = {"messages": [mock_message]}
        assert should_continue(state) == "tools"

    def test_routes_to_end_when_tool_calls_empty(self):
        """Пустой список tool_calls → маршрут на 'end'."""
        mock_message = MagicMock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}
        assert should_continue(state) == "end"

    def test_routes_to_end_when_tool_calls_none(self):
        """tool_calls = None → маршрут на 'end'."""
        mock_message = MagicMock()
        mock_message.tool_calls = None
        state = {"messages": [mock_message]}
        assert should_continue(state) == "end"

    def test_uses_last_message_only(self):
        """Маршрутизация основана только на ПОСЛЕДНЕМ сообщении."""
        # Первое сообщение содержит tool_calls, последнее — нет
        first_msg = MagicMock()
        first_msg.tool_calls = [{"name": "execute_sql_query", "args": {}, "id": "1"}]

        last_msg = MagicMock()
        last_msg.tool_calls = []  # агент завершил работу

        state = {"messages": [first_msg, last_msg]}
        assert should_continue(state) == "end"

    def test_routes_to_tools_with_multiple_tool_calls(self):
        """Несколько tool_calls → всё равно 'tools'."""
        mock_message = MagicMock()
        mock_message.tool_calls = [
            {"name": "execute_sql_query", "args": {}, "id": "1"},
            {"name": "execute_python_code", "args": {}, "id": "2"},
        ]
        state = {"messages": [mock_message]}
        assert should_continue(state) == "tools"
