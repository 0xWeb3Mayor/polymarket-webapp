import { notFound } from 'next/navigation'
import { getMarket } from '@/lib/api'
import MarketView from './MarketView'

interface Props {
  params: Promise<{ id: string }>
}

export default async function MarketPage({ params }: Props) {
  const { id } = await params

  let market
  try {
    market = await getMarket(id, 48)
  } catch {
    notFound()
  }

  return <MarketView conditionId={id} initial={market} />
}
