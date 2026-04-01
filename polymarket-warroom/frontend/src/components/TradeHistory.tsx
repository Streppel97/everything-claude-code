import { useState, useEffect } from 'react'
import { api } from '../utils/api'
import type { TradeData } from '../utils/api'

export default function TradeHistory() {
  const [trades, setTrades] = useState<TradeData[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await api.getTrades(100)
        setTrades(data)
      } catch { /* ignore */ }
      setLoading(false)
    }
    fetch()
    const interval = setInterval(fetch, 10000)
    return () => clearInterval(interval)
  }, [])

  const filtered = trades.filter(t => !statusFilter || t.status === statusFilter)

  const totalPnl = filtered.reduce((sum, t) => sum + (t.pnl ?? 0), 0)
  const wins = filtered.filter(t => (t.pnl ?? 0) > 0).length
  const closed = filtered.filter(t => t.status !== 'OPEN').length

  const exportCsv = () => {
    const headers = 'ID,Market,Direction,Entry,Exit,Size,P&L,Status,Strategy,Opened,Closed\n'
    const rows = filtered.map(t =>
      `${t.id},"${t.question}",${t.direction},${t.entry_price},${t.exit_price ?? ''},${t.position_size},${t.pnl ?? ''},${t.status},${t.strategy},${t.opened_at},${t.closed_at ?? ''}`
    ).join('\n')
    const blob = new Blob([headers + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'trade_history.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return <div className="text-gray-500 text-center py-8">Loading trades...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-warroom-panel border border-warroom-border rounded px-3 py-2 text-sm"
        >
          <option value="">All Statuses</option>
          <option value="OPEN">Open</option>
          <option value="CLOSED">Closed</option>
          <option value="STOPPED_OUT">Stopped Out</option>
        </select>

        <div className="flex gap-6 text-sm ml-4">
          <span>Total: <span className="font-bold">{filtered.length}</span></span>
          <span>Win Rate: <span className="font-bold">{closed > 0 ? ((wins / closed) * 100).toFixed(1) : '0'}%</span></span>
          <span>P&L: <span className={`font-bold ${totalPnl >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>${totalPnl.toFixed(2)}</span></span>
        </div>

        <button onClick={exportCsv} className="ml-auto px-3 py-1.5 bg-gray-700 rounded text-xs hover:bg-gray-600">
          Export CSV
        </button>
      </div>

      <div className="bg-warroom-panel rounded-lg border border-warroom-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-warroom-border text-gray-500 text-xs">
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Time</th>
              <th className="text-left p-3">Market</th>
              <th className="text-center p-3">Direction</th>
              <th className="text-right p-3">Entry</th>
              <th className="text-right p-3">Exit</th>
              <th className="text-right p-3">Size</th>
              <th className="text-right p-3">P&L</th>
              <th className="text-center p-3">Status</th>
              <th className="text-left p-3">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((trade) => (
              <tr key={trade.id} className="border-b border-gray-800 hover:bg-gray-900/50">
                <td className="p-3 text-gray-500">#{trade.id}</td>
                <td className="p-3 text-gray-400 text-xs font-mono">{trade.opened_at?.slice(0, 16).replace('T', ' ')}</td>
                <td className="p-3 max-w-xs truncate">{trade.question || trade.market_id}</td>
                <td className="p-3 text-center">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${trade.direction.includes('YES') ? 'bg-green-900 text-warroom-green' : 'bg-red-900 text-warroom-red'}`}>
                    {trade.direction.replace('BUY_', '')}
                  </span>
                </td>
                <td className="p-3 text-right font-mono">{trade.entry_price.toFixed(4)}</td>
                <td className="p-3 text-right font-mono">{trade.exit_price?.toFixed(4) ?? '-'}</td>
                <td className="p-3 text-right font-mono">${trade.position_size.toFixed(2)}</td>
                <td className={`p-3 text-right font-mono font-bold ${(trade.pnl ?? 0) >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                  {trade.pnl != null ? `$${trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}` : '-'}
                </td>
                <td className="p-3 text-center">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    trade.status === 'OPEN' ? 'bg-blue-900 text-blue-400' :
                    trade.status === 'CLOSED' ? 'bg-gray-800 text-gray-400' :
                    'bg-red-900 text-warroom-red'
                  }`}>
                    {trade.status}
                  </span>
                </td>
                <td className="p-3 text-gray-500 text-xs">{trade.strategy}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center text-gray-600 py-8">No trades yet</div>
        )}
      </div>
    </div>
  )
}
