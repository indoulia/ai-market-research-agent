from datetime import datetime, timezone

import pytest

from app.news_data.yahoo import YahooNewsClient, YahooNewsError


class _FakeTicker:
    def __init__(self, news):
        self.news = news


def test_fetch_news_parses_flat_legacy_schema(monkeypatch):
    items = [
        {
            "uuid": "abc-123",
            "title": "Company reports record quarterly earnings",
            "providerPublishTime": 1750000000,
        },
    ]
    monkeypatch.setattr("app.news_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(items))

    result = YahooNewsClient().fetch_news("reliance.ns")

    assert len(result) == 1
    assert result[0].external_id == "abc-123"
    assert result[0].headline == "Company reports record quarterly earnings"
    assert result[0].published_at == datetime.fromtimestamp(1750000000, tz=timezone.utc)


def test_fetch_news_parses_nested_content_schema(monkeypatch):
    items = [
        {
            "id": "xyz-789",
            "content": {"title": "Board approves special dividend", "pubDate": "2026-03-01T10:00:00Z"},
        },
    ]
    monkeypatch.setattr("app.news_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(items))

    result = YahooNewsClient().fetch_news("TCS.NS")

    assert len(result) == 1
    assert result[0].external_id == "xyz-789"
    assert result[0].headline == "Board approves special dividend"
    assert result[0].published_at == datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


def test_fetch_news_skips_incomplete_items(monkeypatch):
    items = [
        {"uuid": "no-title", "providerPublishTime": 1750000000},
        {"uuid": "no-time", "title": "missing timestamp"},
        {"title": "missing id", "providerPublishTime": 1750000000},
        {"uuid": "ok-1", "title": "usable item", "providerPublishTime": 1750000000},
    ]
    monkeypatch.setattr("app.news_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(items))

    result = YahooNewsClient().fetch_news("INFY.NS")

    assert [r.external_id for r in result] == ["ok-1"]


def test_fetch_news_returns_empty_tuple_when_no_news(monkeypatch):
    monkeypatch.setattr("app.news_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(None))

    assert YahooNewsClient().fetch_news("UNKNOWN.NS") == ()


def test_fetch_news_rejects_empty_symbol():
    with pytest.raises(ValueError, match="symbol"):
        YahooNewsClient().fetch_news("   ")


def test_fetch_news_wraps_provider_errors(monkeypatch):
    def _boom(symbol):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("app.news_data.yahoo.yf.Ticker", _boom)

    with pytest.raises(YahooNewsError):
        YahooNewsClient().fetch_news("RELIANCE.NS")
