import { useState, useEffect } from 'react'
import { api } from '../utils/api'
import type { MarketData } from '../utils/api'

interface Props {
  marketId: string
  onClose: () => void
}

export default function MarketDetail({ marketId, onClose }: Props) {
  const [market, setMarket] = useState<MarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [buyDirection, setBuyDirection] = useState<'BUY_YES' | 'BUY_NO'>('BUY_YES')
  const [amount, setAmount] = useState('100')

  useEffect(() => {
    api.getMarket(marketId).then(setMarket).finally(() => setLoading(false))
  }, [marketId])

  if (loading) return <div className="text-gray-500">Loading...</div>
  if (!market) return <div className="text-warroom-red">Market not found</div>

  const handleBuy = async () => {
    await api.buy(marketId, buyDirection, parseFloat(amount))
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-warroom-panel rounded-lg border border-warroom-border p-6 max-w-lg w-full mx-4">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-lg font-bold">{market.question}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl">&times;</button>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
          <div className="bg-gray-900 rounded p-3">
            <div className="text-gray-500 text-xs mb-1">YES Price</div>
            <div className="text-2xl font-bold text-warroom-green font-mono">{market.outcome_yes_price.toFixed(3)}</div>
          </div>
          <div className="bg-gray-900 rounded p-3">
            <div className="text-gray-500 text-xs mb-1">NO Price</div>
            <div className="text-2xl font-bold text-warroom-red font-mono">{market.outcome_no_price.toFixed(3)}</div>
          </div>
        </div>

        <div className="space-y-2 text-sm mb-6">
          <div className="flex justify-between"><span className="text-gray-500">Category</span><span>{market.category}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">Volume 24h</span><span className="font-mono">${market.volume_24h.toLocaleString()}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">Liquidity</span><span className="font-mono">${market.liquidity.toLocaleString()}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">Spread</span><span className="font-mono">{(market.spread * 100).toFixed(1)}%</span></div>
          {market.resolution_date && (
            <div className="flex justify-between"><span className="text-gray-500">Resolution</span><span>{new Date(market.resolution_date).toLocaleDateString()}</span></div>
          )}
        </div>

        <div className="border-t border-warroom-border pt-4">
          <h3 className="text-sm font-bold mb-3">Quick Trade</h3>
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => setBuyDirection('BUY_YES')}
              className={`flex-1 py-2 rounded text-sm font-bold ${buyDirection === 'BUY_YES' ? 'bg-warroom-green text-white' : 'bg-gray-800'}`}
            >
              BUY YES
            </button>
            <button
              onClick={() => setBuyDirection('BUY_NO')}
              className={`flex-1 py-2 rounded text-sm font-bold ${buyDirection === 'BUY_NO' ? 'bg-warroom-red text-white' : 'bg-gray-800'}`}
            >
              BUY NO
            </button>
          </div>
          <div className="flex gap-2">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bg-gray-900 border border-warroom-border rounded px-3 py-2 text-sm flex-1 focus:outline-none"
              placeholder="Amount (USDC)"
            />
            <button onClick={handleBuy} className="px-4 py-2 bg-warroom-accent rounded text-sm font-bold hover:bg-blue-600">
              Place Order
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
