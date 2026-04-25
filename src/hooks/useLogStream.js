import { useState, useEffect, useRef } from 'react'

const MAX_LINES = 150

function computeProgress(message) {
  if (!message) return null
  const m = message.toLowerCase()

  // Session complete
  if (m.includes('session completed') || m.includes('session complete') || m.includes('monitoring stopped')) return 100

  // Semantic evaluation / ranking
  if (m.includes('[semantic]') || m.includes('semantic evaluation') || m.includes('ranking')) return 85

  // Processing individual project pages — extract N/M
  const procMatch = message.match(/(\d+)\/(\d+)/i)
  if (procMatch && (m.includes('processing') || m.includes('project') || m.includes('evaluating'))) {
    const n = parseInt(procMatch[1], 10)
    const total = parseInt(procMatch[2], 10)
    if (total > 0) return Math.round(35 + (n / total) * 45)
  }

  // Found projects on listing page
  if (m.includes('found') && m.includes('project')) return 35
  if (m.includes('cards for query')) return 35

  // Page loaded / navigating to search
  if (m.includes('page') && m.includes('loaded')) return 25
  if (m.includes('navigating to page') || m.includes('real search mode')) return 20

  // Auth
  if (m.includes('[auth]') || m.includes('logged in') || m.includes('login')) return 15

  // Browser setup
  if (m.includes('[selenium]') || m.includes('chrome') || m.includes('browser setup')) return 5

  return null
}

// Fallback timeline when SSE messages don't arrive in real-time
const PROGRESS_TIMELINE = [
  [1500,  5,  '// браузер запускается...'],
  [4000,  15, '// авторизация...'],
  [9000,  25, '// загрузка страницы...'],
  [14000, 35, '// поиск проектов...'],
  [20000, 50, '// обработка карточек...'],
  [35000, 70, '// семантическая оценка...'],
  [55000, 85, '// финализация...'],
  [85000, 95, '// почти готово...'],
]

export function useLogStream(active) {
  const [lines, setLines] = useState([])
  const [progress, setProgress] = useState(0)
  const [lastMsg, setLastMsg] = useState('')
  const esRef = useRef(null)
  const realProgressRef = useRef(0)

  useEffect(() => {
    if (!active) return
    setLines([])
    setProgress(0)
    setLastMsg('')
    realProgressRef.current = 0

    const es = new EventSource('/api/logs/stream')
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data)
        if (!entry?.message) return

        setLines(prev => {
          const next = [...prev, entry]
          return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
        })
        setLastMsg(entry.message)

        const p = computeProgress(entry.message)
        if (p !== null) {
          realProgressRef.current = p
          setProgress(p)
        }
      } catch {
        // keepalive — skip
      }
    }

    es.onerror = () => {
      setLastMsg('Log stream disconnected')
      es.close()
    }

    // Fallback timers: advance progress/message when SSE is silent
    const timers = PROGRESS_TIMELINE.map(([delay, p, msg]) =>
      setTimeout(() => {
        if (realProgressRef.current < p) {
          setProgress(p)
          setLastMsg(msg)
        }
      }, delay)
    )

    return () => {
      es.close()
      esRef.current = null
      timers.forEach(clearTimeout)
    }
  }, [active])

  // Mark 100% when loading finishes
  useEffect(() => {
    if (!active) setProgress(p => (p > 0 ? 100 : p))
  }, [active])

  return { lines, progress, lastMsg }
}
