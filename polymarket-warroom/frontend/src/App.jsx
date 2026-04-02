import React, { useState, useEffect, useRef, useCallback } from 'react'
import Dashboard from './components/Dashboard'

const API = '/api'

function useWebSocket() {
  const [wsData, setWsData] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectRef = useRef(null)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      reconnectRef.current = setTimeout(connect, 3000)
    }
    ws.onmessage = (e) => {
      try {
        setWsData(JSON.parse(e.data))
      } catch {}
    }

    wsRef.current = ws
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
    }
  }, [connect])

  return { wsData, connected }
}

function App() {
  const [status, setStatus] = useState(null)
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  const [signals, setSignals] = useState([])
  const [activity, setActivity] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [postMortem, setPostMortem] = useState(null)
  const { wsData, connected } = useWebSocket()

  const fetchAll = useCallback(async () => {
    try {
      const [s, p, t, sig, act, m, pm] = await Promise.all([
        fetch(`${API}/status`).then(r => r.json()),
        fetch(`${API}/positions`).then(r => r.json()),
        fetch(`${API}/trades`).then(r => r.json()),
        fetch(`${API}/signals`).then(r => r.json()),
        fetch(`${API}/activity`).then(r => r.json()),
        fetch(`${API}/metrics`).then(r => r.json()),
        fetch(`${API}/post-mortem`).then(r => r.json()),
      ])
      setStatus(s)
      setPositions(p.positions || [])
      setTrades(t.trades || [])
      setSignals(sig.signals || [])
      setActivity(act.activity || [])
      setMetrics(m)
      setPostMortem(pm)
    } catch (err) {
      console.error('Fetch error:', err)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 5000)
    return () => clearInterval(interval)
  }, [fetchAll])

  // Update from WebSocket
  useEffect(() => {
    if (wsData?.type === 'status') {
      setStatus(prev => prev ? { ...prev, portfolio: { ...prev.portfolio, ...wsData.data } } : prev)
    }
    if (wsData?.type === 'activity') {
      setActivity(prev => [...prev.slice(-49), wsData.data])
    }
  }, [wsData])

  const handleAction = async (action, params) => {
    const url = params
      ? `${API}/${action}?${new URLSearchParams(params)}`
      : `${API}/${action}`
    await fetch(url, { method: 'POST' })
    setTimeout(fetchAll, 500)
  }

  return (
    <Dashboard
      status={status}
      positions={positions}
      trades={trades}
      signals={signals}
      activity={activity}
      metrics={metrics}
      postMortem={postMortem}
      connected={connected}
      onAction={handleAction}
      onRefresh={fetchAll}
    />
  )
}

export default App
