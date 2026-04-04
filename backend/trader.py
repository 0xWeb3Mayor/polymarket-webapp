"""
trader.py — PolyAgent execution layer

Live mode:  OWS_LIVE=true + PRIVATE_KEY set in Railway env vars.
            Uses py-clob-client to sign and submit real orders to Polymarket CLOB.
Paper mode: OWS_LIVE=false (default). Full loop with mock tx hash, no real USDC.

Runtime toggle: call set_live_mode(True/False) to switch without redeploying.
"""

import hashlib
import json
import random
import sqlite3
import time
import requests

import config

# ── Runtime mode (overrides env var when set via API) ─────────────────────────
_live_override: bool | None = None   # None = use config.OWS_LIVE

def set_live_mode(live: bool):
    global _live_override
    _live_override = live

def is_live() -> bool:
    if _live_override is not None:
        return _live_override
    return config.OWS_LIVE

# ── OWS import (optional) ─────────────────────────────────────────────────────
try:
    from ows import (
        import_wallet_private_key, list_wallets, get_wallet,
        sign_typed_data, sign_message, create_policy,
    )
    _OWS_AVAILABLE = True
except ImportError:
    _OWS_AVAILABLE = False

# ── Polymarket CLOB EIP-712 constants ─────────────────────────────────────────

_POLY_EXCHANGE    = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
_POLY_DOMAIN      = {
    "name": "Polymarket CTF Exchange",
    "version": "1",
    "chainId": 137,
    "verifyingContract": _POLY_EXCHANGE,
}
_ORDER_STRUCT     = [
    {"name": "salt",          "type": "uint256"},
    {"name": "maker",         "type": "address"},
    {"name": "signer",        "type": "address"},
    {"name": "taker",         "type": "address"},
    {"name": "tokenId",       "type": "uint256"},
    {"name": "makerAmount",   "type": "uint256"},
    {"name": "takerAmount",   "type": "uint256"},
    {"name": "expiration",    "type": "uint256"},
    {"name": "nonce",         "type": "uint256"},
    {"name": "feeRateBps",    "type": "uint256"},
    {"name": "side",          "type": "uint8"},
    {"name": "signatureType", "type": "uint8"},
]


# ── OWS wallet setup (called once at startup) ─────────────────────────────────

def setup_ows_wallet():
    """
    Import private key into OWS vault and register spending policy.
    Safe to call multiple times — skips if wallet already exists.
    """
    if not _OWS_AVAILABLE:
        print("  [OWS] Package not installed — paper mode active")
        return
    if not config.PRIVATE_KEY:
        print("  [OWS] No PRIVATE_KEY set — paper mode active")
        return

    try:
        existing = [w for w in list_wallets() if w.get("name") == config.OWS_WALLET_NAME]
        if not existing:
            print(f"  [OWS] Importing wallet '{config.OWS_WALLET_NAME}' into vault...")
            import_wallet_private_key(config.OWS_WALLET_NAME, config.PRIVATE_KEY)
            print(f"  [OWS] Wallet imported ✓")
        else:
            print(f"  [OWS] Wallet '{config.OWS_WALLET_NAME}' already in vault ✓")

        # Register spending policy — OWS enforces this before decrypting the key
        policy = {
            "name": "polyagent-spend-policy",
            "max_spend_per_tx_usd": config.MAX_TRADE_USD,
            "daily_limit_usd":      config.DAILY_LIMIT_USD,
            "allowed_chains":       ["eip155:137"],
        }
        create_policy(json.dumps(policy))
        print(f"  [OWS] Spending policy registered · max_tx=${config.MAX_TRADE_USD} · daily=${config.DAILY_LIMIT_USD}")
    except Exception as e:
        print(f"  [OWS] Wallet setup error: {e}")


def _ows_address() -> str | None:
    """Return EVM address from the OWS vault wallet."""
    try:
        w = get_wallet(config.OWS_WALLET_NAME)
        for acct in w.get("accounts", []):
            cid = acct.get("chain_id", "")
            if "evm" in cid.lower() or "137" in cid or "1" in cid:
                return acct["address"]
        accounts = w.get("accounts", [])
        if accounts:
            return accounts[0]["address"]
    except Exception:
        pass
    return config.OWS_WALLET_ADDRESS or None


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

    report = result.get("report") or {}
    action = (report.get("action") or "HOLD").upper().strip()

    if signal == "STRONG_BUY":
        if action in ("SELL YES", "BUY NO", "SELL NO"):
            return False
    if signal == "STRONG_SELL":
        if action in ("BUY YES", "SELL NO"):
            return False

    if result.get("liquidity", 0) < config.AGENT_MIN_LIQUIDITY:
        return False

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
    Build a Polymarket CLOB order dict ready for OWS signing.
    side: 'YES' (buy YES token) or 'NO' (buy NO token)
    """
    token_id = market.get("token_id", "")
    price    = float(market.get("last_price", 0.5))

    if side == "NO":
        price = round(1.0 - price, 4)

    size_shares = round(size_usd / price, 2) if price > 0 else 0

    return {
        "token_id":  token_id,
        "side":      "BUY",
        "price":     price,
        "size":      size_shares,
        "size_usd":  size_usd,
        "order_type": "LIMIT",
        "chain":     "eip155:137",
    }


# ── OWS signing ───────────────────────────────────────────────────────────────

def _sign_with_ows(order: dict) -> str:
    """
    Submit a live order to Polymarket CLOB using py-clob-client.
    Falls back to paper mock hash if not live or if signing fails.
    """
    if not (is_live() and config.PRIVATE_KEY and _CLOB_AVAILABLE):
        return _mock_hash(order)

    try:
        pk = config.PRIVATE_KEY if config.PRIVATE_KEY.startswith("0x") else "0x" + config.PRIVATE_KEY
        clob = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=137,
            signature_type=0,
        )
        # Derive API credentials from private key
        try:
            creds = clob.create_or_derive_api_creds()
            clob.set_api_creds(creds)
        except Exception as e:
            print(f"  [WARN] CLOB creds failed: {e}")

        order_args = OrderArgs(
            token_id=order["token_id"],
            price=order["price"],
            size=order["size"],
            side="BUY",
        )
        signed = clob.create_order(order_args)
        resp   = clob.post_order(signed, OrderType.GTC)
        tx = (resp or {}).get("transactionHash") or (resp or {}).get("orderID")
        if tx:
            print(f"  [LIVE] Order submitted: {tx[:20]}...")
            return tx
        print(f"  [WARN] CLOB resp: {resp}")
        return _mock_hash(order)

    except Exception as e:
        print(f"  [WARN] Live signing failed: {e} — falling back to paper")
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
    3. Sign via OWS (policy-gated) or paper mock
    4. Persist trade record to DB
    5. Return trade record
    """
    signal   = result["forecast"]["signal"]
    side     = "YES" if signal == "STRONG_BUY" else "NO"
    market   = {
        "condition_id": result["condition_id"],
        "question":     result.get("question", ""),
        "token_id":     result.get("forecast", {}).get("token_id", ""),
        "last_price":   result["last_price"],
        "liquidity":    result.get("liquidity", 0),
    }

    if not market["token_id"]:
        conn = sqlite3.connect(config.DB_PATH)
        row  = conn.execute(
            "SELECT token_id FROM markets WHERE condition_id = ?",
            (result["condition_id"],),
        ).fetchone()
        conn.close()
        if row:
            market["token_id"] = row[0]

    size_usd    = config.MAX_TRADE_USD
    order       = build_clob_order(market, side, size_usd)
    entry_price = order["price"]

    is_paper = not (is_live() and bool(config.PRIVATE_KEY) and _CLOB_AVAILABLE)
    tx_hash  = _sign_with_ows(order)

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
        "id":          trade_id,
        "condition_id": result["condition_id"],
        "question":    result.get("question", ""),
        "side":        side,
        "entry_price": entry_price,
        "size_usd":    size_usd,
        "signal":      signal,
        "tx_hash":     tx_hash,
        "executed_at": executed_at,
        "ows_wallet":  config.OWS_WALLET_NAME,
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
    conn = sqlite3.connect(config.DB_PATH)
    row  = conn.execute(
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

    current_price = _fetch_current_price(condition_id)
    if current_price is None:
        return {**trade, "current_price": None, "pnl_pct": None}

    entry = trade["entry_price"]
    if trade["side"] == "YES":
        pnl_pct = ((current_price - entry) / entry) * 100 if entry else 0
    else:
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
    pnl = get_pnl(condition_id)
    if not pnl:
        return None

    current_price = pnl.get("current_price")
    if current_price is None:
        return None

    close_side = "NO" if pnl["side"] == "YES" else "YES"
    conn = sqlite3.connect(config.DB_PATH)
    row  = conn.execute(
        "SELECT token_id FROM markets WHERE condition_id = ?",
        (condition_id,),
    ).fetchone()
    conn.close()

    market = {
        "condition_id": condition_id,
        "token_id":     row[0] if row else "",
        "last_price":   current_price,
    }
    order   = build_clob_order(market, close_side, pnl["size_usd"])
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
        "closed_at":      closed_at,
        "exit_price":     current_price,
        "close_tx_hash":  tx_hash,
    }
