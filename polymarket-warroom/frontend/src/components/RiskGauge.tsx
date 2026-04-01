import type { PortfolioData, StatusData } from '../utils/api'

interface Props {
  portfolio: PortfolioData | null
  status: StatusData | null
}

export default function RiskGauge({ portfolio, status }: Props) {
  if (!portfolio) return null

  const exposurePct = portfolio.total_exposure_pct * 100
  const maxExposure = 40 // from settings
  const exposureRatio = Math.min(exposurePct / maxExposure, 1)

  const getColor = (ratio: number) => {
    if (ratio < 0.5) return 'bg-warroom-green'
    if (ratio < 0.75) return 'bg-warroom-yellow'
    return 'bg-warroom-red'
  }

  return (
    <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
      <h2 className="text-sm font-bold text-gray-400 mb-3">RISK METER</h2>

      <div className="space-y-4">
        {/* Exposure Gauge */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-500">Exposure</span>
            <span className="font-mono">{exposurePct.toFixed(1)}% / {maxExposure}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all duration-500 ${getColor(exposureRatio)}`}
              style={{ width: `${Math.min(exposureRatio * 100, 100)}%` }}
            />
          </div>
        </div>

        {/* Position Count */}
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Open Positions</span>
          <span className="font-mono">{portfolio.open_positions.length}</span>
        </div>

        {/* Cash Available */}
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Available Cash</span>
          <span className="font-mono">${portfolio.cash.toFixed(2)}</span>
        </div>

        {/* Trading Status */}
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Status</span>
          <span className={`font-bold ${status?.halted ? 'text-warroom-red' : 'text-warroom-green'}`}>
            {status?.halted ? 'HALTED' : 'ACTIVE'}
          </span>
        </div>

        {status?.halted && status.halt_reason && (
          <div className="bg-red-900/30 rounded p-2 text-xs text-warroom-red">
            {status.halt_reason}
          </div>
        )}

        {/* Daily Loss Indicator */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-500">Daily P&L Limit</span>
            <span className="font-mono">
              ${Math.abs(portfolio.daily_pnl).toFixed(2)} / ${(portfolio.total_value * 0.05).toFixed(2)}
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${portfolio.daily_pnl < 0 ? 'bg-warroom-red' : 'bg-warroom-green'}`}
              style={{
                width: `${Math.min((Math.abs(portfolio.daily_pnl) / (portfolio.total_value * 0.05)) * 100, 100)}%`,
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
