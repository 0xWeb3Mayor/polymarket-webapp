import type { Metadata } from 'next'
import { getMarket } from '@/lib/api'

interface Props {
  params: Promise<{ id: string }>
  children: React.ReactNode
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'

  let title = 'Polymarket Signal'
  let description = 'AI-powered Polymarket mispricing scanner.'

  try {
    const market = await getMarket(id, 48)
    const signal = market.forecast.signal.replace('_', ' ')
    const div = market.forecast.divergence_pct
    const divStr = `${div > 0 ? '+' : ''}${div.toFixed(1)}%`
    title = `${signal}: ${market.question.slice(0, 60)}${market.question.length > 60 ? '…' : ''}`
    description = `Current: ${(market.last_price * 100).toFixed(0)}¢ → Forecast: ${(market.forecast.forecast_price * 100).toFixed(0)}¢ (${divStr} edge)`
  } catch {
    // use defaults
  }

  const ogUrl = `${baseUrl}/api/og/${id}`

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      images: [{ url: ogUrl, width: 1200, height: 630 }],
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [ogUrl],
    },
  }
}

export default function MarketLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
