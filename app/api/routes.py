from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from langchain_core.messages import HumanMessage
from datetime import timedelta
import json

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
    
# --- Agent Stream Route ---

@router.get('/analyze/stream')
async def analyze_stream_endpoint(
    question: str,
    current_user: UserOut = Depends(get_current_user)
):
    """
    SSE-эндпоинт для наблюдения за работой агента в реальном времени.
    Использует LangGraph astream() с stream_mode='updates':
    после каждого узла графа отдаёт JSON-событие с типом шага.

    Формат событий:
      {"type": "thinking"}                          — агент формирует ответ
      {"type": "tool_call", "tool": "<имя>"}        — агент вызывает инструмент
      {"type": "tool_result", "tool": "<имя>"}      — инструмент вернул результат
      {"type": "done", "answer": "<текст>"}         — финальный ответ агента
      {"type": "error", "message": "<текст>"}       — ошибка во время работы
    """
    async def event_generator():
        # Каждый пользователь имеет свой thread_id — история сообщений изолирована
        thread_id = f"user_{current_user.id}"
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [HumanMessage(content=question)]}
        try:
            # astream с mode="updates" даёт словарь {имя_узла: изменения_стейта}
            # после каждого выполненного узла графа
            async for update in app_graph.astream(inputs, config=config, stream_mode="updates"):
                for node_name, state_update in update.items():

                    if node_name == "agent":
                        messages = state_update.get("messages", [])
                        last = messages[-1] if messages else None

                        # Всегда сначала сообщаем что агент обрабатывает запрос
                        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"

                        if last and getattr(last, "tool_calls", None):
                            # Агент решил вызвать инструмент — сообщаем какой именно
                            for tc in last.tool_calls:
                                event = {"type": "tool_call", "tool": tc["name"]}
                                yield f"data: {json.dumps(event)}\n\n"
                        elif last and last.content:
                            # Агент дал финальный текстовый ответ
                            event = {"type": "done", "answer": last.content}
                            yield f"data: {json.dumps(event)}\n\n"

                    elif node_name == "tools":
                        # Инструменты выполнились — сообщаем об этом
                        messages = state_update.get("messages", [])
                        for msg in messages:
                            event = {
                                "type": "tool_result",
                                "tool": getattr(msg, "name", "unknown"),
                            }
                            yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            print(f"Ошибка во время стриминга: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        # no-cache — браузер не должен кешировать поток
        # X-Accel-Buffering: no — отключаем буферизацию в nginx (если он есть)
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

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
