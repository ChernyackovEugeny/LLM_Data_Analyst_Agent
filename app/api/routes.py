from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Cookie, Response
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from langchain_core.messages import HumanMessage
from datetime import timedelta
import json
import io
import pandas as pd

from app.database.database import engine, get_db
from app.auth.auth import get_password_hash, verify_password, create_access_token, decode_token
from app.models.schemas import UserCreate, UserLogin, UserOut, AnalyzeRequest, AnalyzeResponse, UploadResponse
from app.core.graph import app_graph
from app.config import settings

# Максимальный размер загружаемого CSV-файла — 10 МБ
MAX_CSV_SIZE_BYTES = 10 * 1024 * 1024

router = APIRouter()

# --- Dependency ---
# Читаем токен из HttpOnly cookie "access_token".
# Cookie(default=None): если cookie отсутствует — возвращаем 401, а не 422 (validation error).
def get_current_user(access_token: str = Cookie(default=None), db=Depends(get_db)):
    if not access_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    payload = decode_token(access_token)
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
        # Используем ID юзера для памяти и для динамической схемы БД
        thread_id = f"user_{current_user.id}"
        config = {"configurable": {"thread_id": thread_id, "user_id": current_user.id}}
        
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
        # Каждый пользователь имеет свой thread_id — история сообщений изолирована.
        # user_id передаётся в agent_node для формирования схемы БД с CSV-таблицей пользователя.
        thread_id = f"user_{current_user.id}"
        config = {"configurable": {"thread_id": thread_id, "user_id": current_user.id}}
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

# --- CSV Upload Route ---

@router.post('/upload-csv', response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: UserOut = Depends(get_current_user)
):
    """
    Загружает CSV-файл и сохраняет его как таблицу csv_u{user_id} в PostgreSQL.
    Если таблица уже существует — полностью заменяется (вариант 4: один CSV на пользователя).
    После загрузки агент сразу видит новую таблицу — перезапуск не нужен.
    """

    # Проверяем расширение файла
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail='Допускаются только файлы формата .csv')

    # Читаем содержимое файла целиком
    contents = await file.read()

    # Проверяем размер — защита от слишком больших файлов
    if len(contents) > MAX_CSV_SIZE_BYTES:
        raise HTTPException(status_code=413, detail='Файл слишком большой. Максимальный размер — 10 МБ.')

    # Пробуем декодировать: сначала UTF-8, затем Windows-1252 (cp1252)
    # Это покрывает большинство CSV из Excel и других Windows-программ
    try:
        text_data = contents.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text_data = contents.decode('cp1252')
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=422,
                detail='Не удалось определить кодировку файла. Используйте UTF-8 или Windows-1252.'
            )

    # Парсим CSV через pandas
    try:
        df = pd.read_csv(io.StringIO(text_data))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f'Ошибка разбора CSV: {e}')

    if df.empty:
        raise HTTPException(status_code=422, detail='Файл CSV пуст или не содержит данных.')

    # Sanitize имён колонок: пробелы → _, дефисы → _, строчные буквы
    # Без этого PostgreSQL может отказать или имена станут неудобными в SQL
    df.columns = [
        col.strip().lower().replace(' ', '_').replace('-', '_')
        for col in df.columns
    ]

    # Имя таблицы привязано к пользователю — изоляция данных между пользователями
    table_name = f"csv_u{current_user.id}"

    # Записываем в PostgreSQL: if_exists='replace' = DROP IF EXISTS + CREATE + INSERT
    try:
        df.to_sql(
            name=table_name,
            con=engine,           # engine уже импортирован выше
            if_exists='replace',  # заменяем старую таблицу целиком
            index=False,          # не сохраняем индекс pandas как отдельную колонку
            schema='public'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Ошибка записи в базу данных: {e}')

    return UploadResponse(
        table_name=table_name,
        columns=list(df.columns),
        row_count=len(df),
        message=f'Файл "{file.filename}" успешно загружен. Таблица {table_name} создана.'
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

@router.post('/auth/login')
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    """
    Эндпоинт совместим со Swagger UI (форма) и обычными запросами.
    form_data.username содержит email пользователя.
    Токен устанавливается как HttpOnly cookie — не возвращается в теле ответа.
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

    access_token = create_access_token(
        data={'sub': user[1], 'user_id': user[0]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # HttpOnly: JS не может прочитать cookie → XSS не украдёт токен.
    # SameSite=Lax: браузер не отправляет cookie на cross-site POST → CSRF-защита.
    # Secure: только HTTPS (False в dev, настраивается через COOKIE_SECURE в .env).
    # max_age: браузер автоматически удаляет cookie после истечения токена.
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"message": "Login successful"}


@router.post('/auth/logout')
def logout(response: Response):
    # JS не может удалить HttpOnly cookie — только сервер может.
    # delete_cookie ставит Max-Age=0: браузер немедленно удаляет cookie.
    response.delete_cookie(key="access_token", samesite="lax")
    return {"message": "Logged out"}


@router.get('/auth/me', response_model=UserOut)
def get_me(current_user: UserOut = Depends(get_current_user)):
    """Проверка состояния аутентификации. Используется фронтендом при загрузке страницы."""
    return current_user
