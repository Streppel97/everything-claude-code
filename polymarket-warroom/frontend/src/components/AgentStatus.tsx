import { usePortfolio } from '../hooks/usePortfolio'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts'

export default function AgentStatus() {
  const { stats, snapshots, portfolio, loading } = usePortfolio(15000)

  if (loading) return <div className="text-gray-500 text-center py-8">Loading analytics...</div>

  const strategyData = stats ? Object.entries(stats.strategy_breakdown).map(([name, data]) => ({
    name,
    trades: data.trades,
    wins: data.wins,
    pnl: data.total_pnl,
    winRate: data.win_rate * 100,
  })) : []

  return (
    <div className="space-y-4">
      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Trades', value: stats?.total_trades ?? 0 },
          { label: 'Win Rate', value: `${((stats?.win_rate ?? 0) * 100).toFixed(1)}%` },
          { label: 'Sharpe Ratio', value: (stats?.sharpe_ratio ?? 0).toFixed(2) },
          { label: 'Max Drawdown', value: `$${(stats?.max_drawdown ?? 0).toFixed(2)}`, color: 'text-warroom-red' },
        ].map((card, i) => (
          <div key={i} className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
            <div className="text-xs text-gray-500 mb-1">{card.label}</div>
            <div className={`text-2xl font-bold font-mono ${card.color ?? 'text-white'}`}>{card.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Portfolio Value Over Time */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-gray-400 mb-4">PORTFOLIO VALUE (24h)</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={snapshots.map(s => ({
              time: s.timestamp.slice(11, 16),
              value: s.total_value,
              cash: s.cash,
              positions: s.positions_value,
            }))}>
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#1f2937', border: 'none', borderRadius: 8 }} />
              <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={false} name="Total" />
              <Line type="monotone" dataKey="cash" stroke="#10b981" strokeWidth={1} dot={false} name="Cash" />
              <Line type="monotone" dataKey="positions" stroke="#f59e0b" strokeWidth={1} dot={false} name="Positions" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Strategy Performance */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-gray-400 mb-4">STRATEGY PERFORMANCE</h2>
          {strategyData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={strategyData}>
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6b7280' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
                  <Tooltip contentStyle={{ background: '#1f2937', border: 'none', borderRadius: 8 }} />
                  <Bar dataKey="pnl" name="P&L ($)">
                    {strategyData.map((entry, index) => (
                      <Cell key={index} fill={entry.pnl >= 0 ? '#10b981' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-4 space-y-2">
                {strategyData.map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="font-medium">{s.name}</span>
                    <span className="text-gray-500">{s.trades} trades</span>
                    <span className="text-gray-500">{s.winRate.toFixed(0)}% WR</span>
                    <span className={`font-mono font-bold ${s.pnl >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                      ${s.pnl.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-gray-600 text-center py-8">No completed trades yet</div>
          )}
        </div>
      </div>

      {/* Additional Stats */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-gray-400 mb-3">TRADE STATS</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Avg Return</span>
              <span className={`font-mono ${(stats?.avg_return ?? 0) >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                ${(stats?.avg_return ?? 0).toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Best Trade</span>
              <span className="font-mono text-warroom-green">${(stats?.best_trade_pnl ?? 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Worst Trade</span>
              <span className="font-mono text-warroom-red">${(stats?.worst_trade_pnl ?? 0).toFixed(2)}</span>
            </div>
          </div>
        </div>

        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-gray-400 mb-3">CURRENT STATE</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Open Positions</span>
              <span className="font-mono">{portfolio?.open_positions.length ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Exposure</span>
              <span className="font-mono">{((portfolio?.total_exposure_pct ?? 0) * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Available Cash</span>
              <span className="font-mono">${(portfolio?.cash ?? 0).toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
