"""
Unit тесты для app/core/prompts.py

Покрываем: build_agent_prompt(db_schema) — генерация ChatPromptTemplate.
"""
import pytest
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.prompts import build_agent_prompt


SAMPLE_SCHEMA = (
    "TABLE customers (id INTEGER, name TEXT, city TEXT)\n"
    "TABLE orders (id INTEGER, customer_id INTEGER, amount NUMERIC)"
)


class TestBuildAgentPrompt:
    def test_returns_chat_prompt_template(self):
        result = build_agent_prompt(SAMPLE_SCHEMA)
        assert isinstance(result, ChatPromptTemplate)

    def test_prompt_contains_passed_schema(self):
        result = build_agent_prompt(SAMPLE_SCHEMA)
        # Схема вставляется в system-сообщение через f-string
        system_template = result.messages[0].prompt.template
        assert "customers" in system_template
        assert "orders" in system_template

    def test_prompt_has_messages_placeholder(self):
        """Шаблон должен содержать MessagesPlaceholder для истории диалога."""
        result = build_agent_prompt(SAMPLE_SCHEMA)
        placeholders = [m for m in result.messages if isinstance(m, MessagesPlaceholder)]
        assert len(placeholders) == 1
        assert placeholders[0].variable_name == "messages"

    def test_prompt_mentions_select_restriction(self):
        """Промпт должен явно указывать ограничение на SELECT-only запросы."""
        result = build_agent_prompt(SAMPLE_SCHEMA)
        system_template = result.messages[0].prompt.template
        assert "SELECT" in system_template

    def test_prompt_mentions_python_tool(self):
        """Промпт должен упоминать execute_python_code."""
        result = build_agent_prompt(SAMPLE_SCHEMA)
        system_template = result.messages[0].prompt.template
        assert "execute_python_code" in system_template

    def test_prompt_has_system_message_first(self):
        """Первым сообщением должно быть системное."""
        result = build_agent_prompt(SAMPLE_SCHEMA)
        # SystemMessagePromptTemplate или tuple ('system', ...)
        first = result.messages[0]
        # Проверяем через строковое представление — langchain может менять типы
        assert "system" in str(first).lower() or hasattr(first, "prompt")

    def test_different_schemas_produce_different_prompts(self):
        schema_a = "TABLE a (id INT)"
        schema_b = "TABLE b (name TEXT)"
        prompt_a = build_agent_prompt(schema_a)
        prompt_b = build_agent_prompt(schema_b)

        template_a = prompt_a.messages[0].prompt.template
        template_b = prompt_b.messages[0].prompt.template

        assert template_a != template_b
        assert "TABLE a" in template_a
        assert "TABLE b" in template_b
