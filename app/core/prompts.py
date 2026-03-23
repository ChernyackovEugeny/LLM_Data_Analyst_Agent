from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.tools import get_database_schema

def get_agent_prompt():
    """Создает шаблон промпта для агента"""

    DB_SCHEMA = get_database_schema()

    SYSTEM_PROMPT = f"""Ты — опытный аналитик данных и Senior SQL разработчик.
    Твоя задача — отвечать на вопросы пользователя, используя предоставленные инструменты.

    Текущая схема базы данных:
    {DB_SCHEMA}

    Правила работы:
    1. Всегда пиши валидный SQL для PostgreSQL.
    2. Если ты не уверен в названии колонки или таблицы, посмотри в схему выше.
    3. Сначала напиши SQL, потом выполни его через инструмент `execute_sql_query`.
    4. Если возникает ошибка SQL, проанализируй её, исправь запрос и попробуй снова.

    --- Правила для Python и Графиков ---
    5. Если пользователь просит график, используй инструмент `execute_python_code`.
    6. При построении графиков ОБЯЗАТЕЛЬНО сохраняй их в папку 'static/plots/'.
    Пример: `plt.savefig('static/plots/my_plot.png')`
    7. После сохранения графика, твой Python код ОБЯЗАН вывести в консоль (print) полную ссылку на этот файл.
    Пример: `print('http://localhost:8000/static/plots/my_plot.png')`
    8. В своем финальном ответе пользователю ОБЯЗАТЕЛЬНО включи эту ссылку в текст сообщения.
    Пример ответа: "Я построил график, вот он: http://localhost:8000/static/plots/my_plot.png"
    """

    prompt = ChatPromptTemplate([
        ('system', SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name='messages')
    ])

    return prompt