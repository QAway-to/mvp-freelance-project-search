const PYTHON_API_URL = process.env.PYTHON_API_URL

if (!PYTHON_API_URL) {
  console.error('[pythonClient] PYTHON_API_URL is not set — all upstream calls will fail.')
}

async function post(path, payload) {
  if (!PYTHON_API_URL) {
    return { success: false, error: 'UPSTREAM_NOT_CONFIGURED' }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 12_000)

  try {
    const response = await fetch(`${PYTHON_API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    clearTimeout(timer)

    if (!response.ok) {
      return { success: false, error: 'UPSTREAM_ERROR', status: response.status }
    }

    return await response.json()
  } catch (err) {
    clearTimeout(timer)
    if (err.name === 'AbortError') {
      return { success: false, error: 'UPSTREAM_TIMEOUT' }
    }
    return { success: false, error: 'UPSTREAM_DOWN' }
  }
}

async function searchProjects({ keywords, category, timeLeft, hiredMin, proposalsMax }) {
  return post('/api/search', { keywords, category, timeLeft, hiredMin, proposalsMax })
}

async function parseProject(url) {
  return post('/api/parse', { url })
}

module.exports = { searchProjects, parseProject }
