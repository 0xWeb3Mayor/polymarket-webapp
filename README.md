# PolyAgent — Autonomous Prediction Market Trading Agent

An autonomous AI trading agent for [Polymarket](https://polymarket.com) powered by OWS policy-gated signing, TimesFM forecasting, and Claude AI analysis.

**Demo:** https://x.com/mayorxbt/status/2040445286414213313
**GitHub:** [0xWeb3Mayor/polymarket-webapp](https://github.com/0xWeb3Mayor/polymarket-webapp)

---

## What it does

PolyAgent scans every Polymarket prediction market every 15 minutes, finds mispricings using TimesFM price forecasting + Claude AI analysis, and executes trades autonomously — with OWS enforcing spending limits before every signing operation.

The private key never exists in the app. It lives in the OWS vault. Every trade is policy-gated.

---

## OWS integration

PolyAgent uses [Open Wallet Standard](https://github.com/open-wallet-standard/core) as its signing layer:

```python
from ows import (
    import_wallet_private_key,  # stores key in encrypted vault on startup
    create_policy,              # registers max_spend_per_tx + daily_limit
    sign_typed_data,            # signs Polymarket CLOB EIP-712 orders
    sign_message,               # derives CLOB auth headers
)
```

**On startup:**
1. `import_wallet_private_key("polyagent-treasury", PRIVATE_KEY)` — key enters OWS vault, never exposed again
2. `create_policy({"max_spend_per_tx_usd": 50, "daily_limit_usd": 200, "allowed_chains": ["eip155:137"]})` — spending policy registered

**On every trade:**
3. `sign_typed_data(wallet, "evm", polymarket_eip712_order)` — OWS checks policy before decrypting key
4. `sign_message(wallet, "evm", timestamp)` — derives Polymarket CLOB auth headers
5. Order submitted to `clob.polymarket.com/order`

See [`backend/trader.py`](backend/trader.py) for the full implementation.

---

## How it works

1. **Fetch** — Gamma API pulls all active Polymarket markets (3,800+). Geopolitics markets (elections, wars, sanctions, treaties) are prioritized.
2. **Forecast** — TimesFM (Google's zero-shot time series model) predicts price over the next 48 hours with an 80% confidence interval
3. **Signal** — divergence ≥ 20% between forecast and current price → `STRONG_BUY` or `STRONG_SELL`
4. **Gate** — 5-layer execution gate:
   - Signal must be STRONG_BUY or STRONG_SELL
   - Claude AI must not explicitly oppose the direction
   - Market liquidity > $10,000
   - No existing open position for this market
   - OWS spending policy check before signing
5. **Execute** — OWS signs the EIP-712 CLOB order, submits to Polymarket
6. **Log** — every decision (signal, gate block, execution) logged to dashboard in real time

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.11), SQLite |
| Signing | [Open Wallet Standard](https://github.com/open-wallet-standard/core) — policy-gated EVM signing |
| Forecasting | [TimesFM 1.0 200M](https://github.com/google-research/timesfm) — zero-shot time series |
| AI Analysis | Claude Sonnet (`claude-sonnet-4-6`) via Anthropic API |
| Price Data | Polymarket Gamma API + CLOB API |
| Deploy | Railway (backend, auto-starts agent) + Vercel (frontend) |

---

## Project structure

```
polymarket-webapp/
├── backend/
│   ├── main.py          # FastAPI — all endpoints + agent lifecycle
│   ├── agent.py         # Autonomous scan loop (geo-priority, 15min interval)
│   ├── trader.py        # OWS signing + gate logic + trade execution
│   ├── fetch.py         # Gamma API market fetch + multi-chain wallet balance
│   ├── forecast.py      # TimesFM inference
│   ├── report.py        # Claude AI report generation
│   ├── signals.py       # Divergence + signal classification
│   ├── config.py        # All env vars and constants
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Home — URL scanner input
│   │   ├── trades/
│   │   │   ├── page.tsx         # Server component — fetches trades + agent state
│   │   │   └── TradesView.tsx   # Client component — dashboard, logs, positions
│   │   └── m/[id]/
│   │       ├── page.tsx         # Market detail server component
│   │       └── MarketView.tsx   # Chart, signal, AI report
│   ├── components/
│   │   ├── TradeCard.tsx        # Trade position card with P&L
│   │   ├── SignalCard.tsx       # Signal badge
│   │   ├── ForecastChart.tsx    # Recharts history + forecast + CI band
│   │   └── AIReport.tsx         # Structured Claude analysis panel
│   └── lib/
│       └── api.ts               # All API types and fetch helpers
├── railway.json
└── vercel.json
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/trades` | All trades with P&L |
| `POST` | `/trades/{id}/close` | Close an open position via OWS |
| `GET` | `/agent/status` | Running state, live mode, wallet config |
| `POST` | `/agent/start` | Start autonomous loop |
| `POST` | `/agent/stop` | Stop autonomous loop |
| `GET` | `/agent/logs` | Live activity log |
| `GET` | `/wallet/balance` | USDC balance across Polygon, Ethereum, Base |
| `POST` | `/analyze` | Parse Polymarket URL → condition_id |
| `GET` | `/market/{id}` | Forecast + AI report for any market |

---

## Environment variables

| Variable | Where | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Railway | Claude API key |
| `PRIVATE_KEY` | Railway | Wallet private key — imported into OWS vault on startup |
| `OWS_WALLET_ADDRESS` | Railway | Wallet address for balance display |
| `OWS_LIVE` | Railway | `true` = live trading, `false` = paper mode |
| `MAX_TRADE_USD` | Railway | Max USDC per trade (default: 50) |
| `DAILY_LIMIT_USD` | Railway | Daily spend limit enforced by OWS (default: 200) |
| `NEXT_PUBLIC_API_URL` | Vercel | Railway backend URL |
| `NEXT_PUBLIC_APP_URL` | Vercel | Vercel frontend URL |

---

## Agent activity (live)

The agent is currently running on Railway mainnet. Recent decisions from the activity log:

| Time | Signal | Market | Action |
|---|---|---|---|
| 13:46 | STRONG_BUY [GEO] | Will France send warships through Strait of Hormuz? | Executed BUY YES @ 0.042 |
| 13:45 | STRONG_BUY [GEO] | Will Greece send warships through Strait of Hormuz? | Executed BUY YES @ 0.02 |
| 13:45 | STRONG_BUY [GEO] | Will Iran sabotage undersea internet cables by April 30? | Executed BUY YES @ 0.05 |
| 13:45 | STRONG_SELL [GEO] | Will Putin visit China by May 31? | Executed BUY NO @ 0.24 |
| 13:45 | STRONG_BUY [GEO] | Will Russia capture Bilytske by June 30? | Executed BUY YES @ 0.21 |
| 13:38 | STRONG_BUY [GEO] | Ukraine/Russia ceasefire market | Blocked — position already open |
| 13:38 | STRONG_SELL [GEO] | div=-27.1% signal | Blocked — Claude opposes (action=SELL YES) |

All positions: $50 size · OWS policy-gated · paper_trade=0 (live mode)

---

## Local development

**Backend**
```bash
cd backend
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... OWS_LIVE=false uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```
