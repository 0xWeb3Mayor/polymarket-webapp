'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import dynamic from 'next/dynamic'
import { MarketResult, buildChartData, getMarket } from '@/lib/api'
import { AIReport } from '@/components/AIReport'
import { SignalCard } from '@/components/SignalCard'
import { HorizonToggle } from '@/components/HorizonToggle'
import { ShareButton } from '@/components/ShareButton'

const ForecastChart = dynamic(() => import('@/components/ForecastChart'), { ssr: false })

interface Props {
  conditionId: string
  initial: MarketResult
}

export default function MarketView({ conditionId, initial }: Props) {
  const router = useRouter()
  const [market, setMarket] = useState<MarketResult>(initial)
  const [horizon, setHorizon] = useState<number>(initial.forecast.horizon_hours)
  const [loading, setLoading] = useState(false)

  const fetchHorizon = useCallback(
    async (h: number) => {
      setLoading(true)
      try {
        const result = await getMarket(conditionId, h)
        setMarket(result)
      } catch {
        // keep previous data on error
      } finally {
        setLoading(false)
      }
    },
    [conditionId]
  )

  useEffect(() => {
    if (horizon !== initial.forecast.horizon_hours) {
      fetchHorizon(horizon)
    }
  }, [horizon, initial.forecast.horizon_hours, fetchHorizon])

  const nowTimestamp = Math.floor(Date.now() / 1000)
  const chartData = buildChartData(market.price_history, market.forecast, market.last_price)

  const closeDate = new Date(market.close_time * 1000).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })

  return (
    <main className="min-h-screen px-4 py-8 max-w-3xl mx-auto space-y-6">
      {/* Nav */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => router.push('/')}
          className="text-[#475569] hover:text-[#94a3b8] text-sm transition-colors font-mono"
        >
          ← analyze another
        </button>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
          <span className="text-[#475569] text-xs font-mono">polymarket scanner</span>
        </div>
      </div>

      {/* Market meta */}
      <div className="text-xs font-mono text-[#475569] space-x-4">
        <span className="text-[#94a3b8] font-mono text-[10px] tracking-widest">
          {conditionId.slice(0, 10)}...
        </span>
        <span>closes {closeDate}</span>
        {market.volume_24h > 0 && (
          <span>vol ${market.volume_24h.toLocaleString()}</span>
        )}
      </div>

      {/* Signal card — question + prices + thesis */}
      <div className={loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
        <SignalCard
          question={market.question}
          lastPrice={market.last_price}
          forecast={market.forecast}
        />
      </div>

      {/* Horizon toggle */}
      <div className="flex items-center gap-3">
        <span className="text-[#475569] text-xs font-mono tracking-widest uppercase">horizon</span>
        <HorizonToggle value={horizon} onChange={setHorizon} loading={loading} />
      </div>

      {/* Chart */}
      <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <span className="text-[#475569] text-xs font-mono tracking-widest uppercase">
            price history + forecast
          </span>
          <span className="text-[#475569] text-xs font-mono">
            <span style={{ color: '#3b82f6' }}>——</span> historical{' '}
            <span style={{ color: '#22c55e' }}>- - -</span> forecast
          </span>
        </div>
        {loading ? (
          <div className="h-[300px] flex items-center justify-center text-[#475569] text-xs font-mono">
            loading forecast...
          </div>
        ) : (
          <ForecastChart
            data={chartData}
            signal={market.forecast.signal}
            nowTimestamp={nowTimestamp}
          />
        )}
      </div>

      {/* AI Report */}
      {market.report && <AIReport report={market.report} />}

      {/* Actions */}
      <div className="flex items-center justify-between pt-2">
        <ShareButton conditionId={conditionId} />
        <button
          onClick={() => router.push('/')}
          className="text-[#475569] hover:text-[#94a3b8] text-sm font-mono transition-colors"
        >
          analyze another →
        </button>
      </div>
    </main>
  )
}
