from pydantic import BaseModel, Field, EmailStr
from typing import Optional


# --- Auth Models ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserOut(BaseModel):
    id: int
    email: str

# --- Agent Models ---
class AnalyzeRequest(BaseModel):
    """Модель запроса от пользователя"""
    question: str = Field(..., description='Вопрос пользователя на естественном языке')
    thread_id: Optional[str] = None

class AnalyzeResponse(BaseModel):
    """Модель ответа сервера"""
    answer: str = Field(..., description='Ответ агента')


# --- CSV Upload ---
class UploadResponse(BaseModel):
    """Ответ после успешной загрузки CSV-файла"""
    table_name: str = Field(..., description='Имя созданной таблицы в PostgreSQL')
    columns: list[str] = Field(..., description='Список колонок из CSV')
    row_count: int = Field(..., description='Количество загруженных строк')
    message: str = Field(..., description='Сообщение об успехе для пользователя')