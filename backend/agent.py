"""
agent.py — PolyAgent autonomous scan loop

Runs on a cron: fetch markets → forecast → gate → execute.
Launch directly:  python agent.py
Or via the /agent/* API endpoints in main.py.
"""

import asyncio
import random
import time

import config
import fetch
import forecast as fc_module
import report as report_module
import signals as sig_module
import trader

_running = False


async def run_once() -> list[dict]:
    """
    Single pass: scan all markets, fire on STRONG signals that pass the gate.
    Returns list of trade records executed this pass.
    """
    print(f"[AGENT] Scan started at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    executed = []

    try:
        markets = fetch.fetch_markets()
    except Exception as e:
        print(f"[AGENT] fetch_markets failed: {e}")
        return executed

    print(f"[AGENT] {len(markets)} markets loaded")

    for market in markets:
        # Jitter between markets to avoid hammering APIs
        await asyncio.sleep(random.uniform(0.5, 2.0))

        try:
            history = fetch.fetch_price_history(
                market["condition_id"], market["token_id"]
            )
            if not history:
                continue

            price_series = [h["price"] for h in history]
            forecast_result = fc_module.run_forecast(
                market["condition_id"], price_series
            )

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

            # Quick pre-filter — only call Claude for strong signals
            if signal not in ("STRONG_BUY", "STRONG_SELL"):
                continue

            print(f"[AGENT] Strong signal {signal} on {market['condition_id'][:12]}... — getting Claude report")

            ai_report = report_module.generate_report(
                market={**market, "outcome": "YES"},
                forecast={
                    "forecast_price": forecast_result["forecast_price"],
                    "horizon_hours": config.FORECAST_HORIZON_HOURS,
                    "divergence_pct": divergence_pct,
                    "signal": signal,
                },
            )

            result = {
                "condition_id": market["condition_id"],
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
                print(f"[AGENT] Trade executed: {trade['signal']} {trade['side']} tx={trade['tx_hash'][:18]}...")
            else:
                print(f"[AGENT] Gate blocked trade for {market['condition_id'][:12]}...")

        except Exception as e:
            print(f"[AGENT] Error processing {market.get('condition_id','?')[:12]}...: {e}")
            continue

    print(f"[AGENT] Scan complete — {len(executed)} trades executed")
    return executed


async def run_agent():
    """
    Infinite loop: run_once every AGENT_SCAN_INTERVAL seconds with jitter.
    """
    global _running
    _running = True
    print(f"[AGENT] Starting autonomous loop (interval={config.AGENT_SCAN_INTERVAL}s, live={config.OWS_LIVE})")

    while _running:
        await run_once()
        # Add ±5% jitter to avoid fixed-interval request patterns
        jitter = random.uniform(-0.05, 0.05) * config.AGENT_SCAN_INTERVAL
        sleep_time = config.AGENT_SCAN_INTERVAL + jitter
        print(f"[AGENT] Next scan in {int(sleep_time)}s")
        await asyncio.sleep(sleep_time)


def stop_agent():
    global _running
    _running = False
    print("[AGENT] Stop signal received")


if __name__ == "__main__":
    asyncio.run(run_agent())
