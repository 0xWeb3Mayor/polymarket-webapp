import json
import os
import re
from datetime import datetime, timezone


def generate_report(market: dict, forecast: dict) -> dict | None:
    """Generate a structured AI analysis report using Claude.

    Returns None if ANTHROPIC_API_KEY is not set or the call fails —
    the rest of the market response is still returned.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        return None

    close_dt = (
        datetime.fromtimestamp(market["close_time"], tz=timezone.utc).strftime("%b %d, %Y")
        if market.get("close_time")
        else "unknown"
    )
    market_pct = round(market["last_price"] * 100, 1)
    forecast_pct = round(forecast["forecast_price"] * 100, 1)
    outcome = market.get("outcome", "YES")

    prompt = f"""You are a sharp prediction market analyst. Analyze this Polymarket market.

Market question: "{market['question']}"
Outcome tracked: {outcome}
Closes: {close_dt}
Current Polymarket price: {market_pct}¢  (implies {market_pct}% probability YES)
24h volume: ${market['volume_24h']:,.0f}
Liquidity: ${market['liquidity']:,.0f}
TimesFM AI forecast ({forecast['horizon_hours']}h): {forecast_pct}¢  (divergence: {forecast['divergence_pct']:+.1f}%)
Signal: {forecast['signal']}

Respond with ONLY valid JSON, no markdown fences:
{{
  "what_it_asks": "One sentence: exactly what this market resolves on",
  "resolution_criteria": "Specific conditions for YES vs NO resolution",
  "key_factors": ["factor 1", "factor 2", "factor 3", "factor 4"],
  "probability_yes": 0.XX,
  "probability_no": 0.XX,
  "vs_market": "How your probability estimate compares to the {market_pct}% market price and what that implies",
  "mispricing": "Specific edge you see — direction, magnitude, why market may be wrong. Say NONE if fairly priced.",
  "action": "BUY YES or BUY NO or SELL YES or SELL NO or HOLD",
  "reasoning": "2-3 direct sentences explaining why. Be specific, not generic."
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Strip markdown code fences if present
        match = re.search(r"\{[\s\S]*\}", text)
        return json.loads(match.group() if match else text)
    except Exception as e:
        print(f"  [WARN] Report generation failed: {e}")
        return None
