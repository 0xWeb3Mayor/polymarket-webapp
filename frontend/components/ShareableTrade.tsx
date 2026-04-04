'use client'

import { useState } from 'react'
import { Trade } from '@/lib/api'

interface Props {
  trade: Trade
}

export function ShareableTrade({ trade }: Props) {
  const [copied, setCopied] = useState(false)

  function copy() {
    const url = `${window.location.origin}/trades`
    const signal = trade.signal.replace('_', ' ')
    const entry = `${(trade.entry_price * 100).toFixed(0)}¢`
    const pnl = trade.pnl_pct !== null
      ? ` (${trade.pnl_pct > 0 ? '+' : ''}${trade.pnl_pct.toFixed(1)}%)`
      : ''
    const text = `PolyAgent opened: ${signal} ${trade.side} at ${entry}${pnl}\n${url}`
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={copy}
      className="border border-[#1a1a2e] text-[#475569] hover:border-[#22c55e] hover:text-[#22c55e] font-mono text-[10px] px-3 py-1.5 rounded transition-colors tracking-widest uppercase"
    >
      {copied ? '✓ copied' : 'share trade'}
    </button>
  )
}
