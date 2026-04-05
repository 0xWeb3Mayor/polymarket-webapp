import { getTrades, getAgentStatus, getAgentLogs, getWalletBalance } from '@/lib/api'
import TradesView from '../trades/TradesView'

export const metadata = {
  title: 'PolyAgent Dashboard',
  description: 'Agent control panel.',
}

// Prevent search engines indexing the dashboard
export const robots = { index: false, follow: false }

export default async function DashboardPage() {
  const [trades, agentStatus, logs, balance] = await Promise.all([
    getTrades().catch(() => []),
    getAgentStatus().catch(() => ({
      running: false,
      live: false,
      wallet: 'polyagent-treasury',
      max_trade_usd: 10,
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
      readOnly={false}
    />
  )
}
