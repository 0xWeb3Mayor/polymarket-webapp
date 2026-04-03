const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type Signal = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL'

export interface PricePoint {
  timestamp: number
  price: number
}

export interface Forecast {
  forecast_price: number
  ci_80_low: number
  ci_80_high: number
  horizon_hours: number
  divergence_pct: number
  signal: Signal
  run_at: number
}

export interface MarketResult {
  condition_id: string
  question: string
  last_price: number
  close_time: number
  volume_24h: number
  liquidity: number
  forecast: Forecast
  price_history: PricePoint[]
}

export interface AnalyzeResponse {
  condition_id: string
  redirect: string
}

export async function analyzeUrl(url: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Failed to analyze URL')
  }
  return res.json()
}

export async function getMarket(
  conditionId: string,
  horizon: number = 48
): Promise<MarketResult> {
  const res = await fetch(
    `${API_URL}/market/${conditionId}?horizon=${horizon}`,
    { cache: 'no-store' }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Market not found')
  }
  return res.json()
}

export function signalColor(signal: Signal): string {
  const map: Record<Signal, string> = {
    STRONG_BUY: '#22c55e',
    BUY: '#86efac',
    HOLD: '#94a3b8',
    SELL: '#f97316',
    STRONG_SELL: '#ef4444',
  }
  return map[signal]
}

export function signalLabel(signal: Signal): string {
  return signal.replace('_', ' ')
}

export function formatPrice(price: number): string {
  return `${(price * 100).toFixed(0)}¢`
}

export function formatDivergence(pct: number): string {
  return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`
}

export interface ChartPoint {
  timestamp: number
  historical?: number
  forecast?: number
  ci_low?: number
  ci_high?: number
}

export function buildChartData(
  history: PricePoint[],
  forecast: Forecast,
  lastPrice: number
): ChartPoint[] {
  const nowTs = Math.floor(Date.now() / 1000)
  const horizonTs = nowTs + forecast.horizon_hours * 3600

  const historicalPoints: ChartPoint[] = history.map((p) => ({
    timestamp: p.timestamp,
    historical: p.price,
  }))

  const steps = 12
  const forecastPoints: ChartPoint[] = Array.from({ length: steps + 1 }, (_, i) => {
    const progress = i / steps
    return {
      timestamp: Math.round(nowTs + progress * (horizonTs - nowTs)),
      forecast: lastPrice + progress * (forecast.forecast_price - lastPrice),
      ci_low: lastPrice + progress * (forecast.ci_80_low - lastPrice),
      ci_high: lastPrice + progress * (forecast.ci_80_high - lastPrice),
    }
  })

  return [...historicalPoints, ...forecastPoints]
}
