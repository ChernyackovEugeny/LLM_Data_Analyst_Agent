from functools import partial
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.config import settings

from app.core.state import AgentState
from app.core.nodes import agent_node, summarize_node
from app.core.edges import should_continue

from app.tools import execute_sql_query
from app.tools.python_tool import execute_python_code

# --- Инициализация ресурсов ---

# llm — чистый, без инструментов. Используется в summarize_node.
# Передавать llm_with_tools в summarize_node опасно: DeepSeek может вызвать
# SQL-инструмент вместо написания текстового резюме.
llm = ChatOpenAI(
    model=settings.LLM_MODEL_NAME,
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.LLM_BASE_URL,
    temperature=0
)

tools = [execute_sql_query, execute_python_code]
llm_with_tools = llm.bind_tools(tools)

# --- Подготовка узлов ---
# prompt_template больше не строится здесь — nodes.py делает это динамически
# на каждый запрос, чтобы агент видел актуальную схему (включая CSV пользователя).
# LangGraph сам инжектирует config в agent_node — partial связывает только llm.
agent_node_runnable = partial(
    agent_node,
    llm=llm_with_tools,
)

# summarize_node получает plain llm (без tools)
summarize_node_runnable = partial(
    summarize_node,
    llm=llm,
)

tool_node_runnable = ToolNode(tools)

# --- Сборка графа ---
graph = StateGraph(AgentState)

graph.add_node("agent", agent_node_runnable)
graph.add_node("tools", tool_node_runnable)
graph.add_node("summarize", summarize_node_runnable)

graph.set_entry_point("agent")

graph.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "summarize": "summarize",
        "end": END,
    }
)

# Обычные переходы
graph.add_edge("tools", "agent")
graph.add_edge("summarize", END)

# --- Компиляция ---
# raw_graph — несобранный граф. Компилируется в app/app.py (lifespan)
# с AsyncPostgresSaver для персистентной истории диалогов.
# app_graph инициализируется там же и переприсваивается через модульную ссылку.
raw_graph = graph
app_graph = None  # заполняется lifespan перед обработкой первого запроса
