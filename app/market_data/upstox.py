from __future__ import annotations

from datetime import date
import gzip
import json
from typing import Any
from urllib.parse import quote

import httpx


class UpstoxError(RuntimeError):
    pass


class UpstoxClient:
    """Small HTTP client for the Upstox instrument master and Historical Candle V3 API."""

    source = "upstox-v3"
    capability = "MARKET_DATA"
    version = "1"

    def __init__(self, access_token: str, instruments_url: str, timeout: float = 30.0) -> None:
        if not access_token:
            raise ValueError("UPSTOX_ACCESS_TOKEN is required")
        self.instruments_url = instruments_url
        self.client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "UpstoxClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_nse_instruments(self) -> list[dict[str, Any]]:
        response = self.client.get(self.instruments_url)
        response.raise_for_status()
        payload = gzip.decompress(response.content) if self.instruments_url.endswith(".gz") else response.content
        data = json.loads(payload)
        if not isinstance(data, list):
            raise UpstoxError("Upstox instrument master response is not a JSON array")
        return [
            item for item in data
            if item.get("segment") == "NSE_EQ"
            and item.get("instrument_type") in {"EQ", "BE"}
            and item.get("instrument_key")
            and item.get("trading_symbol")
        ]

    def fetch_daily_candles(self, instrument_key: str, from_date: date, to_date: date) -> list[list[Any]]:
        if from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        encoded_key = quote(instrument_key, safe="")
        url = (
            f"https://api.upstox.com/v3/historical-candle/{encoded_key}/days/1/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )
        response = self.client.get(url)
        if response.status_code == 401:
            raise UpstoxError("Upstox access token is expired or unauthorized")
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success":
            raise UpstoxError(f"Upstox historical candle request failed: {body}")
        return body.get("data", {}).get("candles", [])
