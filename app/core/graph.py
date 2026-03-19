from functools import partial
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.core.state import AgentState
from app.core.nodes import agent_node
from app.core.edges import should_continue
from app.core.prompts import get_agent_prompt
from app.tools import execute_sql_query

# --- Инициализация ресурсов ---
llm = ChatOpenAI(
    model=settings.LLM_MODEL_NAME,
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.LLM_BASE_URL,
    temperature=0
)

tools = [execute_sql_query]
llm_with_tools = llm.bind_tools(tools)
prompt_template = get_agent_prompt()

# --- Подготовка функций узлов (Partial Application) ---
# Превращаем функцию 3-х аргументов в функцию 1-го аргумента (state)
agent_node_runnable = partial(
    agent_node,
    llm=llm_with_tools,
    prompt_template=prompt_template
)

tool_node_runnable = ToolNode(tools)

# --- Сборка графа ---
graph = StateGraph(AgentState)

graph.add_node('agent', agent_node_runnable)
graph.add_node('tools', tool_node_runnable)

graph.set_entry_point('agent')

graph.add_conditional_edges(
    'agent',
    should_continue,
    {
        'tools': 'tools',
        'end': END
    }
)

# Обычные переходы
graph.add_edge("tools", "agent")

# --- Компиляция ---
app_graph = graph.compile()