'use client'

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Trade, AgentStatus, AgentLog, WalletBalance,
  closeTrade, getTrades, getAgentStatus,
  startAgent, stopAgent, setAgentMode, getAgentLogs, getWalletBalance,
  pnlColor,
} from '@/lib/api'
import { TradeCard } from '@/components/TradeCard'

interface Props {
  initial: Trade[]
  agentStatus: AgentStatus
  initialLogs: AgentLog[]
  initialBalance: WalletBalance
}

const LOG_COLORS: Record<string, string> = {
  INFO:   '#475569',
  SIGNAL: '#22c55e',
  GATE:   '#f97316',
  TRADE:  '#3b82f6',
  ERROR:  '#ef4444',
}

const LOG_ICONS: Record<string, string> = {
  INFO:   '·',
  SIGNAL: '↑',
  GATE:   '⊘',
  TRADE:  '✓',
  ERROR:  '!',
}

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })
}

function shortAddr(addr: string | null): string {
  if (!addr) return '—'
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`
}

export default function TradesView({ initial, agentStatus: initialStatus, initialLogs, initialBalance }: Props) {
  const router = useRouter()
  const [trades, setTrades] = useState<Trade[]>(initial)
  const [status, setStatus] = useState<AgentStatus>(initialStatus)
  const [logs, setLogs] = useState<AgentLog[]>(initialLogs)
  const [balance, setBalance] = useState<WalletBalance>(initialBalance)
  const [closing, setClosing] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [agentLoading, setAgentLoading] = useState(false)
  const [modeLoading, setModeLoading] = useState(false)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      const [t, s, l, b] = await Promise.all([
        getTrades().catch(() => trades),
        getAgentStatus().catch(() => status),
        getAgentLogs(100).catch(() => logs),
        getWalletBalance().catch(() => balance),
      ])
      setTrades(t)
      setStatus(s)
      setLogs(l)
      setBalance(b)
    } finally {
      setRefreshing(false)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!status.running) return
    const id = setInterval(refresh, 15_000)
    return () => clearInterval(id)
  }, [status.running, refresh])

  const handleModeToggle = useCallback(async () => {
    setModeLoading(true)
    try {
      await setAgentMode(!status.live)
      const s = await getAgentStatus()
      setStatus(s)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to toggle mode')
    } finally {
      setModeLoading(false)
    }
  }, [status.live])

  const handleAgentToggle = useCallback(async () => {
    setAgentLoading(true)
    try {
      if (status.running) {
        await stopAgent()
      } else {
        await startAgent()
      }
      const s = await getAgentStatus()
      setStatus(s)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to toggle agent')
    } finally {
      setAgentLoading(false)
    }
  }, [status.running])

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

  const openTrades    = trades.filter(t => t.closed_at === null)
  const closedTrades  = trades.filter(t => t.closed_at !== null)
  const pnlValues     = trades.filter(t => t.pnl_pct !== null).map(t => t.pnl_pct!)
  const avgPnl        = pnlValues.length > 0
    ? pnlValues.reduce((a, b) => a + b, 0) / pnlValues.length
    : null
  const totalDeployed = openTrades.reduce((a, t) => a + t.size_usd, 0)

  // Polygon USDC is what Polymarket settles on
  const polyUsdc    = (balance.usdc ?? 0) + (balance.usdc_e ?? 0)
  const polyColor   = polyUsdc > 0 ? '#22c55e' : '#475569'

  return (
    <main className="min-h-screen px-3 sm:px-6 py-6 max-w-3xl mx-auto space-y-6">

      {/* Nav — logo left, controls right */}
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => router.push('/')}
          className="text-[#475569] hover:text-[#94a3b8] text-sm transition-colors font-mono shrink-0"
        >
          ← scanner
        </button>

        {/* Right side: status + mode toggle + start/stop */}
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <div className="flex items-center gap-2">
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${status.running ? 'bg-[#22c55e] animate-pulse' : 'bg-[#475569]'}`} />
            <span className="text-[#475569] text-xs font-mono hidden sm:inline">
              {status.running ? 'agent running' : 'agent idle'}
            </span>
          </div>

          {/* LIVE / PAPER toggle */}
          <button
            onClick={handleModeToggle}
            disabled={modeLoading}
            title={status.live ? 'Click to switch to paper mode' : 'Click to switch to live trading'}
            className={`font-mono text-[10px] px-2.5 py-1 rounded border transition-colors tracking-widest uppercase disabled:opacity-40 ${
              status.live
                ? 'border-[#22c55e] text-[#22c55e] bg-[#22c55e]/10 hover:bg-[#22c55e]/20'
                : 'border-[#475569] text-[#475569] hover:border-[#94a3b8] hover:text-[#94a3b8]'
            }`}
          >
            {modeLoading ? '···' : status.live ? '● live' : '○ paper'}
          </button>

          {/* Start / Stop */}
          <button
            onClick={handleAgentToggle}
            disabled={agentLoading}
            className={`font-mono text-xs px-3 py-1.5 rounded border transition-colors tracking-widest uppercase disabled:opacity-40 ${
              status.running
                ? 'border-[#ef4444]/50 text-[#ef4444] hover:border-[#ef4444]'
                : 'border-[#22c55e]/50 text-[#22c55e] hover:border-[#22c55e]'
            }`}
          >
            {agentLoading ? '···' : status.running ? 'stop' : 'start'}
          </button>
        </div>
      </div>

      {/* Header */}
      <div>
        <h1 className="font-mono text-lg sm:text-xl font-bold text-[#f1f5f9] tracking-tight mb-1">
          polyagent trades
        </h1>
        <p className="font-mono text-xs text-[#475569]">
          {status.wallet} · max ${status.max_trade_usd}/trade · ${status.daily_limit_usd}/day
        </p>
      </div>

      {/* Wallet balance — Polygon prominently, others secondary */}
      <div className="bg-[#0d0d10] border border-[#1a1a2e] rounded-lg p-4 space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1 min-w-0">
            <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase">
              wallet · polygon (tradeable)
            </div>
            {balance.address ? (
              <a
                href={`https://polygonscan.com/address/${balance.address}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs text-[#334155] hover:text-[#475569] transition-colors block truncate"
              >
                {shortAddr(balance.address)} ↗
              </a>
            ) : (
              <div className="font-mono text-xs text-[#334155]">—</div>
            )}
          </div>
          <div className="text-right shrink-0">
            <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">
              USDC · polygon
            </div>
            <div className="font-mono text-2xl sm:text-3xl font-bold" style={{ color: polyColor }}>
              ${polyUsdc.toFixed(2)}
            </div>
            {balance.usdc_e !== null && balance.usdc_e > 0 && (
              <div className="font-mono text-[10px] text-[#475569] mt-0.5">
                native ${balance.usdc?.toFixed(2)} · bridged ${balance.usdc_e?.toFixed(2)}
              </div>
            )}
            {polyUsdc === 0 && balance.address && (
              <div className="font-mono text-[10px] text-[#f97316] mt-0.5">
                fund with USDC on Polygon to trade
              </div>
            )}
          </div>
        </div>

        {/* Other chains — collapsed secondary info */}
        {balance.chains && Object.keys(balance.chains).length > 0 && (
          <div className="grid grid-cols-3 gap-2 border-t border-[#1a1a2e] pt-3">
            {(['ethereum', 'base', 'polygon'] as const).map(chain => {
              const c = balance.chains?.[chain]
              if (!c) return null
              const total = (c.usdc ?? 0) + (c.usdc_e ?? 0)
              const explorer = chain === 'polygon'
                ? `https://polygonscan.com/address/${balance.address}`
                : chain === 'base'
                ? `https://basescan.org/address/${balance.address}`
                : `https://etherscan.io/address/${balance.address}`
              const label = chain === 'ethereum' ? 'eth' : chain
              return (
                <a
                  key={chain}
                  href={explorer}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-[#111318] border border-[#1a1a2e] rounded p-2 hover:border-[#334155] transition-colors"
                >
                  <div className="font-mono text-[9px] text-[#334155] tracking-widest uppercase mb-1">{label} ↗</div>
                  <div className={`font-mono text-sm font-bold ${total > 0 ? 'text-[#f1f5f9]' : 'text-[#334155]'}`}>
                    ${total.toFixed(2)}
                  </div>
                  {c.native > 0 && (
                    <div className="font-mono text-[9px] text-[#334155] mt-0.5">
                      {c.native.toFixed(4)} {c.native_symbol}
                    </div>
                  )}
                </a>
              )
            })}
          </div>
        )}

        {balance.address === null && (
          <div className="font-mono text-[10px] text-[#475569] border-t border-[#1a1a2e] pt-3">
            set OWS_WALLET_ADDRESS in Railway to see balance
          </div>
        )}
        {balance.error && balance.address !== null && (
          <div className="font-mono text-[10px] text-[#f97316] border-t border-[#1a1a2e] pt-3">
            RPC error · {balance.error.slice(0, 100)}
          </div>
        )}
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-3 sm:p-4">
          <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">Open</div>
          <div className="font-mono text-xl sm:text-2xl font-bold text-[#f1f5f9]">{openTrades.length}</div>
        </div>
        <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-3 sm:p-4">
          <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">Deployed</div>
          <div className="font-mono text-xl sm:text-2xl font-bold text-[#f1f5f9]">${totalDeployed.toFixed(0)}</div>
        </div>
        <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-3 sm:p-4">
          <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">Avg P&L</div>
          <div className="font-mono text-xl sm:text-2xl font-bold" style={{ color: pnlColor(avgPnl) }}>
            {avgPnl !== null ? `${avgPnl > 0 ? '+' : ''}${avgPnl.toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      {/* Agent activity log */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="font-mono text-xs text-[#475569] tracking-widest uppercase">
            agent activity
          </div>
          <button
            onClick={refresh}
            disabled={refreshing}
            className="font-mono text-[10px] text-[#475569] hover:text-[#94a3b8] transition-colors tracking-widest uppercase disabled:opacity-40"
          >
            {refreshing ? 'refreshing...' : '↻ refresh'}
          </button>
        </div>

        <div className="bg-[#0d0d10] border border-[#1a1a2e] rounded-lg p-3 sm:p-4 space-y-1.5 max-h-64 overflow-y-auto font-mono text-[10px] sm:text-[11px]">
          {logs.length === 0 ? (
            <div className="text-[#334155] text-center py-4">
              no activity yet — agent starts automatically on deploy
            </div>
          ) : (
            logs.map(log => (
              <div key={log.id} className="flex items-start gap-2 min-w-0">
                <span className="text-[#334155] shrink-0">{formatTs(log.ts)}</span>
                <span className="shrink-0 font-bold w-3 text-center" style={{ color: LOG_COLORS[log.level] ?? '#475569' }}>
                  {LOG_ICONS[log.level] ?? '·'}
                </span>
                <span className="shrink-0" style={{ color: LOG_COLORS[log.level] ?? '#475569' }}>{log.event}</span>
                {log.condition_id && (
                  <span className="text-[#334155] shrink-0 hidden sm:inline">{log.condition_id.slice(0, 10)}…</span>
                )}
                {log.detail && (
                  <span className="text-[#475569] truncate min-w-0">{log.detail}</span>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      {/* Open positions */}
      {openTrades.length > 0 && (
        <section className="space-y-3">
          <div className="font-mono text-xs text-[#475569] tracking-widest uppercase">
            open positions ({openTrades.length})
          </div>
          {openTrades.map(trade => (
            <div key={trade.id} className={closing === trade.condition_id ? 'opacity-50 pointer-events-none' : ''}>
              <TradeCard trade={trade} onClose={handleClose} />
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
        <div className="text-center py-12">
          <div className="font-mono text-[#475569] text-sm mb-2">no trades yet</div>
          <div className="font-mono text-[#334155] text-xs">
            {status.running
              ? 'scanning geopolitics markets — trades appear when strong signals pass the gate'
              : 'click start above to begin scanning'}
          </div>
        </div>
      )}

    </main>
  )
}
