import type { PortfolioData, StatsData } from '../utils/api'

interface Props {
  portfolio: PortfolioData | null
  stats: StatsData | null
}

export default function PortfolioPanel({ portfolio, stats }: Props) {
  if (!portfolio) return null

  const pnlColor = portfolio.total_pnl >= 0 ? 'text-warroom-green' : 'text-warroom-red'

  return (
    <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
      <h2 className="text-sm font-bold text-gray-400 mb-3">PORTFOLIO</h2>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Total Value</span>
          <span className="font-bold font-mono">${portfolio.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Cash</span>
          <span className="font-mono">${portfolio.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Positions</span>
          <span className="font-mono">${portfolio.positions_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>
        <hr className="border-warroom-border" />
        <div className="flex justify-between">
          <span className="text-gray-500">Total P&L</span>
          <span className={`font-bold font-mono ${pnlColor}`}>
            ${portfolio.total_pnl >= 0 ? '+' : ''}{portfolio.total_pnl.toFixed(2)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Daily P&L</span>
          <span className={`font-mono ${portfolio.daily_pnl >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
            ${portfolio.daily_pnl >= 0 ? '+' : ''}{portfolio.daily_pnl.toFixed(2)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Win Rate</span>
          <span className="font-mono">
            {portfolio.total_trades > 0 ? ((portfolio.win_count / portfolio.total_trades) * 100).toFixed(1) : '0.0'}%
          </span>
        </div>
        {stats && (
          <>
            <div className="flex justify-between">
              <span className="text-gray-500">Sharpe</span>
              <span className="font-mono">{stats.sharpe_ratio.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Max DD</span>
              <span className="font-mono text-warroom-red">${stats.max_drawdown.toFixed(2)}</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
