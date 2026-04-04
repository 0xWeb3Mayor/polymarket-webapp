'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Trade, AgentStatus, closeTrade, getTrades, pnlColor } from '@/lib/api'
import { TradeCard } from '@/components/TradeCard'

interface Props {
  initial: Trade[]
  agentStatus: AgentStatus
}

export default function TradesView({ initial, agentStatus }: Props) {
  const router = useRouter()
  const [trades, setTrades] = useState<Trade[]>(initial)
  const [status] = useState<AgentStatus>(agentStatus)
  const [closing, setClosing] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await getTrades()
      setTrades(data)
    } finally {
      setRefreshing(false)
    }
  }, [])

  const handleClose = useCallback(async (conditionId: string) => {
    setClosing(conditionId)
    try {
      await closeTrade(conditionId)
      await refresh()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to close trade')
    } finally {
      setClosing(null)
    }
  }, [refresh])

  const openTrades = trades.filter(t => t.closed_at === null)
  const closedTrades = trades.filter(t => t.closed_at !== null)

  // Aggregate stats
  const pnlValues = trades.filter(t => t.pnl_pct !== null).map(t => t.pnl_pct!)
  const avgPnl = pnlValues.length > 0
    ? pnlValues.reduce((a, b) => a + b, 0) / pnlValues.length
    : null
  const totalDeployed = openTrades.reduce((a, t) => a + t.size_usd, 0)

  return (
    <main className="min-h-screen px-4 py-8 max-w-3xl mx-auto space-y-8">
      {/* Nav */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => router.push('/')}
          className="text-[#475569] hover:text-[#94a3b8] text-sm transition-colors font-mono"
        >
          ← scanner
        </button>
        <div className="flex items-center gap-2">
          <span
            className={`w-1.5 h-1.5 rounded-full ${status.running ? 'bg-[#22c55e] animate-pulse' : 'bg-[#475569]'}`}
          />
          <span className="text-[#475569] text-xs font-mono">
            {status.running ? 'agent running' : 'agent idle'}
          </span>
          {status.live ? (
            <span className="font-mono text-[10px] text-[#ef4444] border border-[#ef4444]/30 rounded px-1.5 py-0.5 uppercase tracking-widest">
              live
            </span>
          ) : (
            <span className="font-mono text-[10px] text-[#475569] border border-[#334155] rounded px-1.5 py-0.5 uppercase tracking-widest">
              paper
            </span>
          )}
        </div>
      </div>

      {/* Header */}
      <div>
        <h1 className="font-mono text-xl font-bold text-[#f1f5f9] tracking-tight mb-1">
          polyagent trades
        </h1>
        <p className="font-mono text-xs text-[#475569]">
          {status.wallet} · max ${status.max_trade_usd}/trade · ${status.daily_limit_usd}/day
        </p>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-4">
          <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">Open</div>
          <div className="font-mono text-2xl font-bold text-[#f1f5f9]">{openTrades.length}</div>
        </div>
        <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-4">
          <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">Deployed</div>
          <div className="font-mono text-2xl font-bold text-[#f1f5f9]">${totalDeployed.toFixed(0)}</div>
        </div>
        <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-4">
          <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">Avg P&L</div>
          <div
            className="font-mono text-2xl font-bold"
            style={{ color: pnlColor(avgPnl) }}
          >
            {avgPnl !== null ? `${avgPnl > 0 ? '+' : ''}${avgPnl.toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      {/* Refresh */}
      <div className="flex justify-end">
        <button
          onClick={refresh}
          disabled={refreshing}
          className="font-mono text-[10px] text-[#475569] hover:text-[#94a3b8] transition-colors tracking-widest uppercase disabled:opacity-40"
        >
          {refreshing ? 'refreshing...' : '↻ refresh'}
        </button>
      </div>

      {/* Open positions */}
      {openTrades.length > 0 && (
        <section className="space-y-3">
          <div className="font-mono text-xs text-[#475569] tracking-widest uppercase">
            open positions ({openTrades.length})
          </div>
          {openTrades.map(trade => (
            <div key={trade.id} className={closing === trade.condition_id ? 'opacity-50 pointer-events-none' : ''}>
              <TradeCard
                trade={trade}
                onClose={handleClose}
              />
            </div>
          ))}
        </section>
      )}

      {/* Closed trades */}
      {closedTrades.length > 0 && (
        <section className="space-y-3">
          <div className="font-mono text-xs text-[#475569] tracking-widest uppercase">
            history ({closedTrades.length})
          </div>
          {closedTrades.map(trade => (
            <TradeCard key={trade.id} trade={trade} />
          ))}
        </section>
      )}

      {/* Empty state */}
      {trades.length === 0 && (
        <div className="text-center py-20">
          <div className="font-mono text-[#475569] text-sm mb-2">no trades yet</div>
          <div className="font-mono text-[#334155] text-xs">
            agent scans every hour — strong signals trigger automatic execution
          </div>
        </div>
      )}
    </main>
  )
}
