import Link from 'next/link'
import { UrlInput } from '@/components/UrlInput'

export default function Home() {
  return (
    <main className="flex flex-col flex-1 items-center justify-center min-h-screen px-4">
      {/* Top nav */}
      <div className="absolute top-4 right-4">
        <Link
          href="/trades"
          className="font-mono text-xs text-[#475569] hover:text-[#94a3b8] transition-colors tracking-widest uppercase border border-[#1a1a2e] rounded px-3 py-1.5"
        >
          agent trades →
        </Link>
      </div>

      {/* Header */}
      <div className="mb-12 text-center">
        <div className="flex items-center justify-center gap-2 mb-4">
          <span className="inline-block w-2 h-2 rounded-full bg-[#22c55e] animate-pulse" />
          <span className="text-[#22c55e] text-xs tracking-[3px] uppercase">live signals</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-[#f1f5f9] tracking-tight mb-3">
          polymarket scanner
        </h1>
        <p className="text-[#94a3b8] text-sm tracking-wide">
          paste a polymarket url. get the alpha.
        </p>
      </div>

      {/* Input */}
      <div className="w-full max-w-xl">
        <UrlInput />
      </div>

      {/* Footer note */}
      <div className="mt-16 text-center">
        <p className="text-[#475569] text-xs">
          powered by{' '}
          <span className="text-[#94a3b8]">timesfm</span>
          {' '}·{' '}
          <span className="text-[#94a3b8]">claude</span>
          {' '}·{' '}
          <span className="text-[#94a3b8]">ows</span>
        </p>
      </div>
    </main>
  )
}
