import { ImageResponse } from '@vercel/og'
import { NextRequest } from 'next/server'

export const runtime = 'edge'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const SIGNAL_COLORS: Record<string, string> = {
  STRONG_BUY: '#22c55e',
  BUY: '#86efac',
  HOLD: '#94a3b8',
  SELL: '#f97316',
  STRONG_SELL: '#ef4444',
}

interface RouteParams {
  params: Promise<{ id: string }>
}

export async function GET(req: NextRequest, { params }: RouteParams) {
  const { id } = await params

  let market: {
    question: string
    last_price: number
    forecast: {
      forecast_price: number
      divergence_pct: number
      signal: string
      horizon_hours: number
    }
  } | null = null

  try {
    const res = await fetch(`${API_URL}/market/${id}`, { cache: 'no-store' })
    if (res.ok) market = await res.json()
  } catch {
    // render fallback below
  }

  const signal = market?.forecast?.signal ?? 'HOLD'
  const color = SIGNAL_COLORS[signal] ?? '#94a3b8'
  const question = market?.question ?? 'Polymarket Signal'
  const current = market ? `${(market.last_price * 100).toFixed(0)}¢` : '—'
  const forecast = market ? `${(market.forecast.forecast_price * 100).toFixed(0)}¢` : '—'
  const edge = market
    ? `${market.forecast.divergence_pct > 0 ? '+' : ''}${market.forecast.divergence_pct.toFixed(1)}%`
    : '—'
  const label = signal.replace('_', ' ')

  return new ImageResponse(
    (
      <div
        style={{
          background: '#0a0a0a',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          padding: '48px',
          fontFamily: 'monospace',
          justifyContent: 'space-between',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: '#22c55e',
            }}
          />
          <span style={{ color: '#475569', fontSize: '14px', letterSpacing: '3px' }}>
            POLYMARKET SCANNER
          </span>
        </div>

        {/* Signal + Question */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            style={{
              display: 'inline-flex',
              border: `1px solid ${color}`,
              borderRadius: '4px',
              padding: '4px 12px',
              color,
              fontSize: '13px',
              letterSpacing: '3px',
              fontWeight: 700,
              width: 'fit-content',
            }}
          >
            {label}
          </div>
          <div
            style={{
              color: '#f1f5f9',
              fontSize: '28px',
              lineHeight: '1.4',
              maxWidth: '800px',
            }}
          >
            {question}
          </div>
        </div>

        {/* Price row */}
        <div style={{ display: 'flex', gap: '48px', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ color: '#475569', fontSize: '11px', letterSpacing: '2px' }}>
              CURRENT
            </span>
            <span style={{ color: '#f1f5f9', fontSize: '40px', fontWeight: 700 }}>{current}</span>
          </div>
          <span style={{ color: '#475569', fontSize: '32px', paddingBottom: '8px' }}>→</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ color, fontSize: '11px', letterSpacing: '2px' }}>FORECAST</span>
            <span style={{ color, fontSize: '40px', fontWeight: 700 }}>{forecast}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ color, fontSize: '11px', letterSpacing: '2px' }}>EDGE</span>
            <span style={{ color, fontSize: '40px', fontWeight: 700 }}>{edge}</span>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    }
  )
}
