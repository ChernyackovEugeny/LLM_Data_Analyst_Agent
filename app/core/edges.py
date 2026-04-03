from app.config import settings
from app.core.state import AgentState


def should_continue(state: AgentState) -> str:
    """
    Определяет, нужно ли продолжать выполнение инструментов.
    Возвращает имя следующего узла.

    Порядок проверок:
    1. Если есть tool_calls — идём в 'tools' (приоритет).
    2. Если сообщений больше SUMMARY_THRESHOLD — идём в 'summarize'.
    3. Иначе — END.
    """

    messages = state["messages"]
    last_message = messages[-1]

    # Если последнее сообщение содержит вызов инструмента -> идем в инструменты
    if getattr(last_message, "tool_calls", None):
        return "tools"

    # Если сообщений накопилось больше порога — запускаем суммаризацию перед выходом
    if len(messages) > settings.SUMMARY_THRESHOLD:
        return "summarize"

    # Иначе работа агента закончена -> идем в END
    return "end"
