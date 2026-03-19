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
    answer: str = Field(..., descroption='Ответ агента')