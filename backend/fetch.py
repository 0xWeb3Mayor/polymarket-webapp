import sqlite3
import time
import requests
import config
from datetime import datetime, timezone


def _parse_timestamp(value) -> int:
    """Parse Polymarket date values — handles ISO strings, unix ints, and None."""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return int(datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).timestamp())
        except ValueError:
            return 0
    return 0

DB_PATH = config.DB_PATH


# ── Wallet balance ────────────────────────────────────────────────────────────

# Multiple public Polygon RPCs — tried in order until one works
_POLYGON_RPCS = [
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
    "https://polygon-bor-rpc.publicnode.com",
    "https://1rpc.io/matic",
]


def _erc20_balance(contract: str, wallet: str) -> tuple[float, str | None]:
    """
    Query ERC-20 balanceOf via Polygon RPC.
    Returns (balance, error_message). Tries multiple RPCs before giving up.
    """
    if not wallet:
        return 0.0, "no wallet address configured"

    selector = "0x70a08231"
    padded = wallet.lower().replace("0x", "").zfill(64)
    payload = {
        "jsonrpc": "2.0", "method": "eth_call",
        "params": [{"to": contract, "data": selector + padded}, "latest"],
        "id": 1,
    }

    rpcs = [config.POLYGON_RPC] + [r for r in _POLYGON_RPCS if r != config.POLYGON_RPC]
    last_error = None

    for rpc in rpcs:
        try:
            r = requests.post(rpc, json=payload, timeout=8)
            r.raise_for_status()
            result = r.json().get("result") or "0x0"
            if result in ("0x", "0x0", "", None):
                return 0.0, None
            return int(result, 16) / 1_000_000, None
        except Exception as e:
            last_error = f"{rpc}: {e}"
            continue

    return 0.0, f"all RPCs failed — last: {last_error}"


def get_wallet_balance() -> dict:
    """Return USDC balance on Polygon for the configured OWS wallet address."""
    address = config.OWS_WALLET_ADDRESS
    if not address:
        return {
            "address": None, "usdc": None, "usdc_e": None,
            "total": None, "chain": "polygon", "error": None,
        }

    usdc,   err1 = _erc20_balance(config.USDC_POLYGON,   address)
    usdc_e, err2 = _erc20_balance(config.USDC_POLYGON_E, address)
    error = err1 or err2 or None

    if error:
        print(f"  [WARN] Wallet balance fetch failed: {error}")

    return {
        "address": address,
        "usdc":   round(usdc,   2),
        "usdc_e": round(usdc_e, 2),
        "total":  round(usdc + usdc_e, 2),
        "chain":  "polygon",
        "error":  error,
    }


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            condition_id TEXT PRIMARY KEY,
            question TEXT,
            token_id TEXT,
            close_time INTEGER,
            last_price REAL,
            volume_24h REAL,
            liquidity REAL,
            fetched_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS price_history (
            condition_id TEXT,
            timestamp INTEGER,
            price REAL,
            volume REAL,
            PRIMARY KEY (condition_id, timestamp)
        );

        CREATE TABLE IF NOT EXISTS forecasts (
            condition_id TEXT,
            run_at INTEGER,
            horizon_hours INTEGER,
            forecast_price REAL,
            ci_80_low REAL,
            ci_80_high REAL,
            divergence_pct REAL,
            signal TEXT
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            question TEXT,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            size_usd REAL NOT NULL,
            signal TEXT NOT NULL,
            tx_hash TEXT,
            executed_at INTEGER NOT NULL,
            closed_at INTEGER,
            exit_price REAL,
            ows_wallet TEXT NOT NULL,
            paper_trade INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            level TEXT NOT NULL,
            event TEXT NOT NULL,
            condition_id TEXT,
            detail TEXT
        );
    """)
    conn.commit()
    conn.close()


def _is_cache_fresh(fetched_at: int) -> bool:
    return (time.time() - fetched_at) < config.CACHE_TTL_HOURS * 3600


def _market_passes_filters(market: dict) -> bool:
    now = time.time()
    try:
        close_time = int(market.get("close_time") or 0)
        liquidity = float(market.get("liquidity") or 0)
        volume_24h = float(market.get("volume24hr") or 0)
        last_price = float(market.get("last_trade_price") or 0)
        active = market.get("active", False)
        closed = market.get("closed", True)
        archived = market.get("archived", True)

        if not active or closed or archived:
            return False
        if liquidity < config.MIN_LIQUIDITY:
            return False
        if volume_24h < config.MIN_VOLUME_24H:
            return False
        if not (config.PRICE_MIN <= last_price <= config.PRICE_MAX):
            return False
        days_to_close = (close_time - now) / 86400
        if not (config.RESOLUTION_MIN_DAYS <= days_to_close <= config.RESOLUTION_MAX_DAYS):
            return False
        return True
    except (TypeError, ValueError):
        return False


def _get_yes_token_id(market: dict) -> str | None:
    for token in market.get("tokens", []):
        if token.get("outcome", "").lower() == "yes":
            return token["token_id"]
    return None


GAMMA_API = "https://gamma-api.polymarket.com"


def fetch_markets() -> list[dict]:
    """
    Return all active Polymarket markets passing filters.
    Uses Gamma API (covers ALL markets: AMM + CLOB).
    Falls back to CLOB API if Gamma fails.
    Results are cached for CACHE_TTL_HOURS.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT * FROM markets WHERE fetched_at > ?",
                          (int(time.time()) - config.CACHE_TTL_HOURS * 3600,))
    rows = cursor.fetchall()
    conn.close()

    if rows:
        cols = ["condition_id", "question", "token_id", "close_time",
                "last_price", "volume_24h", "liquidity", "fetched_at"]
        return [dict(zip(cols, row)) for row in rows]

    markets = _fetch_markets_gamma()
    if not markets:
        print("  [WARN] Gamma market fetch returned 0 — falling back to CLOB API")
        markets = _fetch_markets_clob()

    if markets:
        conn = sqlite3.connect(DB_PATH)
        conn.executemany(
            "INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?,?,?,?)",
            [(m["condition_id"], m["question"], m["token_id"], m["close_time"],
              m["last_price"], m["volume_24h"], m["liquidity"], m["fetched_at"])
             for m in markets]
        )
        conn.commit()
        conn.close()

    return markets


def _fetch_markets_gamma() -> list[dict]:
    """Fetch all active markets from Gamma API (covers AMM + CLOB, all market types)."""
    markets = []
    offset = 0
    limit = 100

    while True:
        for attempt in range(3):
            try:
                resp = requests.get(
                    f"{GAMMA_API}/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "archived": "false",
                        "limit": limit,
                        "offset": offset,
                        "order": "volume24hr",
                        "ascending": "false",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as e:
                if attempt == 2:
                    print(f"  [WARN] Gamma page offset={offset} failed: {e}")
                    return markets
                time.sleep(2)

        # Gamma returns a list directly (not wrapped in "data")
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            break

        for market in items:
            if not _gamma_market_passes_filters(market):
                continue
            token_id = _get_gamma_token_id(market)
            if not token_id:
                continue
            entry = {
                "condition_id": market.get("conditionId") or market.get("condition_id", ""),
                "question": market.get("question", ""),
                "token_id": token_id,
                "close_time": _parse_timestamp(market.get("endDate") or market.get("end_date")),
                "last_price": float(market.get("lastTradePrice") or market.get("bestBid") or 0),
                "volume_24h": float(market.get("volume24hr") or market.get("oneDayVolume") or 0),
                "liquidity": float(market.get("liquidity") or 0),
                "fetched_at": int(time.time()),
            }
            if entry["condition_id"]:
                markets.append(entry)

        print(f"  [Gamma] offset={offset} — {len(markets)} markets so far...")
        offset += limit
        if len(items) < limit:
            break

    return markets


def _gamma_market_passes_filters(market: dict) -> bool:
    now = time.time()
    try:
        close_time = _parse_timestamp(market.get("endDate") or market.get("end_date"))
        liquidity  = float(market.get("liquidity") or 0)
        volume_24h = float(market.get("volume24hr") or market.get("oneDayVolume") or 0)
        last_price = float(market.get("lastTradePrice") or market.get("bestBid") or 0)

        if liquidity < config.MIN_LIQUIDITY:
            return False
        if volume_24h < config.MIN_VOLUME_24H:
            return False
        if last_price > 0 and not (config.PRICE_MIN <= last_price <= config.PRICE_MAX):
            return False
        if close_time > 0:
            days_to_close = (close_time - now) / 86400
            if not (config.RESOLUTION_MIN_DAYS <= days_to_close <= config.RESOLUTION_MAX_DAYS):
                return False
        return True
    except (TypeError, ValueError):
        return False


def _get_gamma_token_id(market: dict) -> str | None:
    """Extract YES token_id from Gamma market structure."""
    # Gamma may have clobTokenIds or tokens array
    clob_ids = market.get("clobTokenIds")
    if clob_ids:
        try:
            import json
            ids = json.loads(clob_ids) if isinstance(clob_ids, str) else clob_ids
            if ids:
                return str(ids[0])  # first = YES token
        except Exception:
            pass
    tokens = market.get("tokens", [])
    for t in tokens:
        if str(t.get("outcome", "")).lower() == "yes":
            return t.get("token_id") or t.get("tokenId")
    if tokens:
        return tokens[0].get("token_id") or tokens[0].get("tokenId")
    # Fall back to conditionId itself — Gamma history works with conditionId
    return market.get("conditionId") or market.get("condition_id")


def _fetch_markets_clob() -> list[dict]:
    """Fallback: fetch from CLOB API (orderbook markets only)."""
    markets = []
    cursor_val = ""
    page = 0
    while True:
        page += 1
        params = {"next_cursor": cursor_val} if cursor_val else {}
        for attempt in range(3):
            try:
                resp = requests.get(f"{config.API_BASE}/markets", params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as e:
                if attempt == 2:
                    return markets
                time.sleep(3)

        for market in data.get("data", []):
            if not _market_passes_filters(market):
                continue
            token_id = _get_yes_token_id(market)
            if not token_id:
                continue
            entry = {
                "condition_id": market["condition_id"],
                "question": market["question"],
                "token_id": token_id,
                "close_time": int(market.get("close_time") or 0),
                "last_price": float(market.get("last_trade_price") or 0),
                "volume_24h": float(market.get("volume24hr") or 0),
                "liquidity": float(market.get("liquidity") or 0),
                "fetched_at": int(time.time()),
            }
            markets.append(entry)

        cursor_val = data.get("next_cursor", "")
        if not cursor_val or cursor_val == "LTE=":
            break
    return markets


def _fetch_gamma_history(condition_id: str) -> list | None:
    """Fetch price history from Gamma API using conditionId.

    Gamma covers ALL Polymarket markets (AMM + CLOB).
    CLOB prices-history only has data for orderbook-traded markets.
    """
    for interval in ("max", "1m", "1w"):
        try:
            resp = requests.get(
                f"{GAMMA_API}/prices-history",
                params={"market": condition_id, "interval": interval, "fidelity": 60},
                timeout=10,
            )
            if resp.ok:
                data = resp.json().get("history")
                if data:
                    print(f"  [INFO] Gamma prices-history: {len(data)} points (interval={interval})")
                    return data
        except requests.RequestException:
            pass
    return None


def _fetch_clob_history(token_id: str) -> list | None:
    """Call CLOB prices-history; returns data only for CLOB orderbook markets."""
    try:
        resp = requests.get(
            f"{config.API_BASE}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": 60},
            timeout=10,
        )
        if resp.ok:
            return resp.json().get("history") or None
        print(f"  [WARN] CLOB prices-history returned {resp.status_code} for token {token_id[:20]}...")
    except requests.RequestException as e:
        print(f"  [WARN] CLOB prices-history failed: {e}")
    return None


def fetch_price_history(condition_id: str, token_id: str) -> list[dict]:
    """Return cached hourly price history or fetch from API.

    Strategy:
    1. Gamma API (conditionId) — covers all markets, AMM + CLOB
    2. CLOB API (token_id) — fallback for high-liquidity CLOB-only markets
    """
    min_points = config.MIN_HISTORY_DAYS * 24
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT timestamp, price, volume FROM price_history WHERE condition_id = ? ORDER BY timestamp",
        (condition_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if rows and _is_cache_fresh(rows[-1][0]) and len(rows) >= min_points:
        return [{"timestamp": r[0], "price": r[1], "volume": r[2]} for r in rows]

    # 1. Try Gamma API first — works for all market types
    history = _fetch_gamma_history(condition_id)

    # 2. Fallback to CLOB for high-liquidity orderbook markets
    if not history:
        print(f"  [INFO] Gamma returned no history for {condition_id}, trying CLOB...")
        history = _fetch_clob_history(token_id)

    if not history:
        print(f"  [WARN] No price history available for {condition_id}")
        return []

    entries = [{"timestamp": int(h["t"]), "price": float(h["p"]), "volume": 0.0}
               for h in history]

    # Need at least 24 data points for a meaningful TimesFM forecast
    if len(entries) < 24:
        print(f"  [WARN] Only {len(entries)} history points for {condition_id} (need 24+)")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        "INSERT OR REPLACE INTO price_history VALUES (?,?,?,?)",
        [(condition_id, e["timestamp"], e["price"], e["volume"]) for e in entries]
    )
    conn.commit()
    conn.close()

    return entries
