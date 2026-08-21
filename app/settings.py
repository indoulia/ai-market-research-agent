from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    openai_api_key: str | None = None
    upstox_access_token: str | None = None
    upstox_instruments_url: str = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    # Selects which client scripts/ingest_market_history.py uses ("upstox" or
    # "yahoo") -- lets ops swap providers via env var alone, e.g. as a stopgap
    # while an Upstox account is pending, with no code/script change.
    market_data_provider: str = "upstox"
    # Comma-separated bare NSE symbols (e.g. "RELIANCE,TCS,INFY") used as the
    # universe when market_data_provider=yahoo, which has no instrument-master
    # endpoint of its own.
    yahoo_symbols: str = ""
    app_env: str = "development"
    log_level: str = "INFO"
    # EPIC-M1.145: comma-separated origins allowed to call /api/v1 from a
    # browser (e.g. the Flutter web build). "*" is safe as a default here
    # because this API authenticates via a Bearer token, never cookies --
    # no cross-site-cookie exposure to guard against -- but a deployment
    # can still lock this down via env var.
    cors_allowed_origins: str = "*"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
