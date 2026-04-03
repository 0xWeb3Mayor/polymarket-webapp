import config


def compute_divergence(forecast_price: float, last_price: float) -> float:
    if last_price == 0:
        return 0.0
    return ((forecast_price - last_price) / last_price) * 100


def classify_signal(
    forecast_price: float,
    last_price: float,
    ci_80_low: float,
    ci_80_high: float
) -> str:
    div = compute_divergence(forecast_price, last_price)

    if div > config.DIVERGENCE_STRONG * 100 and ci_80_low > last_price:
        return "STRONG_BUY"
    if div > config.DIVERGENCE_SIGNAL * 100:
        return "BUY"
    if div < -config.DIVERGENCE_STRONG * 100 and ci_80_high < last_price:
        return "STRONG_SELL"
    if div < -config.DIVERGENCE_SIGNAL * 100:
        return "SELL"
    return "HOLD"


def rank_signals(results: list[dict]) -> list[dict]:
    """Sort by absolute divergence desc, exclude HOLD, return top N."""
    actionable = [r for r in results if r["signal"] != "HOLD"]
    sorted_results = sorted(actionable, key=lambda r: abs(r["divergence_pct"]), reverse=True)
    return sorted_results[:config.TOP_N_SIGNALS]
