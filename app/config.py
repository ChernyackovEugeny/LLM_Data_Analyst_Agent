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

    # --- Python Sandbox (python_tool.py) ---
    # True = запускать код в Docker-контейнере (production, docker-compose).
    # False = subprocess fallback (локальная разработка без Docker Compose).
    USE_SANDBOX: bool = False

    # Имя Docker volume для графиков: {COMPOSE_PROJECT_NAME}_plots_data.
    # Используется как общая шина между backend и sandbox-контейнером (DooD).
    PLOTS_VOLUME_NAME: str = "llm_data_analyst_agent_plots_data"

    # Имя Docker-образа для sandbox-контейнеров.
    SANDBOX_IMAGE_NAME: str = "analyst-sandbox:latest"

    # Конфигурация: откуда читать .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()



