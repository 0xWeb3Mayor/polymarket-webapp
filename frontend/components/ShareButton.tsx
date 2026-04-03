'use client'

import { useState } from 'react'

export function ShareButton({ conditionId }: { conditionId: string }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    const url = `${window.location.origin}/m/${conditionId}`
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={copy}
      className="border border-border text-muted hover:border-signal-strong-buy hover:text-signal-strong-buy font-mono text-xs px-4 py-2 rounded-lg transition-colors tracking-widest uppercase"
    >
      {copied ? '✓ copied' : 'share link'}
    </button>
  )
}
