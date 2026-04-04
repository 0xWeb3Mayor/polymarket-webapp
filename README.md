# Polymarket Scanner

Paste a Polymarket URL. Get a zero-shot AI forecast and a structured analysis report — in seconds.

**Live:** [scanner.polyweb.pro](https://scanner.polyweb.pro)

---

## What it does

You paste any Polymarket market URL. The app:

1. **Parses the URL** — handles every Polymarket URL format: `/market/0x...`, `/event/slug/market-slug`, raw condition IDs, and share links with hash fragments
2. **Fetches price history** — pulls hourly OHLC data from the Polymarket Gamma API (covers all market types: binary, categorical, political, AMM and CLOB)
3. **Runs TimesFM** — Google's open-source zero-shot time series forecasting model predicts where the price is heading over the next 24, 48, or 72 hours, with an 80% confidence interval
4. **Generates a signal** — compares the forecast to current market price and classifies it: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
5. **Writes an AI report** — Claude (Sonnet) reads the market question, current odds, volume, and the TimesFM forecast, then produces a structured breakdown: what the market asks, what resolves it, key factors, probability estimates, mispricing analysis, and a clear action (BUY YES / BUY NO / HOLD)
6. **Renders a chart** — historical price line + dashed forecast projection with shaded confidence band

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI (Python 3.11), SQLite |
| Forecasting | [TimesFM 1.0 200M](https://github.com/google-research/timesfm) — PyTorch, CPU |
| AI Analysis | Claude Sonnet (`claude-sonnet-4-6`) via Anthropic API |
| Price Data | Polymarket Gamma API + CLOB API |
| Deploy | Railway (backend) + Vercel (frontend) |

---

## How the forecast works

TimesFM is a **foundation model for time series** — trained by Google on a large corpus of real-world time series data. It does zero-shot forecasting: you feed it a sequence of historical prices and it predicts future values without any fine-tuning on Polymarket data.

The model receives up to 30 days of hourly YES prices (0–1 scale) and outputs:
- A point forecast at the chosen horizon (24h / 48h / 72h)
- 0.1 and 0.9 quantiles — the 80% confidence interval

The **divergence** between the forecast price and the current market price drives the signal:

| Divergence | Signal |
|---|---|
| > +20% | STRONG BUY |
| +10% to +20% | BUY |
| -10% to +10% | HOLD |
| -20% to -10% | SELL |
| < -20% | STRONG SELL |

---

## How the AI report works

After TimesFM runs, Claude receives:
- The market question and outcome being tracked
- Close date, 24h volume, liquidity
- Current Polymarket price (market-implied probability)
- TimesFM forecast price and divergence

Claude returns a structured JSON report with:
- Plain-English summary of what the market resolves on
- Exact resolution criteria (YES vs NO conditions)
- 4 key factors that will determine the outcome
- Its own probability estimate vs the current market price
- Where it sees mispricing and why
- A single action recommendation: `BUY YES`, `BUY NO`, `SELL YES`, `SELL NO`, or `HOLD`
- 2–3 sentences of direct reasoning

TimesFM provides the quantitative signal. Claude provides the qualitative reasoning. Neither is useful alone.

---

## Project structure

```
polymarket-webapp/
├── backend/
│   ├── main.py          # FastAPI app — 5 endpoints
│   ├── parser.py        # URL parsing (all Polymarket formats)
│   ├── fetch.py         # Price history (Gamma API primary, CLOB fallback)
│   ├── forecast.py      # TimesFM inference
│   ├── report.py        # Claude AI report generation
│   ├── signals.py       # Divergence + signal classification
│   ├── config.py        # Thresholds and constants
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Home — URL input
│   │   ├── m/[id]/
│   │   │   ├── page.tsx         # Server component — fetches market data
│   │   │   ├── MarketView.tsx   # Client component — chart, signal, report
│   │   │   └── layout.tsx       # OG meta tags per market
│   │   └── api/og/[id]/route.tsx  # Edge OG image generation
│   ├── components/
│   │   ├── UrlInput.tsx         # Home page input + analyze button
│   │   ├── SignalCard.tsx       # Signal badge + price display
│   │   ├── ForecastChart.tsx    # Recharts chart (history + forecast + CI)
│   │   ├── AIReport.tsx         # Structured AI analysis panel
│   │   ├── HorizonToggle.tsx    # 24h / 48h / 72h selector
│   │   └── ShareButton.tsx      # Copy link
│   └── lib/
│       └── api.ts               # API client + types
├── railway.json
└── vercel.json
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/analyze` | Parse URL → return condition_id |
| `GET` | `/market/{id}?horizon=48` | Full forecast + AI report |
| `GET` | `/market/{id}/refresh` | Force-refresh (clears cache) |
| `GET` | `/recent` | Last 20 analyzed markets |
| `GET` | `/health` | Health check |

---

## Local development

**Backend**
```bash
cd backend
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

---

## Environment variables

| Variable | Where | Required | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Railway | Yes (for reports) | Claude API key |
| `NEXT_PUBLIC_API_URL` | Vercel | Yes | Backend URL, e.g. `https://your-app.railway.app` |
| `NEXT_PUBLIC_APP_URL` | Vercel | For OG images | Frontend URL, e.g. `https://scanner.polyweb.pro` |

The AI report section is silently omitted if `ANTHROPIC_API_KEY` is missing — the forecast chart and signal still work.
