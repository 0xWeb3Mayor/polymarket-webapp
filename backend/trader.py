"""
trader.py — PolyAgent execution layer

Live mode: set OWS_LIVE=true + PRIVATE_KEY in Railway env vars.
Paper mode (default): full execution loop with mock tx hash, no real USDC moved.
"""

import hashlib
import sqlite3
import time
import os
import requests

import config

# ── CLOB client (optional — graceful fallback) ────────────────────────────────

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
    _CLOB_AVAILABLE = True
except ImportError:
    _CLOB_AVAILABLE = False

# OWS is not a real PyPI package — live mode uses PRIVATE_KEY + py-clob-client directly
_OWS_AVAILABLE = False

# ── Gate logic ────────────────────────────────────────────────────────────────

def should_execute(result: dict) -> bool:
    """
    Return True only when ALL gate conditions are met:
    1. Signal is STRONG_BUY or STRONG_SELL
    2. Claude does NOT explicitly say the opposite direction
       (HOLD = uncertainty, allowed through. Only hard disagree blocks.)
    3. Market liquidity > $10,000
    4. No open position already exists for this condition_id
    """
    signal = result.get("forecast", {}).get("signal", "HOLD")
    if signal not in ("STRONG_BUY", "STRONG_SELL"):
        return False

    # Claude veto — only block on explicit opposite direction, not HOLD
    report = result.get("report") or {}
    action = (report.get("action") or "HOLD").upper().strip()

    if signal == "STRONG_BUY":
        # Block only if Claude explicitly says to go the other way
        if action in ("SELL YES", "BUY NO", "SELL NO"):
            return False
    if signal == "STRONG_SELL":
        # Block only if Claude explicitly says to go the other way
        if action in ("BUY YES", "SELL NO"):
            return False

    # Liquidity floor — need book depth to fill without slippage
    if result.get("liquidity", 0) < config.AGENT_MIN_LIQUIDITY:
        return False

    # No duplicate open position
    condition_id = result.get("condition_id", "")
    if condition_id and _has_open_position(condition_id):
        return False

    return True


def _has_open_position(condition_id: str) -> bool:
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT id FROM trades WHERE condition_id = ? AND closed_at IS NULL",
        (condition_id,),
    ).fetchone()
    conn.close()
    return row is not None


# ── CLOB order construction ───────────────────────────────────────────────────

def build_clob_order(market: dict, side: str, size_usd: float) -> dict:
    """
    Build a Polymarket CLOB limit order dict.

    side: 'YES' (buy YES token) or 'NO' (buy NO token / sell YES)
    size_usd: position size in USD

    With py-clob-client available, returns a signed OrderArgs-compatible dict.
    Without it, returns a structured order dict for paper/simulation mode.
    """
    token_id = market.get("token_id", "")
    price = float(market.get("last_price", 0.5))

    if side == "NO":
        # Buying NO ≈ selling YES; price for NO = 1 - price for YES
        price = round(1.0 - price, 4)

    # Size in shares (USD / price per share)
    size_shares = round(size_usd / price, 2) if price > 0 else 0

    order = {
        "token_id": token_id,
        "side": "BUY",        # always BUY the token we want (YES or NO)
        "price": price,
        "size": size_shares,
        "size_usd": size_usd,
        "order_type": "LIMIT",
        "chain": "eip155:137",
    }

    if _CLOB_AVAILABLE and config.OWS_LIVE:
        try:
            creds = ApiCreds(
                api_key=config.CLOB_API_KEY,
                api_secret=config.CLOB_API_SECRET,
                api_passphrase=config.CLOB_API_PASSPHRASE,
            )
            client = ClobClient(
                host="https://clob.polymarket.com",
                chain_id=137,
                creds=creds,
            )
            signed = client.create_order(
                token_id=token_id,
                price=price,
                size=size_shares,
                side="BUY",
            )
            order["_signed_clob_order"] = signed
        except Exception as e:
            print(f"  [WARN] CLOB order construction failed: {e}. Falling back to paper order.")

    return order


# ── OWS signing ───────────────────────────────────────────────────────────────

def _sign_with_ows(order: dict) -> str:
    """
    Submit order via Polymarket CLOB using private key (live mode).
    Falls back to a deterministic mock hash in paper trading mode.
    """
    if config.OWS_LIVE and config.PRIVATE_KEY and _CLOB_AVAILABLE:
        pk = config.PRIVATE_KEY if config.PRIVATE_KEY.startswith("0x") else "0x" + config.PRIVATE_KEY
        try:
            clob = ClobClient(
                host="https://clob.polymarket.com",
                key=pk,
                chain_id=137,
                signature_type=0,  # EOA
            )
            # Derive CLOB API credentials from private key if not set
            if config.CLOB_API_KEY:
                clob.set_api_creds(ApiCreds(
                    api_key=config.CLOB_API_KEY,
                    api_secret=config.CLOB_API_SECRET,
                    api_passphrase=config.CLOB_API_PASSPHRASE,
                ))
            else:
                api_creds = clob.create_or_derive_api_creds()
                clob.set_api_creds(api_creds)

            order_args = OrderArgs(
                token_id=order["token_id"],
                price=order["price"],
                size=order["size"],
                side="BUY",
            )
            signed = clob.create_order(order_args)
            resp = clob.post_order(signed, OrderType.GTC)
            tx = (resp or {}).get("transactionHash") or (resp or {}).get("orderID")
            return tx or _mock_hash(order)
        except Exception as e:
            print(f"  [WARN] Live CLOB order failed: {e} — falling back to paper hash")
            return _mock_hash(order)

    # Paper trading — deterministic mock hash
    return _mock_hash(order)


def _mock_hash(order: dict) -> str:
    seed = f"{order.get('token_id','')}{order.get('price',0)}{time.time()}"
    return "0x" + hashlib.sha256(seed.encode()).hexdigest()


# ── Trade execution ───────────────────────────────────────────────────────────

def execute_trade(result: dict) -> dict:
    """
    Full execution path:
    1. Determine side from signal
    2. Build CLOB order
    3. Sign via OWS (paper or live)
    4. Persist trade record to DB
    5. Return trade record
    """
    signal = result["forecast"]["signal"]
    side = "YES" if signal == "STRONG_BUY" else "NO"
    market = {
        "condition_id": result["condition_id"],
        "question": result.get("question", ""),
        "token_id": result.get("forecast", {}).get("token_id", ""),
        "last_price": result["last_price"],
        "liquidity": result.get("liquidity", 0),
    }

    # Derive YES token_id from the result if available (fetch module stores it)
    if not market["token_id"]:
        conn = sqlite3.connect(config.DB_PATH)
        row = conn.execute(
            "SELECT token_id FROM markets WHERE condition_id = ?",
            (result["condition_id"],),
        ).fetchone()
        conn.close()
        if row:
            market["token_id"] = row[0]

    size_usd = config.MAX_TRADE_USD
    order = build_clob_order(market, side, size_usd)
    entry_price = order["price"]

    is_paper = not (config.OWS_LIVE and bool(config.PRIVATE_KEY) and _CLOB_AVAILABLE)
    tx_hash = _sign_with_ows(order)

    executed_at = int(time.time())

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """INSERT INTO trades
           (condition_id, question, side, entry_price, size_usd, signal,
            tx_hash, executed_at, ows_wallet, paper_trade)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            result["condition_id"],
            result.get("question", ""),
            side,
            entry_price,
            size_usd,
            signal,
            tx_hash,
            executed_at,
            config.OWS_WALLET_NAME,
            1 if is_paper else 0,
        ),
    )
    trade_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    mode = "PAPER" if is_paper else "LIVE"
    print(
        f"  [TRADE:{mode}] {signal} {side} {result['condition_id'][:12]}... "
        f"entry={entry_price:.3f} size=${size_usd} tx={tx_hash[:18]}..."
    )

    return {
        "id": trade_id,
        "condition_id": result["condition_id"],
        "question": result.get("question", ""),
        "side": side,
        "entry_price": entry_price,
        "size_usd": size_usd,
        "signal": signal,
        "tx_hash": tx_hash,
        "executed_at": executed_at,
        "ows_wallet": config.OWS_WALLET_NAME,
        "paper_trade": is_paper,
    }


# ── Position queries ──────────────────────────────────────────────────────────

def get_open_positions() -> list[dict]:
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute(
        """SELECT id, condition_id, question, side, entry_price, size_usd,
                  signal, tx_hash, executed_at, ows_wallet, paper_trade
           FROM trades WHERE closed_at IS NULL
           ORDER BY executed_at DESC"""
    ).fetchall()
    conn.close()
    cols = ["id", "condition_id", "question", "side", "entry_price", "size_usd",
            "signal", "tx_hash", "executed_at", "ows_wallet", "paper_trade"]
    return [dict(zip(cols, r)) for r in rows]


def get_pnl(condition_id: str) -> dict | None:
    """Compare entry price to current market price for a position."""
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        """SELECT id, side, entry_price, size_usd, signal, tx_hash, executed_at,
                  closed_at, exit_price, paper_trade
           FROM trades WHERE condition_id = ? AND closed_at IS NULL
           ORDER BY executed_at DESC LIMIT 1""",
        (condition_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None

    trade = dict(zip(
        ["id", "side", "entry_price", "size_usd", "signal", "tx_hash",
         "executed_at", "closed_at", "exit_price", "paper_trade"],
        row,
    ))

    # Fetch current price from Polymarket API
    current_price = _fetch_current_price(condition_id)
    if current_price is None:
        return {**trade, "current_price": None, "pnl_pct": None}

    entry = trade["entry_price"]
    if trade["side"] == "YES":
        pnl_pct = ((current_price - entry) / entry) * 100 if entry else 0
    else:
        # BUY NO: profit when YES price falls
        pnl_pct = ((entry - current_price) / entry) * 100 if entry else 0

    return {**trade, "current_price": current_price, "pnl_pct": round(pnl_pct, 2)}


def _fetch_current_price(condition_id: str) -> float | None:
    try:
        resp = requests.get(
            f"{config.API_BASE}/markets/{condition_id}", timeout=10
        )
        if resp.ok:
            data = resp.json()
            for token in data.get("tokens", []):
                if token.get("outcome", "").lower() == "yes":
                    return float(token.get("price") or data.get("last_trade_price") or 0)
            return float(data.get("last_trade_price") or 0)
    except requests.RequestException:
        pass
    return None


# ── Close position ────────────────────────────────────────────────────────────

def close_position(condition_id: str) -> dict | None:
    """
    Manually close an open position by submitting the inverse order via OWS.
    Returns updated trade record or None if no open position.
    """
    pnl = get_pnl(condition_id)
    if not pnl:
        return None

    current_price = pnl.get("current_price")
    if current_price is None:
        return None

    # Build inverse order
    close_side = "NO" if pnl["side"] == "YES" else "YES"
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT token_id FROM markets WHERE condition_id = ?",
        (condition_id,),
    ).fetchone()
    conn.close()

    market = {
        "condition_id": condition_id,
        "token_id": row[0] if row else "",
        "last_price": current_price,
    }
    order = build_clob_order(market, close_side, pnl["size_usd"])
    tx_hash = _sign_with_ows(order)
    closed_at = int(time.time())

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """UPDATE trades SET closed_at = ?, exit_price = ?
           WHERE condition_id = ? AND closed_at IS NULL""",
        (closed_at, current_price, condition_id),
    )
    conn.commit()
    conn.close()

    return {
        **pnl,
        "closed_at": closed_at,
        "exit_price": current_price,
        "close_tx_hash": tx_hash,
    }
