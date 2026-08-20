from datetime import date

import httpx
import pytest

from app.market_data import UpstoxClient, UpstoxError


def test_fetch_daily_candles_parses_success(monkeypatch):
    client = UpstoxClient("token", "https://example.test/NSE.json.gz")
    captured = {}

    def fake_get(url):
        captured["url"] = url
        return httpx.Response(
            200,
            json={"status": "success", "data": {"candles": [["2026-08-19T00:00:00+05:30", 10, 11, 9, 10.5, 1000, 0]]}},
        )

    monkeypatch.setattr(client.client, "get", fake_get)
    candles = client.fetch_daily_candles("NSE_EQ|INE123456789", date(2026, 8, 1), date(2026, 8, 19))
    assert len(candles) == 1
    assert "/days/1/2026-08-19/2026-08-01" in captured["url"]
    client.close()


def test_fetch_daily_candles_rejects_reverse_range():
    client = UpstoxClient("token", "https://example.test/NSE.json.gz")
    with pytest.raises(ValueError):
        client.fetch_daily_candles("NSE_EQ|INE123456789", date(2026, 8, 20), date(2026, 8, 19))
    client.close()


def test_fetch_daily_candles_maps_unauthorized(monkeypatch):
    client = UpstoxClient("token", "https://example.test/NSE.json.gz")
    monkeypatch.setattr(client.client, "get", lambda _: httpx.Response(401))
    with pytest.raises(UpstoxError, match="expired or unauthorized"):
        client.fetch_daily_candles("NSE_EQ|INE123456789", date(2026, 8, 1), date(2026, 8, 19))
    client.close()
