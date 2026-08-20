from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    openai_api_key: str | None = None
    app_env: str = "development"
    log_level: str = "INFO"
    market_data_provider: str = "upstox"
    upstox_access_token: str | None = None
    upstox_base_url: str = "https://api.upstox.com"
    upstox_request_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
