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

  let trade: {
    question: string
    side: string
    entry_price: number
    current_price: number | null
    pnl_pct: number | null
    signal: string
    tx_hash: string | null
    paper_trade: number
  } | null = null

  try {
    const res = await fetch(`${API_URL}/trades/${id}`, { cache: 'no-store' })
    if (res.ok) trade = await res.json()
  } catch {
    // render fallback
  }

  const signal = trade?.signal ?? 'STRONG_BUY'
  const sigColor = SIGNAL_COLORS[signal] ?? '#22c55e'
  const sigLabel = signal.replace('_', ' ')
  const question = trade?.question ?? 'Polymarket Trade'
  const side = trade?.side ?? 'YES'
  const sideColor = side === 'YES' ? '#22c55e' : '#f97316'

  const entry = trade ? `${(trade.entry_price * 100).toFixed(0)}¢` : '—'
  const current = trade?.current_price != null
    ? `${(trade.current_price * 100).toFixed(0)}¢`
    : '—'

  const pnl = trade?.pnl_pct != null
    ? `${trade.pnl_pct > 0 ? '+' : ''}${trade.pnl_pct.toFixed(1)}%`
    : '—'
  const pnlColor = trade?.pnl_pct != null
    ? (trade.pnl_pct >= 0 ? '#22c55e' : '#ef4444')
    : '#94a3b8'

  const isPaper = trade?.paper_trade !== 0
  const modeLabel = isPaper ? 'PAPER' : 'LIVE'

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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#22c55e' }} />
            <span style={{ color: '#475569', fontSize: '13px', letterSpacing: '3px' }}>
              POLYAGENT
            </span>
          </div>
          <span style={{
            color: isPaper ? '#475569' : '#ef4444',
            fontSize: '11px',
            letterSpacing: '2px',
            border: `1px solid ${isPaper ? '#334155' : '#ef4444'}`,
            borderRadius: '4px',
            padding: '2px 8px',
          }}>
            {modeLabel}
          </span>
        </div>

        {/* Signal + Side + Question */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <div style={{
              display: 'inline-flex',
              border: `1px solid ${sigColor}`,
              borderRadius: '4px',
              padding: '3px 10px',
              color: sigColor,
              fontSize: '11px',
              letterSpacing: '3px',
              fontWeight: 700,
            }}>
              {sigLabel}
            </div>
            <div style={{
              display: 'inline-flex',
              border: `1px solid ${sideColor}`,
              borderRadius: '4px',
              padding: '3px 10px',
              color: sideColor,
              fontSize: '11px',
              letterSpacing: '3px',
              fontWeight: 700,
            }}>
              BUY {side}
            </div>
          </div>
          <div style={{ color: '#f1f5f9', fontSize: '26px', lineHeight: '1.4', maxWidth: '800px' }}>
            {question}
          </div>
        </div>

        {/* Price + P&L row */}
        <div style={{ display: 'flex', gap: '48px', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ color: '#475569', fontSize: '10px', letterSpacing: '2px' }}>ENTRY</span>
            <span style={{ color: '#f1f5f9', fontSize: '38px', fontWeight: 700 }}>{entry}</span>
          </div>
          <span style={{ color: '#475569', fontSize: '28px', paddingBottom: '6px' }}>→</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ color: '#475569', fontSize: '10px', letterSpacing: '2px' }}>CURRENT</span>
            <span style={{ color: '#f1f5f9', fontSize: '38px', fontWeight: 700 }}>{current}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginLeft: 'auto' }}>
            <span style={{ color: pnlColor, fontSize: '10px', letterSpacing: '2px' }}>P&L</span>
            <span style={{ color: pnlColor, fontSize: '38px', fontWeight: 700 }}>{pnl}</span>
          </div>
        </div>
      </div>
    ),
    { width: 1200, height: 630 }
  )
}
