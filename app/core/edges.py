from app.core.state import AgentState

def should_continue(state: AgentState):
    """
    Определяет, нужно ли продолжать выполнение инструментов.
    Возвращает имя следующего узла.
    """

    messages = state['messages']
    last_message = messages[-1]

    # Если последнее сообщение содержит вызов инструмента -> идем в инструменты
    if last_message.tool_calls:
        return 'tools'
    
    # Иначе работа агента закончена -> идем в END
    return 'end'