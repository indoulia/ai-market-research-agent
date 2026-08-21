from decimal import Decimal

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
    # EPIC-M1.149: which SignalProvider scripts/run_discovery_scan.py resolves.
    # "baseline" (app/baseline_signal.py) is the only value implemented today --
    # a real trained-model provider is out of this EPIC's scope, so an unknown
    # value is a hard, explicit operational failure rather than a silent
    # fallback to baseline.
    discovery_signal_provider: str = "baseline"
    # Same 5%/-3% target/stop used across every other discovery path in this
    # repo (M1.13 generation, M1.14 selection tests) -- overridable per
    # deployment without a code change.
    discovery_target_return: Decimal = Decimal("0.05")
    discovery_stop_return: Decimal = Decimal("-0.03")
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
