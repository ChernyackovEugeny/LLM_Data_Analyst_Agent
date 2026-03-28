import logging

from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Cookie, Response
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from langchain_core.messages import HumanMessage
from datetime import timedelta
import json
import io
import pandas as pd

logger = logging.getLogger(__name__)

from app.database.database import engine, get_db
from app.auth.auth import get_password_hash, verify_password, create_access_token, create_refresh_token, decode_token
from app.models.schemas import UserCreate, UserLogin, UserOut, AnalyzeRequest, AnalyzeResponse, UploadResponse, ChatOut, MessageOut
from app.core import graph as graph_module
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
        # ainvoke ждет завершения всего цикла (Agent -> Tool -> Agent -> END)
        result = await graph_module.app_graph.ainvoke(inputs, config=config)

        # Извлекаем ответ
        # После завершения работы последнее сообщение в списке — это ответ AI
        last_message = result["messages"][-1]

        answer_content = last_message.content

        return AnalyzeResponse(answer=answer_content)

    except Exception as e:
        logger.exception("Ошибка во время синхронного анализа")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# --- Agent Stream Route ---

@router.get('/analyze/stream')
async def analyze_stream_endpoint(
    question: str,
    chat_id: int,
    current_user: UserOut = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    SSE-эндпоинт для наблюдения за работой агента в реальном времени.
    Принимает chat_id — история изолирована по чату, сообщения сохраняются в БД.

    Формат событий:
      {"type": "thinking"}                          — агент формирует ответ
      {"type": "tool_call", "tool": "<имя>"}        — агент вызывает инструмент
      {"type": "tool_result", "tool": "<имя>"}      — инструмент вернул результат
      {"type": "done", "answer": "<текст>"}         — финальный ответ агента
      {"type": "error", "message": "<текст>"}       — ошибка во время работы
    """
    # Проверяем что чат принадлежит пользователю
    row = db.execute(
        text("SELECT id, title FROM chats WHERE id = :cid AND user_id = :uid"),
        {"cid": chat_id, "uid": current_user.id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat_title = row[1]

    # Сохраняем вопрос пользователя
    db.execute(
        text("INSERT INTO messages (chat_id, role, content) VALUES (:cid, 'user', :content)"),
        {"cid": chat_id, "content": question}
    )
    # Auto-title: если это первое сообщение — обновляем заголовок чата
    if chat_title == 'Новый чат':
        title = question[:50] + ('...' if len(question) > 50 else '')
        db.execute(
            text("UPDATE chats SET title = :title WHERE id = :cid"),
            {"title": title, "cid": chat_id}
        )
    db.commit()

    async def event_generator():
        # thread_id привязан к чату — каждый чат имеет независимую историю LangGraph.
        # user_id передаётся в agent_node для формирования схемы БД с CSV-таблицей пользователя.
        thread_id = f"chat_{chat_id}"
        config = {"configurable": {"thread_id": thread_id, "user_id": current_user.id}}
        inputs = {"messages": [HumanMessage(content=question)]}
        final_answer = ""
        try:
            # astream с mode="updates" даёт словарь {имя_узла: изменения_стейта}
            # после каждого выполненного узла графа
            async for update in graph_module.app_graph.astream(inputs, config=config, stream_mode="updates"):
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
                            # Агент дал финальный текстовый ответ — запоминаем для сохранения
                            final_answer = last.content
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
            logger.exception("Ошибка во время стриминга")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Сохраняем финальный ответ агента после завершения стрима
            if final_answer:
                db.execute(
                    text("INSERT INTO messages (chat_id, role, content) VALUES (:cid, 'agent', :content)"),
                    {"cid": chat_id, "content": final_answer}
                )
                db.commit()

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


# --- Chat Routes ---

@router.post('/chats', response_model=ChatOut)
def create_chat(current_user: UserOut = Depends(get_current_user), db=Depends(get_db)):
    result = db.execute(
        text("INSERT INTO chats (user_id) VALUES (:uid) RETURNING id, title, created_at"),
        {"uid": current_user.id}
    )
    db.commit()
    row = result.fetchone()
    return ChatOut(id=row[0], title=row[1], created_at=row[2])


@router.get('/chats', response_model=list[ChatOut])
def list_chats(current_user: UserOut = Depends(get_current_user), db=Depends(get_db)):
    result = db.execute(
        text("SELECT id, title, created_at FROM chats WHERE user_id = :uid ORDER BY created_at DESC"),
        {"uid": current_user.id}
    )
    return [ChatOut(id=r[0], title=r[1], created_at=r[2]) for r in result.fetchall()]


@router.delete('/chats/{chat_id}')
def delete_chat(chat_id: int, current_user: UserOut = Depends(get_current_user), db=Depends(get_db)):
    # Проверяем владение
    row = db.execute(
        text("SELECT id FROM chats WHERE id = :cid AND user_id = :uid"),
        {"cid": chat_id, "uid": current_user.id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")

    thread_id = f"chat_{chat_id}"
    # Удаляем LangGraph checkpoints для этого чата
    db.execute(text("DELETE FROM checkpoint_writes WHERE thread_id = :tid"), {"tid": thread_id})
    db.execute(text("DELETE FROM checkpoint_blobs WHERE thread_id = :tid"), {"tid": thread_id})
    db.execute(text("DELETE FROM checkpoints WHERE thread_id = :tid"), {"tid": thread_id})
    # Удаляем чат (CASCADE удалит messages автоматически)
    db.execute(text("DELETE FROM chats WHERE id = :cid"), {"cid": chat_id})
    db.commit()
    return {"message": "Chat deleted"}


@router.get('/chats/{chat_id}/messages', response_model=list[MessageOut])
def get_chat_messages(chat_id: int, current_user: UserOut = Depends(get_current_user), db=Depends(get_db)):
    # Проверяем владение
    row = db.execute(
        text("SELECT id FROM chats WHERE id = :cid AND user_id = :uid"),
        {"cid": chat_id, "uid": current_user.id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = db.execute(
        text("SELECT role, content, created_at FROM messages WHERE chat_id = :cid ORDER BY created_at ASC"),
        {"cid": chat_id}
    )
    return [MessageOut(role=r[0], content=r[1], created_at=r[2]) for r in result.fetchall()]


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
    Токены устанавливаются как HttpOnly cookie — не возвращаются в теле ответа.
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
    refresh_tok = create_refresh_token({'sub': user[1], 'user_id': user[0]})

    # access_token: короткоживущий (30 мин), отправляется с каждым запросом (path=/)
    # HttpOnly: JS не может прочитать cookie → XSS не украдёт токен.
    # SameSite=Lax: браузер не отправляет cookie на cross-site POST → CSRF-защита.
    # Secure: только HTTPS (False в dev, настраивается через COOKIE_SECURE в .env).
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    # refresh_token: долгоживущий (30 дней), отправляется ТОЛЬКО к /auth/refresh (path=).
    # path=/api/v1/auth/refresh: браузер не отправляет этот cookie ни к каким другим endpoint-ам —
    # refresh token не утечёт с обычными запросами к /analyze, /auth/me и т.д.
    response.set_cookie(
        key="refresh_token",
        value=refresh_tok,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth/refresh",
    )
    return {"message": "Login successful"}


@router.post('/auth/refresh')
def refresh_tokens(response: Response, refresh_token: str = Cookie(default=None)):
    """
    Обновляет access_token по действующему refresh_token.
    Token rotation: выдаётся новый refresh_token, активный пользователь не вылетает никогда.
    30 дней бездействия → перелогин.
    """
    if not refresh_token:
        raise HTTPException(status_code=401, detail='No refresh token')
    payload = decode_token(refresh_token)
    if not payload or payload.get('type') != 'refresh':
        raise HTTPException(status_code=401, detail='Invalid refresh token')

    email = payload.get('sub')
    user_id = payload.get('user_id')

    new_access = create_access_token(
        {'sub': email, 'user_id': user_id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    new_refresh = create_refresh_token({'sub': email, 'user_id': user_id})

    response.set_cookie(
        key="access_token",
        value=new_access,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth/refresh",
    )
    return {"message": "Tokens refreshed"}


@router.post('/auth/logout')
def logout(response: Response):
    # JS не может удалить HttpOnly cookie — только сервер может.
    # delete_cookie ставит Max-Age=0: браузер немедленно удаляет cookie.
    response.delete_cookie(key="access_token", samesite="lax")
    response.delete_cookie(key="refresh_token", samesite="lax", path="/api/v1/auth/refresh")
    return {"message": "Logged out"}


@router.get('/auth/me', response_model=UserOut)
def get_me(current_user: UserOut = Depends(get_current_user)):
    """Проверка состояния аутентификации. Используется фронтендом при загрузке страницы."""
    return current_user
