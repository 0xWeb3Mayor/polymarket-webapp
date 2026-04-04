import { getTrades, getAgentStatus } from '@/lib/api'
import TradesView from './TradesView'

export const metadata = {
  title: 'PolyAgent Trades | Polymarket Scanner',
  description: 'Autonomous prediction market trades executed by PolyAgent via OWS.',
}

export default async function TradesPage() {
  const [trades, agentStatus] = await Promise.all([
    getTrades().catch(() => []),
    getAgentStatus().catch(() => ({
      running: false,
      live: false,
      wallet: 'polyagent-treasury',
      max_trade_usd: 50,
      daily_limit_usd: 200,
    })),
  ])

  return <TradesView initial={trades} agentStatus={agentStatus} />
}
