import { useState } from 'react'
import Dashboard from './components/Dashboard'
import TradeHistory from './components/TradeHistory'
import MarketScanner from './components/MarketScanner'
import AgentStatus from './components/AgentStatus'

type View = 'dashboard' | 'markets' | 'trades' | 'analytics'

export default function App() {
  const [view, setView] = useState<View>('dashboard')

  return (
    <div className="min-h-screen bg-warroom-bg text-gray-100">
      {/* Navigation */}
      <nav className="bg-warroom-panel border-b border-warroom-border px-6 py-3 flex items-center gap-6">
        <h1 className="text-xl font-bold text-warroom-accent">POLYMARKET WAR ROOM</h1>
        <div className="flex gap-1 ml-8">
          {(['dashboard', 'markets', 'trades', 'analytics'] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                view === v
                  ? 'bg-warroom-accent text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content */}
      <main className="p-4">
        {view === 'dashboard' && <Dashboard />}
        {view === 'markets' && <MarketScanner />}
        {view === 'trades' && <TradeHistory />}
        {view === 'analytics' && <AgentStatus />}
      </main>
    </div>
  )
}
