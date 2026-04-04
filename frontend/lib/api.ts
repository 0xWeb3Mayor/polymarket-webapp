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

export interface AIReport {
  what_it_asks: string
  resolution_criteria: string
  key_factors: string[]
  probability_yes: number
  probability_no: number
  vs_market: string
  mispricing: string
  action: string
  reasoning: string
}

export interface MarketResult {
  condition_id: string
  question: string
  outcome: string
  last_price: number
  close_time: number
  volume_24h: number
  liquidity: number
  forecast: Forecast
  price_history: PricePoint[]
  report: AIReport | null
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

// ── Trade types ───────────────────────────────────────────────────────────────

export interface Trade {
  id: number
  condition_id: string
  question: string
  side: 'YES' | 'NO'
  entry_price: number
  size_usd: number
  signal: Signal
  tx_hash: string | null
  executed_at: number
  closed_at: number | null
  exit_price: number | null
  ows_wallet: string
  paper_trade: number   // 1 = paper, 0 = live
  current_price: number | null
  pnl_pct: number | null
  polygonscan_url: string | null
  report?: AIReport | null
}

export interface AgentStatus {
  running: boolean
  live: boolean
  wallet: string
  max_trade_usd: number
  daily_limit_usd: number
}

export async function getTrades(): Promise<Trade[]> {
  const res = await fetch(`${API_URL}/trades`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Failed to fetch trades')
  return res.json()
}

export async function getTrade(conditionId: string): Promise<Trade> {
  const res = await fetch(`${API_URL}/trades/${conditionId}`, { cache: 'no-store' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Trade not found')
  }
  return res.json()
}

export async function closeTrade(conditionId: string): Promise<Trade> {
  const res = await fetch(`${API_URL}/trades/${conditionId}/close`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Failed to close trade')
  }
  return res.json()
}

export async function getAgentStatus(): Promise<AgentStatus> {
  const res = await fetch(`${API_URL}/agent/status`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Failed to get agent status')
  return res.json()
}

export async function startAgent(): Promise<{ status: string }> {
  const res = await fetch(`${API_URL}/agent/start`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to start agent')
  return res.json()
}

export async function stopAgent(): Promise<{ status: string }> {
  const res = await fetch(`${API_URL}/agent/stop`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to stop agent')
  return res.json()
}

export interface AgentLog {
  id: number
  ts: number
  level: 'INFO' | 'SIGNAL' | 'GATE' | 'TRADE' | 'ERROR'
  event: string
  condition_id: string | null
  detail: string | null
}

export async function getAgentLogs(limit = 100): Promise<AgentLog[]> {
  const res = await fetch(`${API_URL}/agent/logs?limit=${limit}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Failed to fetch agent logs')
  return res.json()
}

export function pnlColor(pnl: number | null): string {
  if (pnl === null) return '#94a3b8'
  if (pnl > 5) return '#22c55e'
  if (pnl > 0) return '#86efac'
  if (pnl < -5) return '#ef4444'
  if (pnl < 0) return '#f97316'
  return '#94a3b8'
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
