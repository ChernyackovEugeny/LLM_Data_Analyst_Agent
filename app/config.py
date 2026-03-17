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

    # Конфигурация: откуда читать .env
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()



