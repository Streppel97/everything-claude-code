import { usePortfolio } from '../hooks/usePortfolio'
import { useWebSocket } from '../hooks/useWebSocket'
import PortfolioPanel from './PortfolioPanel'
import RiskGauge from './RiskGauge'
import { api } from '../utils/api'
import { useState, useEffect } from 'react'
import type { SignalData, ActivityEntry, TradeData } from '../utils/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

export default function Dashboard() {
  const { portfolio, status, stats, snapshots, loading, error, refresh } = usePortfolio(10000)
  const { connected } = useWebSocket()
  const [signals, setSignals] = useState<SignalData[]>([])
  const [activity, setActivity] = useState<ActivityEntry[]>([])
  const [trades, setTrades] = useState<TradeData[]>([])

  useEffect(() => {
    const fetchExtras = async () => {
      try {
        const [sig, act, tr] = await Promise.all([
          api.getSignals(10),
          api.getActivity(15),
          api.getTrades(10),
        ])
        setSignals(sig)
        setActivity(act)
        setTrades(tr)
      } catch {
        // ignore
      }
    }
    fetchExtras()
    const interval = setInterval(fetchExtras, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-500">Loading...</div>
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-warroom-red">
        {error} &mdash; Is the backend running?
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Status Bar */}
      <div className="flex items-center gap-4 bg-warroom-panel rounded-lg p-4 border border-warroom-border">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-warroom-green' : 'bg-warroom-red'}`} />
          <span className="text-xs text-gray-500">{connected ? 'LIVE' : 'DISCONNECTED'}</span>
        </div>
        <div className="text-sm">
          Mode: <span className={`font-bold ${status?.halted ? 'text-warroom-red' : 'text-warroom-green'}`}>
            {status?.halted ? 'HALTED' : status?.trading_mode?.toUpperCase()}
          </span>
        </div>
        <div className="text-sm">
          Scans: <span className="font-mono">{status?.scan_count ?? 0}</span>
        </div>
        <div className="ml-auto flex gap-2">
          <button onClick={() => api.scan().then(refresh)} className="px-3 py-1 bg-warroom-accent rounded text-xs hover:bg-blue-600">
            Force Scan
          </button>
          <button
            onClick={() => (status?.halted ? api.resume() : api.halt()).then(refresh)}
            className={`px-3 py-1 rounded text-xs ${status?.halted ? 'bg-warroom-green hover:bg-green-600' : 'bg-warroom-red hover:bg-red-600'}`}
          >
            {status?.halted ? 'Resume' : 'HALT'}
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Scanner */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-warroom-green mb-3">MARKET SCANNER</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {signals.map((sig, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-gray-900 rounded p-2">
                <div className="flex-1 truncate mr-2">{sig.question}</div>
                <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${sig.signal_direction === 'YES' ? 'bg-green-900 text-warroom-green' : 'bg-red-900 text-warroom-red'}`}>
                  {sig.signal_direction}
                </span>
                <span className="ml-2 font-mono w-12 text-right">{sig.current_price_yes.toFixed(2)}</span>
                <span className={`ml-2 font-mono w-14 text-right ${sig.price_change_1h >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                  {(sig.price_change_1h * 100).toFixed(1)}%
                </span>
                <span className="ml-2 font-mono w-10 text-right text-warroom-yellow">{sig.signal_strength.toFixed(2)}</span>
              </div>
            ))}
            {signals.length === 0 && <div className="text-gray-600 text-xs">No signals yet...</div>}
          </div>
        </div>

        {/* Positions */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-blue-400 mb-3">OPEN POSITIONS</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {portfolio?.open_positions.map((pos, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-gray-900 rounded p-2">
                <div className="flex-1 truncate mr-2">{pos.question || pos.market_id}</div>
                <span className={`px-1.5 py-0.5 rounded font-bold ${pos.direction.includes('YES') ? 'text-warroom-green' : 'text-warroom-red'}`}>
                  {pos.direction.replace('BUY_', '')} @ {pos.entry_price.toFixed(3)}
                </span>
                <span className="ml-2 font-mono w-16 text-right">${pos.position_size.toFixed(0)}</span>
                <span className={`ml-2 font-mono w-16 text-right font-bold ${pos.unrealized_pnl >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                  ${pos.unrealized_pnl.toFixed(2)}
                </span>
                <button onClick={() => api.sell(pos.trade_id).then(refresh)} className="ml-2 px-2 py-0.5 bg-red-800 rounded text-xs hover:bg-red-700">
                  Sell
                </button>
              </div>
            ))}
            {(!portfolio?.open_positions.length) && <div className="text-gray-600 text-xs">No open positions</div>}
          </div>
        </div>

        {/* Activity Log */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-purple-400 mb-3">AGENT ACTIVITY</h2>
          <div className="space-y-1 max-h-64 overflow-y-auto font-mono text-xs">
            {activity.map((entry, i) => {
              const time = entry.timestamp.slice(11, 16)
              const colors: Record<string, string> = {
                scanner: 'text-warroom-green',
                analyst: 'text-cyan-400',
                risk: 'text-warroom-yellow',
                executor: 'text-white',
              }
              return (
                <div key={i} className="flex gap-2">
                  <span className="text-gray-600">[{time}]</span>
                  <span className={colors[entry.agent] ?? 'text-gray-400'}>{entry.agent}:</span>
                  <span className="text-gray-300 truncate">{entry.message}</span>
                </div>
              )
            })}
            {activity.length === 0 && <div className="text-gray-600">Waiting for activity...</div>}
          </div>
        </div>

        {/* Trade History */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-warroom-yellow mb-3">
            TRADE HISTORY ({stats?.total_trades ?? 0} trades, {portfolio?.win_count ?? 0}W/{portfolio?.loss_count ?? 0}L)
          </h2>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {trades.map((trade, i) => {
              const time = trade.opened_at?.slice(11, 16) ?? '?'
              return (
                <div key={i} className="flex items-center justify-between text-xs bg-gray-900 rounded p-1.5">
                  <span className="text-gray-500 w-12">{time}</span>
                  <span className={`w-16 ${trade.status === 'OPEN' ? 'text-warroom-green' : 'text-gray-400'}`}>
                    {trade.status === 'OPEN' ? 'BUY' : 'SOLD'} {trade.direction.replace('BUY_', '')}
                  </span>
                  <span className="flex-1 truncate mx-2">{trade.question || trade.market_id}</span>
                  <span className="font-mono w-14 text-right">${trade.position_size.toFixed(0)}</span>
                  {trade.pnl !== null && (
                    <span className={`font-mono w-16 text-right font-bold ${trade.pnl >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                      ${trade.pnl.toFixed(2)}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Bottom Row: Portfolio + Risk */}
      <div className="grid grid-cols-3 gap-4">
        <PortfolioPanel portfolio={portfolio} stats={stats} />
        <RiskGauge portfolio={portfolio} status={status} />

        {/* P&L Chart */}
        <div className="bg-warroom-panel rounded-lg border border-warroom-border p-4">
          <h2 className="text-sm font-bold text-gray-400 mb-3">PORTFOLIO VALUE</h2>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={snapshots.map(s => ({ time: s.timestamp.slice(11, 16), value: s.total_value }))}>
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#1f2937', border: 'none', borderRadius: 8, fontSize: 12 }} />
              <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
