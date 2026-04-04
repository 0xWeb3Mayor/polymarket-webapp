import { getTrades, getAgentStatus, getAgentLogs, getWalletBalance } from '@/lib/api'
import TradesView from './TradesView'

export const metadata = {
  title: 'PolyAgent Trades | Polymarket Scanner',
  description: 'Autonomous prediction market trades executed by PolyAgent via OWS.',
}

export default async function TradesPage() {
  const [trades, agentStatus, logs, balance] = await Promise.all([
    getTrades().catch(() => []),
    getAgentStatus().catch(() => ({
      running: false,
      live: false,
      wallet: 'polyagent-treasury',
      max_trade_usd: 50,
      daily_limit_usd: 200,
    })),
    getAgentLogs(100).catch(() => []),
    getWalletBalance().catch(() => ({
      address: null, usdc: null, usdc_e: null, total: null, chain: 'multi', chains: {}, error: null,
    })),
  ])

  return (
    <TradesView
      initial={trades}
      agentStatus={agentStatus}
      initialLogs={logs}
      initialBalance={balance}
    />
  )
}
