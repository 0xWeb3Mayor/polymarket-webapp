'use client'

import Link from 'next/link'
import { Trade, signalColor, signalLabel, pnlColor } from '@/lib/api'

interface Props {
  trade: Trade
  onClose?: (conditionId: string) => void
}

function formatPrice(p: number | null): string {
  if (p === null) return '—'
  return `${(p * 100).toFixed(0)}¢`
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function TradeCard({ trade, onClose }: Props) {
  const sigColor = signalColor(trade.signal)
  const sigLabel = signalLabel(trade.signal)
  const pColor = pnlColor(trade.pnl_pct)
  const isOpen = trade.closed_at === null
  const isPaper = trade.paper_trade === 1

  return (
    <div className="w-full bg-[#111318] border border-[#1a1a2e] rounded-lg p-5 space-y-4">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5 flex-1 min-w-0">
          {/* Badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="inline-block border rounded px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest uppercase"
              style={{ borderColor: sigColor, color: sigColor }}
            >
              {sigLabel}
            </span>
            <span
              className="inline-block border rounded px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest uppercase"
              style={{
                borderColor: trade.side === 'YES' ? '#22c55e' : '#f97316',
                color: trade.side === 'YES' ? '#22c55e' : '#f97316',
              }}
            >
              BUY {trade.side}
            </span>
            <span className={`inline-block border rounded px-2 py-0.5 font-mono text-[10px] tracking-widest uppercase ${
              isPaper
                ? 'border-[#334155] text-[#475569]'
                : 'border-[#22c55e]/30 text-[#22c55e]'
            }`}>
              mainnet
            </span>
            {isOpen ? (
              <span className="inline-flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
                <span className="font-mono text-[10px] text-[#22c55e] tracking-widest uppercase">open</span>
              </span>
            ) : (
              <span className="font-mono text-[10px] text-[#475569] tracking-widest uppercase">closed</span>
            )}
          </div>
          {/* Question */}
          <Link
            href={`/m/${trade.condition_id}`}
            className="font-mono text-sm text-[#94a3b8] hover:text-[#f1f5f9] transition-colors leading-relaxed line-clamp-2"
          >
            {trade.question}
          </Link>
        </div>

        {/* P&L */}
        <div className="text-right shrink-0">
          <div className="font-mono text-xs text-[#475569] tracking-widest uppercase mb-0.5">P&L</div>
          <div
            className="font-mono text-xl font-bold"
            style={{ color: pColor }}
          >
            {trade.pnl_pct !== null ? `${trade.pnl_pct > 0 ? '+' : ''}${trade.pnl_pct.toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      {/* Price row */}
      <div className="flex items-baseline gap-6 font-mono">
        <div>
          <div className="text-[10px] text-[#475569] tracking-widest uppercase mb-0.5">Entry</div>
          <div className="text-lg font-bold text-[#f1f5f9]">{formatPrice(trade.entry_price)}</div>
        </div>
        <div className="text-[#475569] self-center">→</div>
        <div>
          <div className="text-[10px] text-[#475569] tracking-widest uppercase mb-0.5">Current</div>
          <div
            className="text-lg font-bold"
            style={{ color: pColor }}
          >
            {formatPrice(trade.current_price)}
          </div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-[10px] text-[#475569] tracking-widest uppercase mb-0.5">Size</div>
          <div className="text-sm text-[#94a3b8]">${trade.size_usd}</div>
        </div>
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between border-t border-[#1a1a2e] pt-3 gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="font-mono text-[10px] text-[#475569]">
            {formatDate(trade.executed_at)}
          </span>
          {trade.tx_hash && (
            <a
              href={trade.polygonscan_url ?? '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-[10px] text-[#475569] hover:text-[#94a3b8] transition-colors"
            >
              {trade.tx_hash.slice(0, 10)}...↗
            </a>
          )}
          <span className="font-mono text-[10px] text-[#334155]">
            {trade.ows_wallet}
          </span>
        </div>

        {isOpen && onClose && (
          <button
            onClick={() => onClose(trade.condition_id)}
            className="font-mono text-[10px] text-[#ef4444] border border-[#ef4444]/30 rounded px-2 py-1 hover:border-[#ef4444] transition-colors uppercase tracking-widest"
          >
            close
          </button>
        )}
      </div>
    </div>
  )
}
