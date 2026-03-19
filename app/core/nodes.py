from app.core.state import AgentState


def agent_node(state: AgentState, llm, prompt_template):
    """Узел агента. Вызывает LLM."""

    # Формируем полный промпт
    messages = prompt_template.invoke(state)

    # Вызываем LLM с инструментами
    response = llm.invoke(messages)

    return {'messages': [response]}
