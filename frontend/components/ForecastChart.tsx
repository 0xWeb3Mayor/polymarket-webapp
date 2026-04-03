'use client'

import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { ChartPoint, Signal, signalColor } from '@/lib/api'

interface ForecastChartProps {
  data: ChartPoint[]
  signal: Signal
  nowTimestamp: number
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatPercent(val: number): string {
  return `${(val * 100).toFixed(0)}%`
}

interface TooltipPayload {
  name: string
  value: number
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayload[]
  label?: number
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length || label === undefined) return null

  const date = new Date(label * 1000).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="bg-surface border border-border rounded px-3 py-2 font-mono text-xs">
      <p className="text-secondary mb-1">{date}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }}>
          {entry.name}: {formatPercent(entry.value)}
        </p>
      ))}
    </div>
  )
}

export default function ForecastChart({ data, signal, nowTimestamp }: ForecastChartProps) {
  const color = signalColor(signal)

  // Ticks: sample ~6 evenly spaced timestamps
  const ticks = data
    .filter((_, i) => i % Math.max(1, Math.floor(data.length / 6)) === 0)
    .map((d) => d.timestamp)

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1a1a2e" strokeDasharray="3 3" vertical={false} />

        <XAxis
          dataKey="timestamp"
          type="number"
          domain={['dataMin', 'dataMax']}
          ticks={ticks}
          tickFormatter={formatTimestamp}
          tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'monospace' }}
          axisLine={{ stroke: '#1a1a2e' }}
          tickLine={false}
          scale="time"
        />

        <YAxis
          domain={[0, 1]}
          tickFormatter={formatPercent}
          tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'monospace' }}
          axisLine={false}
          tickLine={false}
          width={48}
        />

        <Tooltip content={<CustomTooltip />} />

        {/* CI band */}
        <Area
          dataKey="ci_high"
          stroke="none"
          fill={color}
          fillOpacity={0.15}
          connectNulls
          name="CI High"
          legendType="none"
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        />
        <Area
          dataKey="ci_low"
          stroke="none"
          fill="#0a0a0a"
          fillOpacity={1}
          connectNulls
          name="CI Low"
          legendType="none"
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        />

        {/* Historical line */}
        <Line
          dataKey="historical"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
          connectNulls
          name="Price"
          isAnimationActive={false}
          activeDot={{ r: 3, fill: '#3b82f6' }}
        />

        {/* Forecast line */}
        <Line
          dataKey="forecast"
          stroke={color}
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
          connectNulls
          name="Forecast"
          isAnimationActive={false}
          activeDot={{ r: 3, fill: color }}
        />

        {/* Now separator */}
        <ReferenceLine
          x={nowTimestamp}
          stroke="#475569"
          strokeDasharray="3 3"
          label={{
            value: 'now',
            fill: '#475569',
            fontSize: 10,
            fontFamily: 'monospace',
            position: 'insideTopRight',
          }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
