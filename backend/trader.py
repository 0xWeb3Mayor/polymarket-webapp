"""
trader.py — PolyAgent execution layer

Live mode: set OWS_LIVE=true + PRIVATE_KEY in Railway env vars.
  - Private key is imported into OWS vault on startup (never stored raw)
  - Spending policy enforced by OWS before every signing operation
  - Orders signed via OWS sign_typed_data (EIP-712)

Paper mode (default): full execution loop with mock tx hash, no real USDC moved.
"""

import hashlib
import json
import random
import sqlite3
import time
import requests

import config

# ── OWS import ────────────────────────────────────────────────────────────────

try:
    from ows import (
        import_wallet_private_key,
        list_wallets,
        get_wallet,
        sign_typed_data,
        sign_message,
        create_policy,
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
    Sign a CLOB order via OWS policy-gated signing and submit to Polymarket.
    OWS checks the spending policy before decrypting the key.
    Falls back to paper mode hash if live signing fails.
    """
    if not (config.OWS_LIVE and config.PRIVATE_KEY and _OWS_AVAILABLE):
        return _mock_hash(order)

    try:
        wallet_address = _ows_address()
        if not wallet_address:
            print("  [WARN] OWS wallet address unavailable — paper mode")
            return _mock_hash(order)

        # Convert token_id to int (Polymarket token IDs are large integers)
        try:
            token_id_int = int(order["token_id"])
        except (ValueError, KeyError):
            token_id_int = 0

        # USDC amounts in micro-units (6 decimals)
        maker_amount = int(order["size_usd"] * 1_000_000)
        taker_amount = int(order["size"]     * 1_000_000)
        salt         = random.randint(1, 2**128)

        # EIP-712 typed data — OWS handles domain separation and hashing
        typed_data = json.dumps({
            "types": {
                "EIP712Domain": [
                    {"name": "name",              "type": "string"},
                    {"name": "version",           "type": "string"},
                    {"name": "chainId",           "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Order": _ORDER_STRUCT,
            },
            "primaryType": "Order",
            "domain": _POLY_DOMAIN,
            "message": {
                "salt":          salt,
                "maker":         wallet_address,
                "signer":        wallet_address,
                "taker":         "0x0000000000000000000000000000000000000000",
                "tokenId":       token_id_int,
                "makerAmount":   maker_amount,
                "takerAmount":   taker_amount,
                "expiration":    0,
                "nonce":         0,
                "feeRateBps":    0,
                "side":          0,  # BUY
                "signatureType": 0,  # EOA
            },
        })

        # OWS enforces spending policy before signing
        sig_result = sign_typed_data(config.OWS_WALLET_NAME, "evm", typed_data)
        signature  = sig_result.get("signature", "")

        # Derive CLOB auth headers via OWS message signing
        ts       = int(time.time())
        auth_res = sign_message(config.OWS_WALLET_NAME, "evm", str(ts))
        auth_sig = auth_res.get("signature", "")

        headers = {
            "Content-Type":   "application/json",
            "POLY_ADDRESS":   wallet_address,
            "POLY_SIGNATURE": auth_sig,
            "POLY_TIMESTAMP": str(ts),
            "POLY_NONCE":     "0",
        }

        clob_order = {
            "salt":          str(salt),
            "maker":         wallet_address,
            "signer":        wallet_address,
            "taker":         "0x0000000000000000000000000000000000000000",
            "tokenId":       str(token_id_int),
            "makerAmount":   str(maker_amount),
            "takerAmount":   str(taker_amount),
            "expiration":    "0",
            "nonce":         "0",
            "feeRateBps":    "0",
            "side":          "0",
            "signatureType": "0",
            "signature":     signature,
        }

        resp = requests.post(
            f"{config.API_BASE}/order",
            json={"order": clob_order, "owner": wallet_address, "orderType": "GTC"},
            headers=headers,
            timeout=15,
        )

        if resp.ok:
            data = resp.json()
            tx = data.get("transactionHash") or data.get("orderID")
            return tx or _mock_hash(order)
        else:
            print(f"  [WARN] CLOB submit {resp.status_code}: {resp.text[:200]}")
            return _mock_hash(order)

    except Exception as e:
        print(f"  [WARN] OWS signing failed: {e} — paper mode")
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

    is_paper = not (config.OWS_LIVE and bool(config.PRIVATE_KEY) and _OWS_AVAILABLE)
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

    mode = "PAPER" if is_paper else "LIVE·OWS"
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
