from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    """Модель запроса от пользователя"""
    question: str = Field(..., description='Вопрос пользователя на естественном языке')

class AnalyzeResponse(BaseModel):
    """Модель ответа сервера"""
    answer: str = Field(..., descroption='Ответ агента')