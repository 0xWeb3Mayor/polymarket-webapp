import { Forecast, Signal, signalColor, signalLabel, formatPrice, formatDivergence } from '@/lib/api'

interface Props {
  question: string
  lastPrice: number
  forecast: Forecast
}

function generateThesis(signal: Signal, lastPrice: number, forecast: Forecast): string {
  const fp = forecast.forecast_price
  const div = forecast.divergence_pct
  const horizon = forecast.horizon_hours

  if (signal === 'HOLD') {
    return `The model finds no meaningful edge here. Current price of ${formatPrice(lastPrice)} is within the model's noise band. Skip.`
  }

  const direction = div > 0 ? 'underpriced' : 'overpriced'
  const action = div > 0 ? 'Buying YES' : 'Selling YES (buying NO)'
  const returnStr = formatDivergence(Math.abs(div))

  return `The model thinks this market is significantly ${direction}. ${action} at ${formatPrice(lastPrice)} targeting ${formatPrice(fp)} in ${horizon}hrs returns ${returnStr} if correct. 80% CI: ${formatPrice(forecast.ci_80_low)} – ${formatPrice(forecast.ci_80_high)}.`
}

export function SignalCard({ question, lastPrice, forecast }: Props) {
  const color = signalColor(forecast.signal)
  const label = signalLabel(forecast.signal)
  const thesis = generateThesis(forecast.signal, lastPrice, forecast)

  return (
    <div className="w-full bg-surface border border-border rounded-lg p-6 space-y-4">
      <div className="space-y-2">
        <div
          className="inline-block border rounded px-3 py-1 font-mono text-xs font-bold tracking-widest uppercase"
          style={{ borderColor: color, color }}
        >
          {label}
        </div>
        <h1 className="font-mono text-base text-slate-200 leading-relaxed">{question}</h1>
      </div>

      <div className="flex items-baseline gap-6 font-mono">
        <div>
          <div className="text-xs text-muted tracking-widest uppercase mb-1">Current</div>
          <div className="text-3xl font-bold text-slate-200">{formatPrice(lastPrice)}</div>
        </div>
        <div className="text-muted text-xl self-center">→</div>
        <div>
          <div className="text-xs tracking-widest uppercase mb-1" style={{ color }}>Forecast</div>
          <div className="text-3xl font-bold" style={{ color }}>{formatPrice(forecast.forecast_price)}</div>
        </div>
        <div>
          <div className="text-xs tracking-widest uppercase mb-1" style={{ color }}>Edge</div>
          <div className="text-3xl font-bold" style={{ color }}>{formatDivergence(forecast.divergence_pct)}</div>
        </div>
      </div>

      <p className="font-mono text-sm text-muted leading-relaxed border-t border-border pt-4">
        {thesis}
      </p>
    </div>
  )
}
