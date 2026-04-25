import { useState, useEffect, useRef } from 'react'

const MAX_LINES = 150

export function useLogStream(active) {
  const [lines, setLines] = useState([])
  const esRef = useRef(null)

  useEffect(() => {
    if (!active) return

    const es = new EventSource('/api/logs/stream')
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data)
        setLines(prev => {
          const next = [...prev, entry]
          return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
        })
      } catch {
        // keepalive or malformed — skip
      }
    }

    es.onerror = () => {
      setLines(prev => [...prev, {
        timestamp: new Date().toISOString(),
        level: 'ERROR',
        message: 'Log stream disconnected',
      }])
      es.close()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [active])

  const clear = () => setLines([])

  return { lines, clear }
}
