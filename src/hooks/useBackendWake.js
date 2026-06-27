import { useEffect, useRef, useState } from 'react'

// Render's free tier spins the Python backend down when idle, so the first
// request after a cold start hangs for ~30–60s. This hook pings /api/wake
// (which proxies the backend's /health) on mount and keeps retrying until it
// gets a definitive `healthy` — the UI gates the search form behind it until
// then, so the user never fires a search into a sleeping backend.
const POLL_DELAY_MS = 2500
const MAX_ATTEMPTS = 48 // ~ a few minutes including the server-side cold-start wait

export function useBackendWake() {
  const [state, setState] = useState('warming') // warming | ready | error
  const [attempt, setAttempt] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const runningRef = useRef(false)
  const cancelledRef = useRef(false)

  async function run() {
    if (runningRef.current) return
    runningRef.current = true
    cancelledRef.current = false
    setState('warming')
    setAttempt(0)
    setElapsed(0)

    const startedAt = Date.now()
    const ticker = setInterval(() => {
      if (!cancelledRef.current) setElapsed(Math.round((Date.now() - startedAt) / 1000))
    }, 1000)

    try {
      for (let i = 1; i <= MAX_ATTEMPTS; i++) {
        if (cancelledRef.current) return
        setAttempt(i)
        try {
          const res = await fetch('/api/wake', { cache: 'no-store' })
          const data = await res.json().catch(() => ({}))
          if (data.status === 'healthy') {
            if (!cancelledRef.current) setState('ready')
            return
          }
        } catch {
          // network hiccup mid cold-start — fall through and retry
        }
        if (i < MAX_ATTEMPTS) await new Promise(r => setTimeout(r, POLL_DELAY_MS))
      }
      if (!cancelledRef.current) setState('error')
    } finally {
      clearInterval(ticker)
      runningRef.current = false
    }
  }

  useEffect(() => {
    run()
    return () => { cancelledRef.current = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { state, attempt, elapsed, run }
}
