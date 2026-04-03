import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, ".")
import main
from main import app

client = TestClient(app)

MOCK_MARKET = {
    "condition_id": "0xabc123",
    "question": "Will BTC hit $100k?",
    "token_id": "tok_yes_1",
    "close_time": 9999999999,
    "last_price": 0.34,
    "volume_24h": 45000.0,
    "liquidity": 128000.0,
    "fetched_at": 9999999999,
}

MOCK_HISTORY = [
    {"timestamp": 1700000000 + i * 3600, "price": 0.30 + i * 0.001, "volume": 0.0}
    for i in range(400)
]

MOCK_FORECAST = {
    "forecast_price": 0.51,
    "ci_80_low": 0.44,
    "ci_80_high": 0.58,
    "horizon_hours": 48,
}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_valid_condition_id():
    resp = client.post("/analyze", json={"url": "0xabc123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["condition_id"] == "0xabc123"
    assert data["redirect"] == "/m/0xabc123"


def test_analyze_invalid_url():
    resp = client.post("/analyze", json={"url": "not-a-polymarket-url"})
    assert resp.status_code == 400


def test_get_market_returns_forecast():
    with patch("main._get_market_from_db", return_value=MOCK_MARKET), \
         patch("main.fetch.fetch_price_history", return_value=MOCK_HISTORY), \
         patch("main.fc_module.run_forecast", return_value=MOCK_FORECAST), \
         patch("main.sqlite3.connect") as mock_conn:
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.execute = MagicMock()
        mock_conn.return_value.commit = MagicMock()
        mock_conn.return_value.close = MagicMock()
        resp = client.get("/market/0xabc123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["condition_id"] == "0xabc123"
    assert "forecast" in data
    assert data["forecast"]["signal"] in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL")
    assert "price_history" in data


def test_get_market_not_found():
    with patch("main._get_market_from_db", return_value=None), \
         patch("main._fetch_market_by_id", return_value=None):
        resp = client.get("/market/0xnotexist")
    assert resp.status_code == 404
