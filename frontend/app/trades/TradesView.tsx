'use client'

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Trade, AgentStatus, AgentLog, WalletBalance,
  closeTrade, getTrades, getAgentStatus,
  startAgent, stopAgent, getAgentLogs, getWalletBalance,
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

  // Poll every 15s while agent is running
  useEffect(() => {
    if (!status.running) return
    const id = setInterval(refresh, 15_000)
    return () => clearInterval(id)
  }, [status.running, refresh])

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

  const openTrades = trades.filter(t => t.closed_at === null)
  const closedTrades = trades.filter(t => t.closed_at !== null)
  const pnlValues = trades.filter(t => t.pnl_pct !== null).map(t => t.pnl_pct!)
  const avgPnl = pnlValues.length > 0
    ? pnlValues.reduce((a, b) => a + b, 0) / pnlValues.length
    : null
  const totalDeployed = openTrades.reduce((a, t) => a + t.size_usd, 0)

  const balanceColor = balance.total !== null
    ? (balance.total > 0 ? '#22c55e' : '#475569')
    : '#475569'

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
        <div className="flex items-center gap-3">
          <span className={`w-1.5 h-1.5 rounded-full ${status.running ? 'bg-[#22c55e] animate-pulse' : 'bg-[#475569]'}`} />
          <span className="text-[#475569] text-xs font-mono">
            {status.running ? 'agent running' : 'agent idle'}
          </span>
          <span className={`font-mono text-[10px] border rounded px-1.5 py-0.5 uppercase tracking-widest ${
            status.live ? 'text-[#22c55e] border-[#22c55e]/30' : 'text-[#475569] border-[#334155]'
          }`}>
            mainnet
          </span>
        </div>
      </div>

      {/* Header + Start/Stop */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-mono text-xl font-bold text-[#f1f5f9] tracking-tight mb-1">
            polyagent trades
          </h1>
          <p className="font-mono text-xs text-[#475569]">
            {status.wallet} · max ${status.max_trade_usd}/trade · ${status.daily_limit_usd}/day
          </p>
        </div>
        <button
          onClick={handleAgentToggle}
          disabled={agentLoading}
          className={`font-mono text-xs px-4 py-2 rounded border transition-colors tracking-widest uppercase disabled:opacity-40 shrink-0 ${
            status.running
              ? 'border-[#ef4444]/50 text-[#ef4444] hover:border-[#ef4444]'
              : 'border-[#22c55e]/50 text-[#22c55e] hover:border-[#22c55e]'
          }`}
        >
          {agentLoading ? '...' : status.running ? 'stop agent' : 'start agent'}
        </button>
      </div>

      {/* Wallet balance */}
      <div className="bg-[#0d0d10] border border-[#1a1a2e] rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase">
              wallet · all chains
            </div>
            {balance.address ? (
              <a
                href={`https://polygonscan.com/address/${balance.address}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs text-[#334155] hover:text-[#475569] transition-colors"
              >
                {shortAddr(balance.address)} ↗
              </a>
            ) : (
              <div className="font-mono text-xs text-[#334155]">—</div>
            )}
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] text-[#475569] tracking-widest uppercase mb-1">
              total USDC
            </div>
            <div className="font-mono text-2xl font-bold" style={{ color: balanceColor }}>
              {balance.total !== null ? `$${balance.total.toFixed(2)}` : '—'}
            </div>
          </div>
        </div>

        {/* Per-chain breakdown */}
        {balance.address && balance.chains && Object.keys(balance.chains).length > 0 && (
          <div className="grid grid-cols-3 gap-2 border-t border-[#1a1a2e] pt-3">
            {(['polygon', 'ethereum', 'base'] as const).map(chain => {
              const c = balance.chains[chain]
              if (!c) return null
              const chainTotal = (c.usdc ?? 0) + (c.usdc_e ?? 0)
              const explorerBase = chain === 'polygon'
                ? 'https://polygonscan.com/address/'
                : chain === 'base'
                ? 'https://basescan.org/address/'
                : 'https://etherscan.io/address/'
              return (
                <a
                  key={chain}
                  href={`${explorerBase}${balance.address}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-[#111318] border border-[#1a1a2e] rounded p-2 hover:border-[#334155] transition-colors"
                >
                  <div className="font-mono text-[9px] text-[#334155] tracking-widest uppercase mb-1">
                    {chain} ↗
                  </div>
                  <div className={`font-mono text-sm font-bold ${chainTotal > 0 ? 'text-[#22c55e]' : 'text-[#475569]'}`}>
                    ${chainTotal.toFixed(2)}
                  </div>
                  {c.usdc_e !== undefined && c.usdc_e > 0 && (
                    <div className="font-mono text-[9px] text-[#334155] mt-0.5">
                      +${c.usdc_e.toFixed(2)} bridged
                    </div>
                  )}
                  {c.native > 0 && (
                    <div className="font-mono text-[9px] text-[#334155]">
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
            RPC partial error · {balance.error.slice(0, 120)}
          </div>
        )}
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
          <div className="font-mono text-2xl font-bold" style={{ color: pnlColor(avgPnl) }}>
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

        <div className="bg-[#0d0d10] border border-[#1a1a2e] rounded-lg p-4 space-y-1.5 max-h-64 overflow-y-auto font-mono text-[11px]">
          {logs.length === 0 ? (
            <div className="text-[#334155] text-center py-4">
              no activity yet — agent starts automatically on deploy
            </div>
          ) : (
            logs.map(log => (
              <div key={log.id} className="flex items-start gap-2.5">
                <span className="text-[#334155] shrink-0">{formatTs(log.ts)}</span>
                <span className="shrink-0 font-bold w-3 text-center" style={{ color: LOG_COLORS[log.level] ?? '#475569' }}>
                  {LOG_ICONS[log.level] ?? '·'}
                </span>
                <span style={{ color: LOG_COLORS[log.level] ?? '#475569' }}>{log.event}</span>
                {log.condition_id && (
                  <span className="text-[#334155] shrink-0">{log.condition_id.slice(0, 10)}…</span>
                )}
                {log.detail && (
                  <span className="text-[#475569] truncate">{log.detail}</span>
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
              ? 'scanning geopolitics markets first — trades appear when strong signals pass the gate'
              : 'agent auto-starts on deploy — or click start agent above'}
          </div>
        </div>
      )}
    </main>
  )
}
