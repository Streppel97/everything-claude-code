import { useState, useEffect } from 'react'
import { api } from '../utils/api'
import type { SignalData } from '../utils/api'

export default function MarketScanner() {
  const [signals, setSignals] = useState<SignalData[]>([])
  const [filter, setFilter] = useState('')
  const [sortBy, setSortBy] = useState<'signal_strength' | 'volume_24h' | 'price_change_1h'>('signal_strength')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await api.getSignals(100)
        setSignals(data)
      } catch { /* ignore */ }
      setLoading(false)
    }
    fetch()
    const interval = setInterval(fetch, 15000)
    return () => clearInterval(interval)
  }, [])

  const filtered = signals
    .filter(s => !filter || s.question.toLowerCase().includes(filter.toLowerCase()) || s.category.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'signal_strength') return b.signal_strength - a.signal_strength
      if (sortBy === 'volume_24h') return b.volume_24h - a.volume_24h
      return Math.abs(b.price_change_1h) - Math.abs(a.price_change_1h)
    })

  if (loading) return <div className="text-gray-500 text-center py-8">Loading markets...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <input
          type="text"
          placeholder="Filter markets..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="bg-warroom-panel border border-warroom-border rounded px-3 py-2 text-sm flex-1 focus:outline-none focus:border-warroom-accent"
        />
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className="bg-warroom-panel border border-warroom-border rounded px-3 py-2 text-sm focus:outline-none"
        >
          <option value="signal_strength">Sort: Signal Strength</option>
          <option value="volume_24h">Sort: Volume</option>
          <option value="price_change_1h">Sort: 1h Change</option>
        </select>
        <span className="text-gray-500 text-sm">{filtered.length} markets</span>
      </div>

      <div className="bg-warroom-panel rounded-lg border border-warroom-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-warroom-border text-gray-500 text-xs">
              <th className="text-left p-3">Market</th>
              <th className="text-left p-3">Category</th>
              <th className="text-right p-3">YES</th>
              <th className="text-right p-3">NO</th>
              <th className="text-right p-3">1h Chg</th>
              <th className="text-right p-3">Volume 24h</th>
              <th className="text-right p-3">Liquidity</th>
              <th className="text-right p-3">Spread</th>
              <th className="text-right p-3">Signal</th>
              <th className="text-center p-3">Direction</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((sig, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-900/50">
                <td className="p-3 max-w-xs truncate">{sig.question}</td>
                <td className="p-3 text-gray-500 text-xs">{sig.category}</td>
                <td className="p-3 text-right font-mono">{sig.current_price_yes.toFixed(3)}</td>
                <td className="p-3 text-right font-mono">{sig.current_price_no.toFixed(3)}</td>
                <td className={`p-3 text-right font-mono ${sig.price_change_1h >= 0 ? 'text-warroom-green' : 'text-warroom-red'}`}>
                  {(sig.price_change_1h * 100).toFixed(1)}%
                </td>
                <td className="p-3 text-right font-mono">${sig.volume_24h.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className="p-3 text-right font-mono">${sig.liquidity.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className="p-3 text-right font-mono">{(sig.spread * 100).toFixed(1)}%</td>
                <td className="p-3 text-right">
                  <span className={`font-mono font-bold ${sig.signal_strength > 0.7 ? 'text-warroom-green' : sig.signal_strength > 0.4 ? 'text-warroom-yellow' : 'text-gray-500'}`}>
                    {sig.signal_strength.toFixed(2)}
                  </span>
                </td>
                <td className="p-3 text-center">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${sig.signal_direction === 'YES' ? 'bg-green-900 text-warroom-green' : 'bg-red-900 text-warroom-red'}`}>
                    {sig.signal_direction}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center text-gray-600 py-8">No signals match your filter</div>
        )}
      </div>
    </div>
  )
}
