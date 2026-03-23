from app.core.state import AgentState


def agent_node(state: AgentState, llm, prompt_template):
    """Узел агента. Вызывает LLM."""

    # Формируем полный промпт
    messages = prompt_template.invoke(state)

    # Логируем что отправляем в LLM
    print("\n========== ЗАПРОС К LLM ==========")
    for msg in messages.messages:
        print(f"[{msg.__class__.__name__}]: {msg.content[:300]}")
    print("===================================\n")

    # Вызываем LLM с инструментами
    response = llm.invoke(messages)

    # Логируем что LLM ответил
    print("\n========== ОТВЕТ LLM ==========")
    print(f"content: {response.content}")
    print(f"tool_calls: {response.tool_calls}")
    print("================================\n")

    return {'messages': [response]}
