import asyncio
import sqlite3
import time
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _require_secret(x_agent_secret: str | None = Header(default=None)):
    """Dependency — blocks request if AGENT_SECRET is set and header doesn't match."""
    if config.AGENT_SECRET and x_agent_secret != config.AGENT_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

import config
import fetch
import forecast as fc_module
import report as report_module
import signals as sig_module
import trader
from parser import extract_condition_id

app = FastAPI(title="Polymarket Scanner API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    fetch.init_db()
    # Setup OWS wallet vault + spending policy
    trader.setup_ows_wallet()
    # Auto-start agent — no manual intervention required
    global _agent_task
    import agent as agent_module
    _agent_task = asyncio.create_task(agent_module.run_agent())
    print(f"[STARTUP] PolyAgent auto-started (live={config.OWS_LIVE}, interval={config.AGENT_SCAN_INTERVAL}s)")


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


# ── /trades endpoints ──────────────────────────────────────────────────────────

_TRADE_COLS = [
    "id", "condition_id", "question", "side", "entry_price", "size_usd",
    "signal", "tx_hash", "executed_at", "closed_at", "exit_price",
    "ows_wallet", "paper_trade",
]


def _enrich_trade(row: tuple) -> dict:
    """Add current_price and pnl_pct to a raw trades row."""
    t = dict(zip(_TRADE_COLS, row))
    try:
        if t["closed_at"] is None:
            pnl = trader.get_pnl(t["condition_id"])
            t["current_price"] = (pnl or {}).get("current_price")
            t["pnl_pct"]       = (pnl or {}).get("pnl_pct")
        else:
            t["current_price"] = t.get("exit_price")
            entry, exit_ = t.get("entry_price"), t.get("exit_price")
            if entry and exit_:
                t["pnl_pct"] = round(
                    ((exit_ - entry) / entry * 100) if t["side"] == "YES"
                    else ((entry - exit_) / entry * 100),
                    2,
                )
            else:
                t["pnl_pct"] = None
    except Exception:
        t["current_price"] = None
        t["pnl_pct"]       = None
    t["polygonscan_url"] = (
        f"https://polygonscan.com/tx/{t['tx_hash']}" if t.get("tx_hash") else None
    )
    return t


@app.get("/trades")
def get_trades():
    """Last 50 trades. P&L enrichment is best-effort per trade."""
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute(
        f"SELECT {', '.join(_TRADE_COLS)} FROM trades ORDER BY executed_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        t = dict(zip(_TRADE_COLS, row))
        t["current_price"] = None
        t["pnl_pct"] = None
        t["polygonscan_url"] = (
            f"https://polygonscan.com/tx/{t['tx_hash']}" if t.get("tx_hash") else None
        )
        result.append(t)
    return result


@app.get("/trades/{condition_id}")
def get_trade(condition_id: str):
    """Full detail for a single position including forecast report."""
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        f"SELECT {', '.join(_TRADE_COLS)} FROM trades WHERE condition_id = ? ORDER BY executed_at DESC LIMIT 1",
        (condition_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No trade found for this market")
    trade = _enrich_trade(row)

    # Attach last forecast report if available
    try:
        market = _get_market_from_db(condition_id) or _fetch_market_by_id(condition_id)
        if market:
            history = fetch.fetch_price_history(condition_id, market["token_id"])
            if history:
                price_series = [h["price"] for h in history]
                fc = fc_module.run_forecast(condition_id, price_series)
                div = sig_module.compute_divergence(fc["forecast_price"], market["last_price"])
                sig = sig_module.classify_signal(
                    fc["forecast_price"], market["last_price"],
                    fc["ci_80_low"], fc["ci_80_high"]
                )
                report = report_module.generate_report(
                    market={**market, "outcome": "YES"},
                    forecast={"forecast_price": fc["forecast_price"],
                              "horizon_hours": 48, "divergence_pct": div, "signal": sig},
                )
                trade["report"] = report
    except Exception:
        trade["report"] = None

    return trade


@app.post("/trades/{condition_id}/close")
def close_trade(condition_id: str, x_agent_secret: str | None = Header(default=None)):
    """Manually close an open position via OWS."""
    _require_secret(x_agent_secret)
    result = trader.close_position(condition_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No open position for this market")
    return result


# ── Agent control endpoints ────────────────────────────────────────────────────

_agent_task: Optional[asyncio.Task] = None


@app.post("/agent/start")
async def start_agent(x_agent_secret: str | None = Header(default=None)):
    """Start the autonomous trading loop."""
    _require_secret(x_agent_secret)
    global _agent_task
    try:
        import agent as agent_module
        if _agent_task and not _agent_task.done():
            return {"status": "already_running", "live": config.OWS_LIVE}
        _agent_task = asyncio.create_task(agent_module.run_agent())
        return {"status": "started", "live": config.OWS_LIVE}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/agent/stop")
async def stop_agent(x_agent_secret: str | None = Header(default=None)):
    """Stop the autonomous trading loop."""
    _require_secret(x_agent_secret)
    global _agent_task
    try:
        import agent as agent_module
        agent_module.stop_agent()
        if _agent_task:
            _agent_task.cancel()
    except Exception:
        pass
    return {"status": "stopped"}


@app.get("/agent/status")
async def agent_status():
    return {
        "running": _agent_task is not None and not _agent_task.done(),
        "live": trader.is_live(),
        "wallet": config.OWS_WALLET_NAME,
        "max_trade_usd": config.MAX_TRADE_USD,
        "daily_limit_usd": config.DAILY_LIMIT_USD,
    }


class ModeRequest(BaseModel):
    live: bool

@app.post("/agent/mode")
async def set_agent_mode(req: ModeRequest, x_agent_secret: str | None = Header(default=None)):
    """Toggle between live and paper trading without redeploying."""
    _require_secret(x_agent_secret)
    if req.live and not config.PRIVATE_KEY:
        return {"error": "PRIVATE_KEY not set — cannot enable live mode"}
    trader.set_live_mode(req.live)
    return {"live": req.live, "status": "live trading enabled" if req.live else "paper mode enabled"}


@app.post("/agent/run-once")
async def run_agent_once():
    """Trigger a single scan pass (useful for demo / testing)."""
    import agent as agent_module
    executed = await agent_module.run_once()
    return {"trades_executed": len(executed), "trades": executed}


@app.get("/wallet/balance")
def wallet_balance():
    """Return USDC balance on Polygon for the OWS wallet."""
    return fetch.get_wallet_balance()


@app.post("/demo/seed")
def demo_seed():
    """Insert realistic paper trades for demo/hackathon purposes."""
    now = int(time.time())
    demo_trades = [
        (
            "0x6c013e0e5f2a1b3d4c5e6f7a8b9c0d1e2f3a4b5c",
            "Will Russia and Ukraine reach a ceasefire agreement by June 2026?",
            "YES", 0.060, 50.0, "STRONG_BUY", "0x4e017454ac77291a2b3c4d5e6f7a8b9c0d1e2f3a",
            now - 3600, None, None, "polyagent-treasury", 1,
        ),
        (
            "0x0b54eb55f3c2d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
            "Will Taiwan hold presidential elections without military incident in 2026?",
            "YES", 0.035, 50.0, "STRONG_BUY", "0x1230767c8799af2b3c4d5e6f7a8b9c0d1e2f3a4b",
            now - 7200, None, None, "polyagent-treasury", 1,
        ),
        (
            "0x49e0fd35a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9",
            "Will Iran nuclear talks result in a deal before end of 2026?",
            "YES", 0.199, 50.0, "STRONG_BUY", "0x5a4dbe899a921e3c4d5e6f7a8b9c0d1e2f3a4b5c",
            now - 1800, None, None, "polyagent-treasury", 1,
        ),
        (
            "0x16b7d06d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b",
            "Will there be a military conflict between NATO and Russia in 2026?",
            "NO", 0.921, 50.0, "STRONG_SELL", "0x5a4dbe899a921ef3a4b5c6d7e8f9a0b1c2d3e4f5",
            now - 5400, None, None, "polyagent-treasury", 1,
        ),
    ]
    conn = sqlite3.connect(config.DB_PATH)
    inserted = 0
    for t in demo_trades:
        existing = conn.execute(
            "SELECT id FROM trades WHERE condition_id = ? AND closed_at IS NULL", (t[0],)
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO trades
                   (condition_id, question, side, entry_price, size_usd, signal,
                    tx_hash, executed_at, closed_at, exit_price, ows_wallet, paper_trade)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                t,
            )
            inserted += 1
    conn.commit()
    conn.close()
    return {"inserted": inserted, "message": f"{inserted} demo trades added"}


@app.get("/agent/logs")
def get_agent_logs(limit: int = 100):
    """Return the most recent agent activity log entries."""
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute(
        """SELECT id, ts, level, event, condition_id, detail
           FROM agent_logs ORDER BY ts DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0], "ts": r[1], "level": r[2],
            "event": r[3], "condition_id": r[4], "detail": r[5],
        }
        for r in rows
    ]
