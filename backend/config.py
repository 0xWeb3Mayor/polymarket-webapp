import os

# API
API_BASE = "https://clob.polymarket.com"
API_RATE_LIMIT_PER_MIN = 100

# Market filters — kept wide to scan everything on Polymarket
MIN_LIQUIDITY = 1_000       # USD — low floor, catch emerging markets
MIN_HISTORY_DAYS = 2        # days of price history required for TimesFM
MIN_VOLUME_24H = 50         # USD — very low, we want coverage not just majors
PRICE_MIN = 0.02            # 2¢ — include near-certain and near-impossible markets
PRICE_MAX = 0.98            # 98¢
RESOLUTION_MIN_DAYS = 1     # include markets resolving tomorrow
RESOLUTION_MAX_DAYS = 730   # include 2-year geopolitics markets

# Forecasting
FORECAST_HORIZON_HOURS = 48
CACHE_TTL_HOURS = 6
HISTORY_DAYS = 30           # days of hourly history to feed TimesFM

# Signals
DIVERGENCE_SIGNAL = 0.10    # 10% divergence = signal
DIVERGENCE_STRONG = 0.20    # 20% divergence = strong signal
TOP_N_SIGNALS = 5

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = "/data/scanner.db"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CHARTS_DIR = os.path.join(OUTPUT_DIR, "charts")

# ── PolyAgent trading config ──────────────────────────────────────────────────

# OWS wallet
OWS_WALLET_NAME = os.environ.get("OWS_WALLET_NAME", "polyagent-treasury")
OWS_WALLET_PASSWORD = os.environ.get("OWS_WALLET_PASSWORD", "")
OWS_LIVE = os.environ.get("OWS_LIVE", "false").lower() == "true"

# Polymarket CLOB
CLOB_API_KEY = os.environ.get("CLOB_API_KEY", "")
CLOB_API_SECRET = os.environ.get("CLOB_API_SECRET", "")
CLOB_API_PASSPHRASE = os.environ.get("CLOB_API_PASSPHRASE", "")

# Risk limits (also enforced at OWS policy layer)
MAX_TRADE_USD = float(os.environ.get("MAX_TRADE_USD", "50"))
DAILY_LIMIT_USD = float(os.environ.get("DAILY_LIMIT_USD", "200"))

# Execution gate
AGENT_MIN_LIQUIDITY = 10_000   # 2x standard filter — needs book depth
AGENT_SCAN_INTERVAL = int(os.environ.get("AGENT_SCAN_INTERVAL", "900"))  # 15 min default

# Wallet balance
OWS_WALLET_ADDRESS = os.environ.get("OWS_WALLET_ADDRESS", "")
POLYGON_RPC = os.environ.get("POLYGON_RPC", "https://polygon-rpc.com")
USDC_POLYGON   = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # native USDC
USDC_POLYGON_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # bridged USDC.e

# Geopolitics keyword filter (markets matching any keyword are prioritised)
GEOPOLITICS_KEYWORDS = [
    "election", "president", "prime minister", "minister", "parliament",
    "senate", "congress", "vote", "referendum", "chancellor", "leader",
    "war", "conflict", "military", "troops", "invasion", "ceasefire",
    "missile", "nuclear", "coup", "assassination", "protest", "regime",
    "nato", "sanctions", "treaty", "alliance", "summit", "diplomacy",
    "russia", "ukraine", "china", "taiwan", "israel", "iran", "north korea",
    "gaza", "middle east", "europe", "geopolit", "bilateral", "tariff",
    "trade war", "us-china", "g7", "g20", "un security",
]
