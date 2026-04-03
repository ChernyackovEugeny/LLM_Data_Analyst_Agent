from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# Определяем состояние агента.
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str  # накопленное резюме старой истории; пустая строка = нет резюме