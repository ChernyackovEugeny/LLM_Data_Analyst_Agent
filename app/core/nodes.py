import logging

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.core.state import AgentState
from app.core.prompts import build_agent_prompt
from app.tools.schemas import get_database_schema

logger = logging.getLogger(__name__)


def sanitize_messages(messages: list) -> list:
    """
    Убирает из истории "висячие" tool_calls — AIMessage с tool_calls,
    за которыми не следует ToolMessage для каждого tool_call_id.

    Такое состояние возникает когда инструмент упал с исключением до того
    как ToolNode успел сохранить ToolMessage в checkpoint. DeepSeek API
    отвергает такую историю с ошибкой 400 invalid_request_error.

    Заменяем AIMessage с незакрытыми tool_calls на AIMessage
    только с content (если он есть), + добавляем синтетический ToolMessage
    с сообщением об ошибке — чтобы история оставалась валидной.
    """
    result = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            result.append(msg)
            i += 1
            continue

        # Собираем id всех tool_calls этого AIMessage
        expected_ids = {tc["id"] for tc in tool_calls}

        # Смотрим сколько ToolMessage идёт следом
        j = i + 1
        found_ids = set()
        while j < len(messages) and isinstance(messages[j], ToolMessage):
            found_ids.add(messages[j].tool_call_id)
            j += 1

        if expected_ids == found_ids:
            # Всё в порядке — tool_calls закрыты ToolMessage-ами
            result.extend(messages[i:j])
            i = j
        else:
            # Висячий tool_call — закрываем синтетическим ToolMessage
            logger.warning(
                "Обнаружен висячий tool_call в истории (ids: %s), применяем санацию",
                expected_ids - found_ids,
            )
            # Сохраняем AIMessage без tool_calls (только content)
            if msg.content:
                result.append(AIMessage(content=msg.content))
            # Добавляем синтетический ToolMessage для каждого незакрытого id
            for tc in tool_calls:
                if tc["id"] not in found_ids:
                    result.append(ToolMessage(
                        content="Инструмент завершился с ошибкой. Попробуй выполнить запрос заново.",
                        tool_call_id=tc["id"],
                    ))
            # Добавляем уже существующие ToolMessage (если часть была)
            result.extend(messages[i + 1:j])
            i = j

    return result


def agent_node(state: AgentState, llm, config: RunnableConfig):
    """
    Узел агента в LangGraph-графе.

    Получает свежую схему БД на каждый вызов — это ключевой момент:
    без этого агент не видел бы CSV-таблицы, загруженные после старта сервера.

    config — автоматически инжектируется LangGraph'ом.
    Из него достаём user_id, чтобы показать агенту только таблицы текущего пользователя.

    Если в state есть summary — инжектируем его как SystemMessage в начало сообщений,
    чтобы агент помнил суть предыдущих разговоров даже после суммаризации.
    """

    # Извлекаем user_id из LangGraph-конфига (передаётся из routes.py)
    user_id: int | None = config.get("configurable", {}).get("user_id")

    # Получаем актуальную схему БД с учётом CSV-таблицы пользователя
    db_schema = get_database_schema(user_id=user_id)

    # Строим промпт с актуальной схемой
    prompt_template = build_agent_prompt(db_schema)

    # Санируем историю — убираем висячие tool_calls которые могут появиться
    # если инструмент упал до того как ToolNode записал ToolMessage в checkpoint.
    clean_messages = sanitize_messages(list(state["messages"]))

    # Инжектируем summary в начало сообщений если он есть.
    # Не модифицируем state напрямую — создаём локальный список только для вызова шаблона.
    summary = state.get("summary", "")
    if summary:
        summary_message = SystemMessage(
            content=f"Краткое резюме предыдущего разговора:\n{summary}"
        )
        messages_for_prompt = [summary_message] + clean_messages
    else:
        messages_for_prompt = clean_messages

    # Формируем полный список сообщений для LLM
    messages = prompt_template.invoke({"messages": messages_for_prompt})

    logger.debug("Запрос к LLM: %d сообщений", len(messages.messages))
    for msg in messages.messages:
        logger.debug("[%s]: %s", msg.__class__.__name__, str(msg.content)[:300])

    # Вызываем LLM с привязанными инструментами
    response = llm.invoke(messages)

    logger.debug("Ответ LLM: content=%s tool_calls=%s", str(response.content)[:200], response.tool_calls)

    return {'messages': [response]}


def summarize_node(state: AgentState, llm) -> dict:
    """
    Узел суммаризации в LangGraph-графе.

    Срабатывает когда число сообщений в state превышает SUMMARY_THRESHOLD.
    Сжимает старые сообщения в текстовый summary через LLM (без tools),
    затем удаляет их из state через RemoveMessage, оставляя только последние
    SUMMARY_KEEP_LAST сообщений.

    Использует plain LLM без bind_tools — чтобы исключить случайный вызов
    инструментов вместо написания текстового резюме.

    Инкрементальная суммаризация: если summary уже существует — дополняем его,
    а не создаём с нуля. Это сохраняет всю историю в сжатом виде.
    """
    messages = state["messages"]
    existing_summary = state.get("summary", "")

    # Сообщения которые нужно сжать (всё кроме последних KEEP_LAST)
    messages_to_summarize = messages[:-settings.SUMMARY_KEEP_LAST]

    logger.info(
        "Суммаризация: сжимаем %d сообщений, оставляем %d",
        len(messages_to_summarize),
        settings.SUMMARY_KEEP_LAST,
    )

    # Формируем запрос на суммаризацию.
    # Если summary уже есть — просим дополнить его (инкрементально).
    if existing_summary:
        summarize_prompt = (
            f"Существующее резюме предыдущего разговора:\n{existing_summary}\n\n"
            "Дополни это резюме следующими новыми сообщениями, сохраняя все важные факты."
        )
    else:
        summarize_prompt = (
            "Создай краткое резюме следующего разговора между пользователем и "
            "аналитическим агентом. Сохрани ключевые вопросы, SQL-запросы, "
            "числовые результаты и выводы."
        )

    summary_request = [
        SystemMessage(content=summarize_prompt),
        *messages_to_summarize,
        HumanMessage(content="Напиши резюме на русском языке, кратко и по делу."),
    ]

    response = llm.invoke(summary_request)

    logger.info("Суммаризация завершена, длина резюме: %d символов", len(response.content))

    # Удаляем старые сообщения через RemoveMessage.
    # add_messages reducer обрабатывает RemoveMessage как инструкцию удаления по id.
    # Простой возврат {"messages": messages[-N:]} НЕ заменит список, а добавит дубли.
    messages_to_remove = [
        RemoveMessage(id=m.id) for m in messages_to_summarize
    ]

    return {
        "summary": response.content,
        "messages": messages_to_remove,
    }
