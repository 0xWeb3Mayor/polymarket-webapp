import os

# API
API_BASE = "https://clob.polymarket.com"
API_RATE_LIMIT_PER_MIN = 100

# Market filters
MIN_LIQUIDITY = 5_000       # USD
MIN_HISTORY_DAYS = 3        # days of hourly data required
MIN_VOLUME_24H = 500        # USD
PRICE_MIN = 0.05
PRICE_MAX = 0.95
RESOLUTION_MIN_DAYS = 7     # market must resolve at least 7 days out
RESOLUTION_MAX_DAYS = 90    # market must resolve within 90 days

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
AGENT_SCAN_INTERVAL = 3600     # seconds between autonomous scans
