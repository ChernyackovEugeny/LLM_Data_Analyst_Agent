import logging

from langchain_core.runnables import RunnableConfig

from app.core.state import AgentState
from app.core.prompts import build_agent_prompt
from app.tools.schemas import get_database_schema

logger = logging.getLogger(__name__)


def agent_node(state: AgentState, llm, config: RunnableConfig):
    """
    Узел агента в LangGraph-графе.

    Получает свежую схему БД на каждый вызов — это ключевой момент:
    без этого агент не видел бы CSV-таблицы, загруженные после старта сервера.

    config — автоматически инжектируется LangGraph'ом.
    Из него достаём user_id, чтобы показать агенту только таблицы текущего пользователя.
    """

    # Извлекаем user_id из LangGraph-конфига (передаётся из routes.py)
    user_id: int | None = config.get("configurable", {}).get("user_id")

    # Получаем актуальную схему БД с учётом CSV-таблицы пользователя
    db_schema = get_database_schema(user_id=user_id)

    # Строим промпт с актуальной схемой
    prompt_template = build_agent_prompt(db_schema)

    # Формируем полный список сообщений для LLM
    messages = prompt_template.invoke(state)

    logger.debug("Запрос к LLM: %d сообщений", len(messages.messages))
    for msg in messages.messages:
        logger.debug("[%s]: %s", msg.__class__.__name__, msg.content[:300])

    # Вызываем LLM с привязанными инструментами
    response = llm.invoke(messages)

    logger.debug("Ответ LLM: content=%s tool_calls=%s", response.content[:200], response.tool_calls)

    return {'messages': [response]}
