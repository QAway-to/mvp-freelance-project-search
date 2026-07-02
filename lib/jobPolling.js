// Client-side job polling for long-running scrapes.
//
// The UI runs inside a Telegram-miniapp WebView: any long HTTP request dies on
// app switch / screen lock / Wi-Fi↔LTE handover, and Render's edge kills
// byte-less responses at ~100s. So a search is started as a server-side job and
// consumed via short polls. Every poll is independent — a suspended WebView
// just resumes polling from its `since` cursor when the user comes back.

const POLL_INTERVAL_MS = 3000
const POLL_BACKOFF_MAX_MS = 12000
const POLL_DEADLINE_MS = 20 * 60_000 // worst-case Kwork scrape (~15 min) + buffer
const START_ATTEMPTS = 4             // start retries ride out a free-tier cold start
const START_RETRY_BASE_MS = 3000
const MAX_FAIL_STREAK = 20           // consecutive poll failures before giving up

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// AbortSignal.timeout needs WebView/Chromium ≥103 — older Telegram WebViews
// (esp. iOS WKWebView on old OS builds) lack it, and a synchronous throw here
// would burn the whole retry budget on an error that never resolves.
function timeoutSignal(ms) {
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    return AbortSignal.timeout(ms)
  }
  if (typeof AbortController === 'undefined') return undefined
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

// Resolves after `ms`, or as soon as the page becomes visible again — so a
// user returning to the miniapp gets the next poll immediately instead of
// waiting out a backoff that grew while the WebView was frozen.
function sleepResumeAware(ms) {
  if (typeof document === 'undefined') return sleep(ms)
  return new Promise(resolve => {
    let timer = null
    const done = () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
      resolve()
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') done()
    }
    timer = setTimeout(done, ms)
    document.addEventListener('visibilitychange', onVisible)
  })
}

async function startJob(startPath, { headers, body }) {
  let lastError = new Error('start failed')
  for (let attempt = 0; attempt < START_ATTEMPTS; attempt++) {
    let res = null
    try {
      res = await fetch(startPath, {
        method: 'POST',
        headers,
        body,
        signal: timeoutSignal(95_000),
      })
    } catch (err) {
      res = null
      lastError = err // network error / timeout — retryable (cold start)
    }
    if (res) {
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.jobId) return data.jobId
      lastError = new Error(data.message || `start failed (HTTP ${res.status})`)
      // 4xx = permanent (bad params, auth) — retrying can't fix it, fail fast.
      if (res.status >= 400 && res.status < 500) throw lastError
    }
    if (attempt < START_ATTEMPTS - 1) {
      // Server may be cold-starting (60–90s on the free tier); creating a job is
      // idempotent thanks to server-side single-flight, so retrying is safe.
      await sleepResumeAware(START_RETRY_BASE_MS * (attempt + 1))
    }
  }
  throw lastError
}

// Starts a job and polls it to completion, feeding each batch to onBatch.
// Resolves when the job is done/cancelled; rejects on job error, fatal
// JOB_NOT_FOUND (err.code === 'JOB_NOT_FOUND' — the backend restarted), too
// many consecutive poll failures, or the overall deadline.
async function pollJob({ startPath, statusPath, headers, body, onBatch, onProgress }) {
  const jobId = await startJob(startPath, { headers, body })

  let since = 0
  let failStreak = 0
  let delay = POLL_INTERVAL_MS
  const deadline = Date.now() + POLL_DEADLINE_MS

  while (Date.now() < deadline) {
    await sleepResumeAware(delay)

    let data
    try {
      const res = await fetch(
        `${statusPath}?jobId=${encodeURIComponent(jobId)}&since=${since}`,
        { headers, signal: timeoutSignal(20_000) },
      )
      if (res.status === 404) {
        const err = new Error('JOB_NOT_FOUND')
        err.code = 'JOB_NOT_FOUND'
        throw err
      }
      data = await res.json()
      if (!res.ok) {
        const err = new Error(data.message || `poll failed (HTTP ${res.status})`)
        // Other 4xx (bad request, auth) are permanent — don't burn retries.
        if (res.status >= 400 && res.status < 500) err.fatal = true
        throw err
      }
    } catch (err) {
      if (err.code === 'JOB_NOT_FOUND' || err.fatal) throw err
      // Transient poll failure (suspend, flaky mobile network, edge hiccup):
      // the job keeps running server-side — back off and keep polling.
      failStreak += 1
      if (failStreak >= MAX_FAIL_STREAK) {
        throw new Error('Связь с сервером потеряна — попробуйте ещё раз')
      }
      delay = Math.min(delay * 2, POLL_BACKOFF_MAX_MS)
      continue
    }

    failStreak = 0
    delay = POLL_INTERVAL_MS
    // Cursor must never go backwards — duplicates would reappear in the UI.
    since = Math.max(since, Number(data.nextSince) || 0)

    const batch = data.projects || data.items || []
    if (batch.length && onBatch) onBatch(batch)
    if (data.progress && onProgress) onProgress(data.progress)

    if (data.jobStatus === 'done' || data.jobStatus === 'cancelled') {
      return { truncated: !!data.truncated }
    }
    if (data.jobStatus === 'error') {
      throw new Error(data.jobError || 'Поиск завершился с ошибкой')
    }
  }

  throw new Error('Поиск не завершился за отведённое время — попробуйте сузить фильтры')
}

module.exports = { pollJob }
