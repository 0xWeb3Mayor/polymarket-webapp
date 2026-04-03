import sqlite3
import time

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import fetch
import forecast as fc_module
import report as report_module
import signals as sig_module
from parser import extract_condition_id

app = FastAPI(title="Polymarket Scanner API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    fetch.init_db()


# ── helpers ──────────────────────────────────────────────────────────────────

_MARKET_COLS = ["condition_id", "question", "token_id", "close_time",
                "last_price", "volume_24h", "liquidity", "fetched_at"]


def _get_market_from_db(condition_id: str) -> dict | None:
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT * FROM markets WHERE condition_id = ?", (condition_id,)
    ).fetchone()
    conn.close()
    return dict(zip(_MARKET_COLS, row)) if row else None


def _best_token(tokens: list) -> dict | None:
    """Return YES token for binary markets; highest-priced token for multi-outcome."""
    for t in tokens:
        if t.get("outcome", "").lower() == "yes":
            return t
    if tokens:
        return max(tokens, key=lambda t: float(t.get("price", 0) or 0))
    return None


def _fetch_market_by_id(condition_id: str) -> dict | None:
    """Fetch a single market directly from Polymarket API by condition_id."""
    try:
        resp = requests.get(
            f"{config.API_BASE}/markets/{condition_id}", timeout=15
        )
        if not resp.ok:
            return None
        data = resp.json()
        token = _best_token(data.get("tokens", []))
        if not token:
            return None
        token_id = token["token_id"]
        # Use token-level price when available (more accurate for multi-outcome)
        last_price = float(token.get("price") or data.get("last_trade_price") or 0)
        return {
            "condition_id": condition_id,
            "question": data.get("question", ""),
            "outcome": token.get("outcome", "YES"),
            "token_id": token_id,
            "close_time": int(data.get("close_time") or 0),
            "last_price": last_price,
            "volume_24h": float(data.get("volume24hr") or 0),
            "liquidity": float(data.get("liquidity") or 0),
            "fetched_at": int(time.time()),
        }
    except requests.RequestException:
        return None


def _build_forecast_response(market: dict, horizon: int) -> dict:
    """Fetch history, run forecast, return full response dict."""
    history = fetch.fetch_price_history(market["condition_id"], market["token_id"])
    if not history:
        raise HTTPException(
            status_code=422,
            detail="Not enough price history for this market — it may be too new or have low trading activity (need 24+ hours of data)"
        )

    price_series = [h["price"] for h in history]
    forecast_result = fc_module.run_forecast(market["condition_id"], price_series)

    last_price = market["last_price"]
    divergence_pct = sig_module.compute_divergence(
        forecast_result["forecast_price"], last_price
    )
    signal = sig_module.classify_signal(
        forecast_result["forecast_price"], last_price,
        forecast_result["ci_80_low"], forecast_result["ci_80_high"]
    )

    run_at = int(time.time())

    # Persist forecast to DB
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)",
        (market["condition_id"], run_at, horizon,
         forecast_result["forecast_price"], forecast_result["ci_80_low"],
         forecast_result["ci_80_high"], divergence_pct, signal)
    )
    conn.commit()
    conn.close()

    ai_report = report_module.generate_report(
        market={**market, "outcome": market.get("outcome", "YES")},
        forecast={
            "forecast_price": forecast_result["forecast_price"],
            "horizon_hours": horizon,
            "divergence_pct": divergence_pct,
            "signal": signal,
        },
    )

    return {
        "condition_id": market["condition_id"],
        "question": market["question"],
        "outcome": market.get("outcome", "YES"),
        "last_price": last_price,
        "close_time": market["close_time"],
        "volume_24h": market["volume_24h"],
        "liquidity": market["liquidity"],
        "forecast": {
            "forecast_price": forecast_result["forecast_price"],
            "ci_80_low": forecast_result["ci_80_low"],
            "ci_80_high": forecast_result["ci_80_high"],
            "horizon_hours": horizon,
            "divergence_pct": divergence_pct,
            "signal": signal,
            "run_at": run_at,
        },
        "price_history": [
            {"timestamp": h["timestamp"], "price": h["price"]}
            for h in history[-336:]  # last 14 days for chart
        ],
        "report": ai_report,
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    url: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    condition_id = extract_condition_id(req.url)
    if not condition_id:
        raise HTTPException(
            status_code=400,
            detail="Could not parse a Polymarket condition_id from that URL"
        )
    return {"condition_id": condition_id, "redirect": f"/m/{condition_id}"}


@app.get("/market/{condition_id}")
def get_market(condition_id: str, horizon: int = 48):
    market = _get_market_from_db(condition_id)
    if not market:
        market = _fetch_market_by_id(condition_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return _build_forecast_response(market, horizon)


@app.get("/market/{condition_id}/refresh")
def refresh_market(condition_id: str, horizon: int = 48):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "DELETE FROM price_history WHERE condition_id = ?", (condition_id,)
    )
    conn.commit()
    conn.close()
    return get_market(condition_id, horizon)


@app.get("/recent")
def get_recent():
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute("""
        SELECT f.condition_id, m.question, f.signal, f.divergence_pct, f.run_at
        FROM forecasts f
        JOIN markets m ON f.condition_id = m.condition_id
        ORDER BY f.run_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    return [
        {"condition_id": r[0], "question": r[1],
         "signal": r[2], "divergence_pct": r[3], "run_at": r[4]}
        for r in rows
    ]
