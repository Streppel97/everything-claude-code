import { useEffect, useRef, useState, useCallback } from 'react'

interface WSMessage {
  type: string
  data: unknown
  timestamp: string
}

export function useWebSocket(url = 'ws://localhost:8000/ws') {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)
  const reconnectTimeoutRef = useRef<number>()
  const reconnectDelay = useRef(1000)

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        reconnectDelay.current = 1000
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSMessage
          setLastMessage(msg)
        } catch {
          // ignore non-JSON messages
        }
      }

      ws.onclose = () => {
        setConnected(false)
        // Auto-reconnect with exponential backoff
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30000)
          connect()
        }, reconnectDelay.current)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      // connection failed, will retry via onclose
    }
  }, [url])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { connected, lastMessage, send }
}
