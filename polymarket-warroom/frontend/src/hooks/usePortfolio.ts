import { useState, useEffect, useCallback } from 'react'
import { api, PortfolioData, StatusData, StatsData, SnapshotData } from '../utils/api'

export function usePortfolio(refreshInterval = 10000) {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null)
  const [status, setStatus] = useState<StatusData | null>(null)
  const [stats, setStats] = useState<StatsData | null>(null)
  const [snapshots, setSnapshots] = useState<SnapshotData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [p, s, st, sn] = await Promise.all([
        api.getPortfolio(),
        api.getStatus(),
        api.getStats(),
        api.getSnapshots(24),
      ])
      setPortfolio(p)
      setStatus(s)
      setStats(st)
      setSnapshots(sn)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, refreshInterval)
    return () => clearInterval(interval)
  }, [refresh, refreshInterval])

  return { portfolio, status, stats, snapshots, loading, error, refresh }
}
