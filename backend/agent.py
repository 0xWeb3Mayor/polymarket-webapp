"""
agent.py — PolyAgent autonomous scan loop

Auto-started on server boot. No manual intervention required.
Geopolitics markets are scanned first every pass.
Scan interval: AGENT_SCAN_INTERVAL (default 900s / 15 min).
"""

import asyncio
import random
import sqlite3
import time

import config
import fetch
import forecast as fc_module
import report as report_module
import signals as sig_module
import trader

_running = False


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(level: str, event: str, condition_id: str = None, detail: str = None):
    ts = int(time.time())
    icons = {"INFO": "·", "SIGNAL": "↑", "GATE": "⊘", "TRADE": "✓", "ERROR": "!"}
    parts = [f"[{icons.get(level,'·')}] {event}"]
    if condition_id:
        parts.append(condition_id[:14] + "...")
    if detail:
        parts.append(detail)
    print("  ".join(parts))
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO agent_logs (ts, level, event, condition_id, detail) VALUES (?,?,?,?,?)",
            (ts, level, event, condition_id, detail),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [WARN] log write failed: {e}")


# ── Geopolitics scoring ───────────────────────────────────────────────────────

def _geo_score(question: str) -> int:
    """Return count of geopolitics keyword hits. Higher = more relevant."""
    q = question.lower()
    return sum(1 for kw in config.GEOPOLITICS_KEYWORDS if kw in q)


def _prioritise(markets: list[dict]) -> list[dict]:
    """
    Sort markets so geopolitics come first.
    Within each tier, shuffle to avoid always hitting the same markets first.
    """
    geo   = [m for m in markets if _geo_score(m["question"]) > 0]
    other = [m for m in markets if _geo_score(m["question"]) == 0]

    # Sort geo by score desc (most keyword hits first)
    geo.sort(key=lambda m: _geo_score(m["question"]), reverse=True)
    random.shuffle(other)

    return geo + other


# ── Single scan pass ──────────────────────────────────────────────────────────

async def run_once() -> list[dict]:
    _log("INFO", "Scan started")
    executed = []

    try:
        markets = fetch.fetch_markets()
    except Exception as e:
        _log("ERROR", "fetch_markets failed", detail=str(e))
        return executed

    prioritised = _prioritise(markets)
    geo_count = sum(1 for m in prioritised if _geo_score(m["question"]) > 0)
    _log("INFO", "Markets loaded", detail=f"{len(prioritised)} total  {geo_count} geopolitics")

    strong_count = 0
    blocked_count = 0

    for market in prioritised:
        await asyncio.sleep(random.uniform(0.3, 1.2))  # gentle rate limit

        cid = market["condition_id"]
        is_geo = _geo_score(market["question"]) > 0

        try:
            history = fetch.fetch_price_history(cid, market["token_id"])
            if not history:
                continue

            price_series = [h["price"] for h in history]
            forecast_result = fc_module.run_forecast(cid, price_series)

            last_price = market["last_price"]
            divergence_pct = sig_module.compute_divergence(
                forecast_result["forecast_price"], last_price
            )
            signal = sig_module.classify_signal(
                forecast_result["forecast_price"],
                last_price,
                forecast_result["ci_80_low"],
                forecast_result["ci_80_high"],
            )

            if signal not in ("STRONG_BUY", "STRONG_SELL"):
                continue

            strong_count += 1
            geo_tag = " [GEO]" if is_geo else ""
            _log(
                "SIGNAL",
                f"{signal}{geo_tag}",
                condition_id=cid,
                detail=f"div={divergence_pct:+.1f}%  {last_price:.3f}→{forecast_result['forecast_price']:.3f}",
            )

            ai_report = report_module.generate_report(
                market={**market, "outcome": "YES"},
                forecast={
                    "forecast_price": forecast_result["forecast_price"],
                    "horizon_hours": config.FORECAST_HORIZON_HOURS,
                    "divergence_pct": divergence_pct,
                    "signal": signal,
                },
            )

            claude_action = (ai_report or {}).get("action", "—")
            _log("INFO", "Claude report", condition_id=cid, detail=f"action={claude_action}")

            result = {
                "condition_id": cid,
                "question": market["question"],
                "outcome": "YES",
                "last_price": last_price,
                "close_time": market["close_time"],
                "volume_24h": market["volume_24h"],
                "liquidity": market["liquidity"],
                "forecast": {
                    "forecast_price": forecast_result["forecast_price"],
                    "ci_80_low": forecast_result["ci_80_low"],
                    "ci_80_high": forecast_result["ci_80_high"],
                    "horizon_hours": config.FORECAST_HORIZON_HOURS,
                    "divergence_pct": divergence_pct,
                    "signal": signal,
                    "run_at": int(time.time()),
                    "token_id": market.get("token_id", ""),
                },
                "report": ai_report,
            }

            if trader.should_execute(result):
                trade = trader.execute_trade(result)
                executed.append(trade)
                _log(
                    "TRADE",
                    f"Executed  BUY {trade['side']}",
                    condition_id=cid,
                    detail=f"entry={trade['entry_price']:.3f}  size=${trade['size_usd']}  tx={trade['tx_hash'][:16]}...",
                )
            else:
                blocked_count += 1
                _log("GATE", f"Blocked — {_gate_reason(result)}", condition_id=cid)

        except Exception as e:
            _log("ERROR", "Processing failed", condition_id=cid, detail=str(e))
            continue

    _log(
        "INFO",
        "Scan complete",
        detail=f"strong={strong_count}  blocked={blocked_count}  executed={len(executed)}",
    )
    return executed


def _gate_reason(result: dict) -> str:
    signal = result.get("forecast", {}).get("signal", "")
    action = ((result.get("report") or {}).get("action") or "").upper().strip()
    liquidity = result.get("liquidity", 0)
    cid = result.get("condition_id", "")

    if signal not in ("STRONG_BUY", "STRONG_SELL"):
        return f"signal too weak ({signal})"
    if signal == "STRONG_BUY" and action in ("SELL YES", "BUY NO", "SELL NO"):
        return f"Claude opposes (action={action})"
    if signal == "STRONG_SELL" and action in ("BUY YES", "SELL NO"):
        return f"Claude opposes (action={action})"
    if liquidity < config.AGENT_MIN_LIQUIDITY:
        return f"low liquidity (${liquidity:,.0f})"

    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT id FROM trades WHERE condition_id=? AND closed_at IS NULL", (cid,)
    ).fetchone()
    conn.close()
    if row:
        return "position already open"
    return "unknown"


# ── Autonomous loop ───────────────────────────────────────────────────────────

async def run_agent():
    global _running
    _running = True
    _log("INFO", "Agent started", detail=f"interval={config.AGENT_SCAN_INTERVAL}s  live={config.OWS_LIVE}  geo-priority=on")

    while _running:
        await run_once()
        jitter = random.uniform(-0.05, 0.05) * config.AGENT_SCAN_INTERVAL
        sleep_time = config.AGENT_SCAN_INTERVAL + jitter
        _log("INFO", f"Next scan in {int(sleep_time)}s")
        await asyncio.sleep(sleep_time)

    _log("INFO", "Agent stopped")


def stop_agent():
    global _running
    _running = False


if __name__ == "__main__":
    asyncio.run(run_agent())
