import os

# API
API_BASE = "https://clob.polymarket.com"
API_RATE_LIMIT_PER_MIN = 100

# Market filters
MIN_LIQUIDITY = 5_000       # USD
MIN_HISTORY_DAYS = 14       # days of hourly data required
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
