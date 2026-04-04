"""
agent.py — PolyAgent autonomous scan loop

Runs on a cron: fetch markets → forecast → gate → execute.
Every decision is logged to the agent_logs DB table.
Launch directly:  python agent.py
Or via the /agent/* API endpoints in main.py.
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
    """Write a structured log entry to agent_logs and stdout."""
    ts = int(time.time())
    prefix = {"INFO": "[·]", "SIGNAL": "[↑]", "GATE": "[⊘]", "TRADE": "[✓]", "ERROR": "[!]"}.get(level, "[·]")
    parts = [f"{prefix} {event}"]
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
        print(f"  [WARN] Failed to write agent log: {e}")


# ── Single scan pass ──────────────────────────────────────────────────────────

async def run_once() -> list[dict]:
    """
    Single pass: scan all markets, fire on STRONG signals that pass the gate.
    Returns list of trade records executed this pass.
    """
    _log("INFO", "Scan started")
    executed = []

    try:
        markets = fetch.fetch_markets()
    except Exception as e:
        _log("ERROR", "fetch_markets failed", detail=str(e))
        return executed

    _log("INFO", f"Markets loaded", detail=f"{len(markets)} markets")

    strong_count = 0
    blocked_count = 0

    for market in markets:
        await asyncio.sleep(random.uniform(0.5, 2.0))

        cid = market["condition_id"]

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
            _log(
                "SIGNAL",
                f"{signal}",
                condition_id=cid,
                detail=f"divergence={divergence_pct:+.1f}%  price={last_price:.3f}→{forecast_result['forecast_price']:.3f}",
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
            _log(
                "INFO",
                "Claude report",
                condition_id=cid,
                detail=f"action={claude_action}",
            )

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
                # Explain why the gate blocked
                reason = _gate_reason(result)
                _log("GATE", f"Blocked — {reason}", condition_id=cid)

        except Exception as e:
            _log("ERROR", f"Processing failed", condition_id=cid, detail=str(e))
            continue

    _log(
        "INFO",
        "Scan complete",
        detail=f"strong={strong_count}  blocked={blocked_count}  executed={len(executed)}",
    )
    return executed


def _gate_reason(result: dict) -> str:
    """Return a human-readable explanation of why the gate blocked a trade."""
    signal = result.get("forecast", {}).get("signal", "")
    report = result.get("report") or {}
    action = (report.get("action") or "").upper()
    liquidity = result.get("liquidity", 0)
    cid = result.get("condition_id", "")

    if signal not in ("STRONG_BUY", "STRONG_SELL"):
        return f"signal too weak ({signal})"
    if signal == "STRONG_BUY" and "BUY YES" not in action:
        return f"Claude disagrees (action={action})"
    if signal == "STRONG_SELL" and "BUY NO" not in action:
        return f"Claude disagrees (action={action})"
    if liquidity < config.AGENT_MIN_LIQUIDITY:
        return f"liquidity too low (${liquidity:,.0f} < ${config.AGENT_MIN_LIQUIDITY:,})"

    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT id FROM trades WHERE condition_id = ? AND closed_at IS NULL", (cid,)
    ).fetchone()
    conn.close()
    if row:
        return "position already open"

    return "unknown"


# ── Autonomous loop ───────────────────────────────────────────────────────────

async def run_agent():
    global _running
    _running = True
    _log("INFO", f"Agent started", detail=f"interval={config.AGENT_SCAN_INTERVAL}s  live={config.OWS_LIVE}")

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
