async function request(path, options = {}, timeoutMs = 30_000) {
  const PYTHON_API_URL = process.env.PYTHON_API_URL

  if (!PYTHON_API_URL) {
    console.error(`[upstream] ${path} -> UPSTREAM_NOT_CONFIGURED (PYTHON_API_URL missing)`)
    return { success: false, error: 'UPSTREAM_NOT_CONFIGURED' }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const startedAt = Date.now()

  try {
    const response = await fetch(`${PYTHON_API_URL}${path}`, {
      ...options,
      signal: controller.signal,
    })

    if (!response.ok) {
      console.error(`[upstream] ${path} -> HTTP ${response.status} after ${Date.now() - startedAt}ms`)
      return { success: false, error: 'UPSTREAM_ERROR', status: response.status }
    }

    return await response.json()
  } catch (err) {
    const ms = Date.now() - startedAt
    if (err.name === 'AbortError') {
      console.error(`[upstream] ${path} -> UPSTREAM_TIMEOUT after ${ms}ms (limit ${timeoutMs}ms)`)
      return { success: false, error: 'UPSTREAM_TIMEOUT' }
    }
    // This is the server-side twin of the browser's "Failed to fetch": when the
    // Python backend is down/cold, undici throws here. Log the real cause.
    console.error(`[upstream] ${path} -> UPSTREAM_DOWN after ${ms}ms: ${err.name}: ${err.message}`)
    return { success: false, error: 'UPSTREAM_DOWN' }
  } finally {
    clearTimeout(timer)
  }
}

async function parseProject(url) {
  return request('/api/parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
}

async function searchProjects({ keywords, timeLeft, hiredMin, proposalsMax, budgetMin, budgetMax, categories }) {
  return request('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords, timeLeft, hiredMin, proposalsMax, budgetMin, budgetMax, categories }),
  }, 300_000)
}

async function getProjects() {
  return request('/projects')
}

async function generateCp({ description, budget, title, files }) {
  return request('/agent/generate-cp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, budget, title, files }),
  }, 120_000)
}

async function submitRespond({ url, cp_text, duration, title, description }) {
  // Offer submit drives a real Selenium browser (Chrome form render ~45s + fill +
  // submit); keep a generous timeout so the UI waits instead of showing a false error.
  return request('/api/respond', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, cp_text, duration, title, description }),
  }, 240_000)
}

async function searchWorkzilla() {
  return request('/api/workzilla/search', { method: 'POST', headers: { 'Content-Type': 'application/json' } }, 600_000)
}

// ── Job-based search (poll delivery) ─────────────────────────────────────────
// Create/poll are both SHORT requests by design: the multi-minute scrape lives
// server-side, so nothing here needs to outlast the Telegram-WebView suspend
// window or Render's ~100s edge cutoff. Create keeps 90s to ride out a
// free-tier cold start (Render queues the request while the service boots).

async function createSearchJob(params) {
  return request('/api/search/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  }, 90_000)
}

async function getSearchJobStatus(jobId, since = 0) {
  return request(`/api/search/jobs/${encodeURIComponent(jobId)}?since=${Number(since) || 0}`, {}, 15_000)
}

async function createWorkzillaJob() {
  return request('/api/workzilla/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' } }, 90_000)
}

async function getWorkzillaJobStatus(jobId, since = 0) {
  return request(`/api/workzilla/jobs/${encodeURIComponent(jobId)}?since=${Number(since) || 0}`, {}, 15_000)
}

async function submitWorkzillaRespond({ url, cp_text }) {
  return request('/api/workzilla/respond', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, cp_text }),
  }, 60_000)
}

module.exports = {
  parseProject,
  searchProjects,
  getProjects,
  generateCp,
  submitRespond,
  searchWorkzilla,
  submitWorkzillaRespond,
  createSearchJob,
  getSearchJobStatus,
  createWorkzillaJob,
  getWorkzillaJobStatus,
}
