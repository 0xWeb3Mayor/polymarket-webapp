'use client'

import { AIReport as AIReportType } from '@/lib/api'

interface Props {
  report: AIReportType
}

function actionColor(action: string): string {
  const a = action.toUpperCase()
  if (a.startsWith('BUY')) return '#22c55e'
  if (a.startsWith('SELL')) return '#ef4444'
  return '#94a3b8'
}

function ProbBar({ yes, no }: { yes: number; no: number }) {
  const yesPct = Math.round(yes * 100)
  const noPct = Math.round(no * 100)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-xs font-mono">
        <span className="w-8 text-right text-[#22c55e]">{yesPct}%</span>
        <div className="flex-1 h-1.5 bg-[#1a1a2e] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-[#22c55e] transition-all"
            style={{ width: `${yesPct}%` }}
          />
        </div>
        <span className="text-[#475569]">YES</span>
      </div>
      <div className="flex items-center gap-2 text-xs font-mono">
        <span className="w-8 text-right text-[#ef4444]">{noPct}%</span>
        <div className="flex-1 h-1.5 bg-[#1a1a2e] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-[#ef4444] transition-all"
            style={{ width: `${noPct}%` }}
          />
        </div>
        <span className="text-[#475569]">NO</span>
      </div>
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] tracking-[3px] uppercase font-mono text-[#475569]">{label}</p>
      {children}
    </div>
  )
}

export function AIReport({ report }: Props) {
  const color = actionColor(report.action)

  return (
    <div className="bg-[#111318] border border-[#1a1a2e] rounded-lg p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] tracking-[3px] uppercase font-mono text-[#475569]">
          ai analysis
        </span>
        <span className="text-[10px] font-mono text-[#475569]">claude sonnet</span>
      </div>

      {/* What it asks */}
      <Section label="what this asks">
        <p className="text-sm font-mono text-[#f1f5f9] leading-relaxed">{report.what_it_asks}</p>
        <p className="text-xs font-mono text-[#64748b] leading-relaxed mt-1">
          {report.resolution_criteria}
        </p>
      </Section>

      {/* Key factors */}
      <Section label="key factors">
        <ul className="space-y-1">
          {report.key_factors.map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-xs font-mono text-[#94a3b8]">
              <span className="text-[#22c55e] mt-0.5 shrink-0">›</span>
              <span>{f}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* Probability */}
      <Section label="probability estimate">
        <ProbBar yes={report.probability_yes} no={report.probability_no} />
        <p className="text-xs font-mono text-[#64748b] mt-2 leading-relaxed">{report.vs_market}</p>
      </Section>

      {/* Mispricing */}
      <Section label="mispricing">
        <p className="text-xs font-mono text-[#94a3b8] leading-relaxed">{report.mispricing}</p>
      </Section>

      {/* Recommendation */}
      <div className="border border-[#1a1a2e] rounded-lg p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] tracking-[3px] uppercase font-mono text-[#475569]">
            recommendation
          </span>
          <span
            className="text-sm font-mono font-bold tracking-widest"
            style={{ color }}
          >
            {report.action}
          </span>
        </div>
        <p className="text-xs font-mono text-[#94a3b8] leading-relaxed">{report.reasoning}</p>
      </div>
    </div>
  )
}
