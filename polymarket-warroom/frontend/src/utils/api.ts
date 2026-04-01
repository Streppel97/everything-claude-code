const API_BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const api = {
  getStatus: () => request<StatusData>('/status'),
  getPortfolio: () => request<PortfolioData>('/portfolio'),
  getSignals: (limit = 20) => request<SignalData[]>(`/signals?limit=${limit}`),
  getTradeSignals: () => request<TradeSignalData[]>('/trade-signals'),
  getPositions: () => request<PositionData[]>('/positions'),
  getTrades: (limit = 50, offset = 0) =>
    request<TradeData[]>(`/trades?limit=${limit}&offset=${offset}`),
  getActivity: (limit = 50) => request<ActivityEntry[]>(`/activity?limit=${limit}`),
  getStats: () => request<StatsData>('/stats'),
  getSnapshots: (hours = 24) => request<SnapshotData[]>(`/snapshots?hours=${hours}`),
  getMarket: (id: string) => request<MarketData>(`/markets/${id}`),

  scan: () => request<{ signals_count: number }>('/scan', { method: 'POST' }),
  buy: (marketId: string, direction: string, amount: number) =>
    request(`/buy?market_id=${marketId}&direction=${direction}&amount=${amount}`, { method: 'POST' }),
  sell: (tradeId: number) =>
    request(`/sell?trade_id=${tradeId}`, { method: 'POST' }),
  halt: () => request('/halt', { method: 'POST' }),
  resume: () => request('/resume', { method: 'POST' }),
}

// Types
export interface StatusData {
  trading_mode: string
  pipeline_running: boolean
  halted: boolean
  halt_reason: string
  scan_count: number
  open_positions: number
  cash: number
  total_value: number
}

export interface PortfolioData {
  total_value: number
  cash: number
  positions_value: number
  open_positions: PositionData[]
  total_exposure_pct: number
  daily_pnl: number
  total_pnl: number
  win_count: number
  loss_count: number
  total_trades: number
}

export interface PositionData {
  trade_id: number
  market_id: string
  question: string
  direction: string
  entry_price: number
  current_price: number
  position_size: number
  unrealized_pnl: number
  strategy: string
  opened_at: string
}

export interface SignalData {
  market_id: string
  question: string
  category: string
  current_price_yes: number
  current_price_no: number
  volume_24h: number
  liquidity: number
  price_change_1h: number
  price_change_6h: number
  price_change_24h: number
  spread: number
  signal_strength: number
  signal_direction: string
  reasoning: string
}

export interface TradeSignalData {
  market_id: string
  direction: string
  confidence: number
  strategy: string
  entry_price: number
  target_exit_price: number
  stop_loss_price: number
  expected_value: number
  position_size_suggestion: number
  reasoning: string
}

export interface TradeData {
  id: number
  market_id: string
  question: string
  direction: string
  entry_price: number
  exit_price: number | null
  position_size: number
  pnl: number | null
  status: string
  mode: string
  opened_at: string
  closed_at: string | null
  strategy: string
}

export interface ActivityEntry {
  timestamp: string
  agent: string
  message: string
}

export interface StatsData {
  total_trades: number
  win_rate: number
  avg_return: number
  best_trade_pnl: number
  worst_trade_pnl: number
  sharpe_ratio: number
  max_drawdown: number
  strategy_breakdown: Record<string, { trades: number; wins: number; total_pnl: number; win_rate: number }>
}

export interface SnapshotData {
  total_value: number
  cash: number
  positions_value: number
  timestamp: string
}

export interface MarketData {
  id: string
  question: string
  category: string
  outcome_yes_price: number
  outcome_no_price: number
  volume_24h: number
  liquidity: number
  spread: number
  resolution_date: string | null
}
