import sqlite3
import time
import requests
import config

DB_PATH = config.DB_PATH


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


def fetch_markets() -> list[dict]:
    """Return cached markets if fresh, else fetch from API and cache."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT * FROM markets WHERE fetched_at > ?",
                          (int(time.time()) - config.CACHE_TTL_HOURS * 3600,))
    rows = cursor.fetchall()
    conn.close()

    if rows:
        cols = ["condition_id", "question", "token_id", "close_time",
                "last_price", "volume_24h", "liquidity", "fetched_at"]
        return [dict(zip(cols, row)) for row in rows]

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
                    raise
                print(f"  [WARN] Page {page} attempt {attempt+1} failed: {e}. Retrying...")
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

        print(f"  Page {page} — {len(markets)} markets found so far...")
        cursor_val = data.get("next_cursor", "")
        if not cursor_val or cursor_val == "LTE=":
            break

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


def _fetch_clob_history(token_id: str, params: dict) -> list | None:
    """Call CLOB prices-history with given params; return history list or None."""
    try:
        resp = requests.get(
            f"{config.API_BASE}/prices-history",
            params={"market": token_id, **params},
            timeout=10,
        )
        if not resp.ok:
            print(f"  [WARN] CLOB prices-history returned {resp.status_code} for token {token_id[:20]}...")
            return None
        return resp.json().get("history") or None
    except requests.RequestException as e:
        print(f"  [WARN] CLOB prices-history request failed: {e}")
        return None


def fetch_price_history(condition_id: str, token_id: str) -> list[dict]:
    """Return cached hourly price history or fetch from API."""
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

    end_ts = int(time.time())
    start_ts = end_ts - config.HISTORY_DAYS * 86400

    # Primary: timestamp-range request (30 days, hourly)
    history = _fetch_clob_history(token_id, {"startTs": start_ts, "endTs": end_ts, "fidelity": 60})

    # Fallback: let CLOB return whatever it has (handles new markets / 400 on timestamp range)
    if not history:
        history = _fetch_clob_history(token_id, {"interval": "max", "fidelity": 60})

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
