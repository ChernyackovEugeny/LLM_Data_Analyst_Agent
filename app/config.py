from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Настройки приложения.
    Автоматически считывает переменные из .env файла.
    """

    APP_NAME: str = 'LLM Data Analyst Agent'
    DEBUG: bool = True

    # --- Настройки LLM (DeepSeek) ---
    DEEPSEEK_API_KEY: str
    LLM_MODEL_NAME: str = "deepseek-chat" 
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"

    # --- Настройки Базы Данных ---
    DATABASE_URL: str

    # Read-only подключение — используется ТОЛЬКО в sql_tool.py.
    # analyst_readonly имеет только SELECT: DDL/DML отклоняется на уровне БД.
    # Дефолт = пустая строка, чтобы бэкенд стартовал при локальной разработке
    # до того как readonly-пользователь настроен. sql_tool упадёт при первом
    # SQL-запросе, но /auth/login будет работать нормально.
    READONLY_DATABASE_URL: str = ""

    # --- Security (Auth) ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- CORS ---
    # pydantic-settings парсит list[str] из .env как JSON-массив:
    #   ALLOWED_ORIGINS=["http://localhost","http://localhost:5173"]
    # Дефолт покрывает: Docker/nginx (порт 80) + Vite dev server (5173).
    ALLOWED_ORIGINS: list[str] = ["http://localhost", "http://localhost:5173", "http://localhost:3000"]

    # --- HttpOnly Cookie ---
    # True = cookie передаётся только по HTTPS (production).
    # False = разрешаем HTTP (локальная разработка).
    # В production с HTTPS поставить COOKIE_SECURE=true в .env.
    COOKIE_SECURE: bool = False
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Python Sandbox (python_tool.py) ---
    # True = запускать код в Docker-контейнере (production, docker-compose).
    # False = subprocess fallback (локальная разработка без Docker Compose).
    USE_SANDBOX: bool = False

    # Имя Docker volume для графиков: {COMPOSE_PROJECT_NAME}_plots_data.
    # Используется как общая шина между backend и sandbox-контейнером (DooD).
    PLOTS_VOLUME_NAME: str = "llm_data_analyst_agent_plots_data"

    # Имя Docker-образа для sandbox-контейнеров.
    SANDBOX_IMAGE_NAME: str = "analyst-sandbox:latest"

    # --- Очистка static/plots/ ---
    # PNG-файлы старше этого порога удаляются при старте бэкенда.
    # 0 = не удалять PNG автоматически.
    # Через .env можно увеличить: PLOTS_MAX_AGE_HOURS=48
    PLOTS_MAX_AGE_HOURS: int = 24

    # Конфигурация: откуда читать .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()



