import glob
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings
from app.core import graph as graph_module
from app.api.routes import router as api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan: выполняется при старте (до yield) и при shutdown (после yield).

    Порядок при старте:
      1. Очистка static/plots/ — удаляем аварийные temp-скрипты и старые PNG.
      2. Инициализация AsyncPostgresSaver — создаём таблицы чекпоинтера если нет.
      3. Компиляция графа с персистентным чекпоинтером.
    """

    # -------------------------------------------------------------------------
    # 1. Очистка static/plots/
    # -------------------------------------------------------------------------
    plots_dir = "static/plots"
    os.makedirs(plots_dir, exist_ok=True)

    # _tmp_*.py — остатки упавших выполнений. При нормальной работе они удаляются
    # в finally-блоке python_tool.py. Если файлы есть при старте — это аварийный
    # остаток предыдущего запуска. Удаляем всегда.
    for f in glob.glob(os.path.join(plots_dir, "_tmp_*.py")):
        try:
            os.remove(f)
            logger.info(f"Очищен аварийный temp-скрипт: {f}")
        except OSError:
            pass

    # *.png старше PLOTS_MAX_AGE_HOURS — удаляем по возрасту.
    # PNG хранить вечно не нужно: они ссылаются из истории диалогов,
    # но старые диалоги и так недоступны через UI.
    # PLOTS_MAX_AGE_HOURS=0 в .env отключает очистку PNG.
    if settings.PLOTS_MAX_AGE_HOURS > 0:
        cutoff = time.time() - settings.PLOTS_MAX_AGE_HOURS * 3600
        removed = 0
        for f in glob.glob(os.path.join(plots_dir, "*.png")):
            try:
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
                    removed += 1
            except OSError:
                pass
        if removed:
            logger.info(f"Очищено {removed} устаревших PNG из {plots_dir}")

    # -------------------------------------------------------------------------
    # 2. AsyncPostgresSaver
    # -------------------------------------------------------------------------
    # AsyncPostgresSaver требует psycopg3 URL (без "+psycopg2").
    # settings.DATABASE_URL хранит SQLAlchemy-формат: postgresql+psycopg2://...
    pg_url = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")

    async with AsyncPostgresSaver.from_conn_string(pg_url) as checkpointer:
        # setup() идемпотентен: создаёт таблицы checkpoints / checkpoint_blobs /
        # checkpoint_migrations если они не существуют. Повторный вызов безопасен.
        await checkpointer.setup()

        # Компилируем граф с персистентным чекпоинтером.
        # graph_module.app_graph переприсваивается — routes.py читает его через
        # модульную ссылку (from app.core import graph as graph_module),
        # поэтому все последующие запросы используют актуальный объект.
        graph_module.app_graph = graph_module.raw_graph.compile(checkpointer=checkpointer)
        logger.info("LangGraph: AsyncPostgresSaver инициализирован, история диалогов персистентна")

        yield
        # После yield: shutdown. AsyncPostgresSaver закрывает соединение автоматически
        # через async context manager.


app = FastAPI(
    title=settings.APP_NAME,
    description='API для аналитического агента на базе LLM и LangGraph',
    version='1.0.0',
    lifespan=lifespan,
)

# Монтируем статические файлы
# Теперь файлы доступны по http://localhost:8000/static/plots/image.png
app.mount("/static", StaticFiles(directory="static"), name="static")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # конкретные origins из config (не wildcard)
    allow_credentials=True,                   # нужно для HttpOnly cookie в cross-origin dev
    allow_methods=["GET", "POST"],            # только методы которые реально используются
    allow_headers=["Content-Type"],           # Authorization header больше не нужен (cookie)
)

# Подключаем роуты
app.include_router(api_router, prefix='/api/v1')

# Эндпоинт для проверки здоровья
@app.get('/health')
async def health_check():
    return {'status': 'ok', 'model': settings.LLM_MODEL_NAME}
