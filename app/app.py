from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router as api_router


# Создаем экземпляр приложения
app = FastAPI(
    title=settings.APP_NAME,
    description='API для аналитического агента на базе LLM и LangGraph',
    version='1.0.0'
)

# Настройка CORS (разрешаем запросы с фронтендов)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

# Подключаем роуты
app.include_router(api_router, prefix='/api/v1')

# Эндпоинт для проверки здоровья
@app.get('/health')
async def health_check():
    return {'status': 'ok', 'model': settings.LLM_MODEL_NAME}

