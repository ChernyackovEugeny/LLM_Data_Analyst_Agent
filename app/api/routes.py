from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.core.graph import app_graph

router = APIRouter()

@router.post('/analyze', response_model=AnalyzeResponse)
async def analyze_endpoint(request: AnalyzeRequest):
    """
    Основной эндпоинт для общения с агентом.
    Принимает вопрос, возвращает ответ.
    """

    try:
        # Формируем входящее сообщение
        # LangGraph ожидает список сообщений в state["messages"]
        inputs = {
            'messages': [HumanMessage(content=request.question)]
        }

        # Запускаем граф агента
        # invoke ждет завершения всего цикла (Agent -> Tool -> Agent -> END)
        result = app_graph.invoke(inputs)

        # Извлекаем ответ
        # После завершения работы последнее сообщение в списке — это ответ AI
        last_message = result["messages"][-1]

        answer_content = last_message.content

        return AnalyzeResponse(answer=answer_content)

    except Exception as e:
        # Логируем ошибку
        print(f'Error during analysis: {e}')
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")