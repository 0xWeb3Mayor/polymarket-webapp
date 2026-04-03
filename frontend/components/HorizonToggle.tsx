'use client'

interface Props {
  value: number
  onChange: (hours: number) => void
  loading?: boolean
}

const OPTIONS = [24, 48, 72]

export function HorizonToggle({ value, onChange, loading }: Props) {
  return (
    <div className="flex items-center gap-1 bg-surface border border-border rounded-lg p-1 font-mono text-xs">
      {OPTIONS.map((h) => (
        <button
          key={h}
          onClick={() => onChange(h)}
          disabled={loading}
          className={`px-3 py-1.5 rounded transition-colors tracking-wider disabled:opacity-40 ${
            value === h
              ? 'bg-signal-strong-buy text-bg font-bold'
              : 'text-muted hover:text-slate-200'
          }`}
        >
          {h}hr
        </button>
      ))}
    </div>
  )
}
