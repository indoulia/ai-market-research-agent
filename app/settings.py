from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    openai_api_key: str | None = None
    upstox_access_token: str | None = None
    upstox_instruments_url: str = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    app_env: str = "development"
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
