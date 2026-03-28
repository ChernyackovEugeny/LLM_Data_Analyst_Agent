from langchain_core.runnables import RunnableConfig

from app.core.state import AgentState
from app.core.prompts import build_agent_prompt
from app.tools.schemas import get_database_schema


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

    # Логируем что отправляем в LLM
    print("\n========== ЗАПРОС К LLM ==========")
    for msg in messages.messages:
        print(f"[{msg.__class__.__name__}]: {msg.content[:300]}")
    print("===================================\n")

    # Вызываем LLM с привязанными инструментами
    response = llm.invoke(messages)

    # Логируем что LLM ответил
    print("\n========== ОТВЕТ LLM ==========")
    print(f"content: {response.content}")
    print(f"tool_calls: {response.tool_calls}")
    print("================================\n")

    return {'messages': [response]}
