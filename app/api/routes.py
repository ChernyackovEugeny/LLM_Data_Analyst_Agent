from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from langchain_core.messages import HumanMessage
from datetime import timedelta

from app.database.database import engine, get_db
from app.auth.auth import oauth2_scheme, get_password_hash, verify_password, create_access_token, decode_token
from app.models.schemas import UserCreate, UserLogin, Token, UserOut, AnalyzeRequest, AnalyzeResponse
from app.core.graph import app_graph
from app.config import settings

router = APIRouter()

# --- Dependency ---
def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail='Could not validate credentials')
    
    email = payload.get("sub")
    user_id = payload.get("user_id")

    return UserOut(id=user_id, email=email)

# --- Agent Route ---
@router.post('/analyze', response_model=AnalyzeResponse)
async def analyze_endpoint(
    request: AnalyzeRequest,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Основной эндпоинт для общения с агентом.
    Принимает вопрос, возвращает ответ.
    """
    try:
        # Используем ID юзера для памяти
        thread_id = f"user_{current_user.id}"
        config = {"configurable": {"thread_id": thread_id}}
        
        # Формируем входящее сообщение
        # LangGraph ожидает список сообщений в state["messages"]
        inputs = {
            'messages': [HumanMessage(content=request.question)]
        }

        # Запускаем граф агента
        # invoke ждет завершения всего цикла (Agent -> Tool -> Agent -> END)
        result = app_graph.invoke(inputs, config=config)

        # Извлекаем ответ
        # После завершения работы последнее сообщение в списке — это ответ AI
        last_message = result["messages"][-1]

        answer_content = last_message.content

        return AnalyzeResponse(answer=answer_content)

    except Exception as e:
        # Логируем ошибку
        print(f'Error during analysis: {e}')
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    
# --- Auth Routes ---

@router.post('/auth/signup', response_model=UserOut)
def signup(user_data: UserCreate, db=Depends(get_db)):
    # Проверяем есть ли юзер
    result = db.execute(text('SELECT id FROM users WHERE email = :email'), {'email': user_data.email})

    if result.fetchone():
        raise HTTPException(status_code=400, detail='Email already registered')

    hashed_pwd = get_password_hash(user_data.password)

    query = text("""
        INSERT INTO users (email, hashed_password)
        VALUES (:email, :hashed_password)
        RETURNING id, email
    """)

    result = db.execute(query, {'email': user_data.email, 'hashed_password': hashed_pwd})
    db.commit()

    new_user = result.fetchone()
    return UserOut(id=new_user[0], email=new_user[1])

@router.post('/auth/login', response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    """
    Эндпоинт совместим со Swagger UI (форма) и обычными запросами.
    form_data.username содержит email пользователя.
    """
    email = form_data.username
    password = form_data.password

    result = db.execute(
        text('SELECT id, email, hashed_password FROM users WHERE email = :email'), 
        {'email': email}
    )
    user = result.fetchone()

    if not user or not verify_password(password, user[2]):
        raise HTTPException(status_code=401, detail='Incorrect email or password')
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={'sub': user[1], 'user_id': user[0]},
        expires_delta=access_token_expires
    )

    return {'access_token': access_token, 'token_type': 'bearer'}
