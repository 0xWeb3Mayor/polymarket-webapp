# PolyAgent — Developer Reference

> Last updated: 2026-04-04
> Repo: github.com/0xWeb3Mayor/polymarket-webapp
> Live scanner: scanner.polyweb.pro

---

## 1. What this is

**Polymarket Scanner** (existing, live) — paste a Polymarket URL, get a TimesFM forecast + Claude analysis report.

**PolyAgent** (built on top) — autonomous trading agent. Scans markets on a 1-hour loop, finds STRONG mispricings, gets Claude confirmation, signs orders via OWS (Open Wallet Standard), submits to Polymarket CLOB. Paper trading by default.

---

## 2. Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11 / FastAPI / uvicorn |
| Forecasting | TimesFM (zero-shot, CPU) |
| AI analysis | Claude claude-sonnet-4-6 via Anthropic SDK |
| Trading | py-clob-client (Polymarket CLOB) |
| Wallet / signing | Open Wallet Standard (OWS) SDK |
| Database | SQLite at `/data/scanner.db` |
| Frontend | Next.js (App Router) / Tailwind / JetBrains Mono |
| Charts | Recharts |
| OG images | @vercel/og (edge runtime) |
| Backend deploy | Railway (Docker) |
| Frontend deploy | Vercel |

---

## 3. Repo structure

```
polymarket-webapp/
├── backend/
│   ├── main.py          # FastAPI app + all endpoints
│   ├── config.py        # All env vars + constants
│   ├── fetch.py         # Market fetch + price history + init_db
│   ├── forecast.py      # TimesFM wrapper
│   ├── signals.py       # Divergence calc + signal classification
│   ├── report.py        # Claude AI analysis report
│   ├── parser.py        # Polymarket URL → condition_id
│   ├── trader.py        # OWS signing + CLOB orders + gate logic  ← NEW
│   ├── agent.py         # Autonomous scan loop + DB logging        ← NEW
│   ├── requirements.txt
│   ├── Dockerfile
│   └── Procfile
└── frontend/
    ├── app/
    │   ├── page.tsx              # Home (URL input)
    │   ├── m/[id]/               # Market result page
    │   ├── trades/               # PolyAgent trades dashboard       ← NEW
    │   │   ├── page.tsx
    │   │   └── TradesView.tsx
    │   └── api/og/
    │       ├── [id]/route.tsx    # Market OG image
    │       └── trade/[id]/route.tsx  # Trade OG image              ← NEW
    ├── components/
    │   ├── SignalCard.tsx
    │   ├── AIReport.tsx
    │   ├── ForecastChart.tsx
    │   ├── HorizonToggle.tsx
    │   ├── ShareButton.tsx
    │   ├── UrlInput.tsx
    │   ├── TradeCard.tsx         ← NEW
    │   └── ShareableTrade.tsx    ← NEW
    └── lib/
        └── api.ts                # All types + fetch helpers
```

---

## 4. Database schema

**SQLite at `/data/scanner.db`** — persisted Railway volume.

```sql
-- Existing tables
markets         (condition_id PK, question, token_id, close_time, last_price, volume_24h, liquidity, fetched_at)
price_history   (condition_id, timestamp, price, volume)  PK(condition_id, timestamp)
forecasts       (condition_id, run_at, horizon_hours, forecast_price, ci_80_low, ci_80_high, divergence_pct, signal)

-- PolyAgent tables
trades (
  id            INTEGER PK AUTOINCREMENT,
  condition_id  TEXT NOT NULL,
  question      TEXT,
  side          TEXT NOT NULL,        -- 'YES' or 'NO'
  entry_price   REAL NOT NULL,
  size_usd      REAL NOT NULL,
  signal        TEXT NOT NULL,        -- STRONG_BUY / STRONG_SELL
  tx_hash       TEXT,
  executed_at   INTEGER NOT NULL,
  closed_at     INTEGER,
  exit_price    REAL,
  ows_wallet    TEXT NOT NULL,
  paper_trade   INTEGER DEFAULT 1     -- 1=paper, 0=live
)

agent_logs (
  id            INTEGER PK AUTOINCREMENT,
  ts            INTEGER NOT NULL,
  level         TEXT NOT NULL,        -- INFO / SIGNAL / GATE / TRADE / ERROR
  event         TEXT NOT NULL,
  condition_id  TEXT,
  detail        TEXT
)
```

---

## 5. API endpoints

### Existing (do not modify)
```
POST /analyze                    body: {url} → {condition_id, redirect}
GET  /market/{condition_id}      ?horizon=48 → full market + forecast + report
GET  /market/{condition_id}/refresh
GET  /recent                     → last 20 forecasts
GET  /health
```

### PolyAgent (new)
```
GET  /trades                     → last 50 trades with live P&L
GET  /trades/{condition_id}      → full trade detail + fresh report
POST /trades/{condition_id}/close → close open position via OWS

GET  /agent/status               → {running, live, wallet, max_trade_usd, daily_limit_usd}
POST /agent/start                → start autonomous loop
POST /agent/stop                 → stop loop
POST /agent/run-once             → trigger single scan pass (demo/testing)
GET  /agent/logs?limit=100       → recent agent activity log entries
```

---

## 6. The execution gate (5 layers)

A trade only fires when ALL of these pass:

| Layer | Condition |
|---|---|
| Signal strength | STRONG_BUY or STRONG_SELL (>20% divergence) |
| Claude confirmation | `report.action` must be "BUY YES" (for STRONG_BUY) or "BUY NO" (for STRONG_SELL) |
| Liquidity floor | `market.liquidity > $10,000` |
| No duplicate | No open position for this `condition_id` already in DB |
| OWS policy | $50 max/tx, $200/day, Polygon only — enforced at signing layer |

Code: `trader.py → should_execute(result)`

---

## 7. OWS integration

**Chain:** Polygon mainnet (`eip155:137`)
**Deposit:** USDC on Polygon to the address generated by `ows wallet create`

```python
# trader.py — signing flow
from ows import WalletClient
client = WalletClient(wallet_name='polyagent-treasury', password=OWS_WALLET_PASSWORD)
signed_tx = client.sign(transaction=clob_order, policy={
    'max_spend_per_tx': 50,
    'daily_limit': 200,
    'allowed_chains': ['eip155:137'],
})
tx_hash = clob_client.post_order(signed_tx)
```

**Paper mode** (default): OWS signs but order is not submitted to mainnet. A deterministic mock `tx_hash` is generated from `sha256(token_id + price + timestamp)`.

**Live mode**: Set `OWS_LIVE=true` in Railway. Real USDC moves on Polygon.

One-time wallet setup (run on the Railway server or locally):
```bash
pip install open-wallet-standard
ows wallet create --name polyagent-treasury
# → prints Polygon address — fund this with USDC on Polygon
```

---

## 8. Environment variables

### Railway (backend)
```
ANTHROPIC_API_KEY       Claude API key
OWS_WALLET_NAME         polyagent-treasury
OWS_WALLET_PASSWORD     wallet decryption password (never logged)
OWS_LIVE                false (paper) | true (mainnet)
CLOB_API_KEY            Polymarket CLOB API key
CLOB_API_SECRET         Polymarket CLOB API secret
CLOB_API_PASSPHRASE     Polymarket CLOB passphrase
MAX_TRADE_USD           50
DAILY_LIMIT_USD         200
PORT                    set automatically by Railway
```

### Vercel (frontend)
```
NEXT_PUBLIC_API_URL     https://your-railway-app.railway.app
NEXT_PUBLIC_APP_URL     https://your-vercel-app.vercel.app
```

---

## 9. Signal classification

```python
# signals.py
divergence = (forecast_price - last_price) / last_price * 100

STRONG_BUY   → divergence > 20% AND ci_80_low > last_price
BUY          → divergence > 10%
STRONG_SELL  → divergence < -20% AND ci_80_high < last_price
SELL         → divergence < -10%
HOLD         → everything else
```

Agent only acts on `STRONG_BUY` and `STRONG_SELL`.

---

## 10. Agent loop (agent.py)

```
run_agent()           infinite async loop, sleeps AGENT_SCAN_INTERVAL ± 5% jitter
  └─ run_once()       single pass
       ├─ fetch.fetch_markets()             all markets passing filters
       ├─ for each market:
       │    ├─ fetch_price_history()
       │    ├─ fc_module.run_forecast()
       │    ├─ sig_module.classify_signal()
       │    ├─ if not STRONG → skip (no Claude call)
       │    ├─ report_module.generate_report()   ← Claude called here
       │    ├─ trader.should_execute()
       │    └─ trader.execute_trade()            ← OWS signs here
       └─ _log() every decision to agent_logs table
```

**Scan interval:** `config.AGENT_SCAN_INTERVAL` = 3600s (1 hour)
**Market filters (pre-agent):** liquidity > $5k, volume > $500/24h, price 5–95¢, resolves 7–90 days out
**Agent-specific filter:** liquidity > $10k (tighter — needs book depth)

---

## 11. Frontend routes

```
/                     Home — URL input
/m/[condition_id]     Market result — forecast + chart + Claude report
/trades               PolyAgent dashboard — start/stop, activity log, positions, P&L
/api/og/[id]          OG image for market signal cards
/api/og/trade/[id]    OG image for trade share cards
```

---

## 12. Key config constants (config.py)

```python
MIN_LIQUIDITY        = 5_000     # standard market filter
AGENT_MIN_LIQUIDITY  = 10_000    # tighter filter for execution
DIVERGENCE_SIGNAL    = 0.10      # 10% → BUY/SELL
DIVERGENCE_STRONG    = 0.20      # 20% → STRONG_BUY/SELL
MAX_TRADE_USD        = 50        # per-trade cap (also OWS policy)
DAILY_LIMIT_USD      = 200       # daily cap (also OWS policy)
AGENT_SCAN_INTERVAL  = 3600      # seconds between scans
FORECAST_HORIZON_HOURS = 48
DB_PATH              = "/data/scanner.db"
```

---

## 13. Local dev

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Run agent manually (one pass)
curl -X POST http://localhost:8000/agent/run-once

# Start autonomous loop
curl -X POST http://localhost:8000/agent/start

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:3000
```

---

## 14. Files NOT to touch

Per PRD scope guard — these are stable and tested:

- `forecast.py` — TimesFM wrapper
- `signals.py` — divergence + classification
- `report.py` — Claude prompt + JSON parsing
- `parser.py` — URL → condition_id
- All existing `/market/*` and `/analyze` endpoints

---

## 15. Demo script (hackathon)

1. Open `/` — paste a live Polymarket URL
2. Show TimesFM forecast: e.g. 72¢ vs 48¢ market price → STRONG BUY
3. Show Claude report: `action: BUY YES`, reasoning
4. Go to `/trades` — show agent already executed this trade (paper mode)
5. Show activity log: scan → signal → Claude → gate passed → trade fired
6. Show OWS audit: wallet name, policy enforced ($50 cap), key never exposed
7. Click trade tx hash → Polygonscan link

**Tagline:** TimesFM found the signal. Claude confirmed the reasoning. OWS executed it safely.
