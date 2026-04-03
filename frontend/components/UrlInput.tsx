'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { analyzeUrl } from '@/lib/api'

export function UrlInput() {
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await analyzeUrl(url.trim())
      router.push(`/m/${result.condition_id}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Something went wrong'
      setError(
        msg.toLowerCase().includes('parse') || msg.toLowerCase().includes('condition')
          ? "that doesn't look like a polymarket url"
          : msg
      )
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl space-y-3">
      <div className="relative">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://polymarket.com/event/..."
          className="w-full bg-surface border border-border rounded-lg px-4 py-3 font-mono text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-signal-strong-buy focus:ring-1 focus:ring-signal-strong-buy transition-colors"
          disabled={loading}
          autoFocus
        />
      </div>
      {error && (
        <p className="font-mono text-xs text-signal-strong-sell">{error}</p>
      )}
      <button
        type="submit"
        disabled={loading || !url.trim()}
        className="w-full bg-surface border border-signal-strong-buy text-signal-strong-buy font-mono text-sm font-semibold py-3 rounded-lg hover:bg-signal-strong-buy hover:text-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed tracking-widest uppercase"
      >
        {loading ? 'analyzing...' : 'Analyze →'}
      </button>
    </form>
  )
}
