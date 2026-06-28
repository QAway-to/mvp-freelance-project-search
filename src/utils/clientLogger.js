// Reports client-side failures (most importantly `TypeError: Failed to fetch`)
// to the server so they land in the kwork-ui service logs on Render. A browser
// sandbox can't write files, so we ship the event to /api/client-log, which
// console.error's it to stderr — and on Render stderr IS the log stream.
//
// sendBeacon is tried first: it's fire-and-forget and survives page unload,
// which matters because these errors often coincide with the user navigating
// away or a flaky connection. A keepalive fetch is the fallback when sendBeacon
// is unavailable. Caveat: if the kwork-ui service itself is unreachable, this
// report can't get through either — it captures upstream/backend failures and
// transient errors, not a fully-down frontend.

/**
 * @param {string} event - short stable label, e.g. 'search_failed'
 * @param {{ endpoint?: string, message?: string, [k: string]: unknown }} [details]
 * @returns {void}
 */
export function logClientError(event, details = {}) {
  if (typeof window === 'undefined') return

  let payload
  try {
    payload = JSON.stringify({
      ...details,
      event,
      page: window.location.href,
      userAgent: navigator.userAgent,
      ts: new Date().toISOString(),
    })
  } catch {
    return
  }

  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' })
      if (navigator.sendBeacon('/api/client-log', blob)) return
    }
    fetch('/api/client-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(() => {})
  } catch {
    // Logging must never break the app.
  }
}
