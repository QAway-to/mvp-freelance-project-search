async function request(path, options = {}, timeoutMs = 30_000) {
  const PYTHON_API_URL = process.env.PYTHON_API_URL

  if (!PYTHON_API_URL) {
    return { success: false, error: 'UPSTREAM_NOT_CONFIGURED' }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${PYTHON_API_URL}${path}`, {
      ...options,
      signal: controller.signal,
    })

    if (!response.ok) {
      return { success: false, error: 'UPSTREAM_ERROR', status: response.status }
    }

    return await response.json()
  } catch (err) {
    if (err.name === 'AbortError') {
      return { success: false, error: 'UPSTREAM_TIMEOUT' }
    }
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

async function searchProjects({ keywords, timeLeft, hiredMin, proposalsMax }) {
  return request('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords, timeLeft, hiredMin, proposalsMax }),
  }, 300_000)
}

async function getProjects() {
  return request('/projects')
}

async function generateCp({ description, budget, title }) {
  return request('/agent/generate-cp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, budget, title }),
  }, 60_000)
}

async function submitRespond({ url, cp_text }) {
  return request('/api/respond', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, cp_text }),
  }, 60_000)
}

module.exports = { parseProject, searchProjects, getProjects, generateCp, submitRespond }
