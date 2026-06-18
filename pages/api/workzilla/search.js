const { requireAuth } = require('../../../lib/auth')
const PYTHON_API_URL = process.env.PYTHON_API_URL

export default async function handler(req, res) {
  if (requireAuth(req, res)) return
  if (req.method !== 'POST') return res.status(405).end()

  if (!PYTHON_API_URL) {
    res.write('data: {"error":"UPSTREAM_NOT_CONFIGURED"}\n\n')
    res.write('data: {"done":true}\n\n')
    return res.end()
  }

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('X-Accel-Buffering', 'no')
  res.flushHeaders()

  let upstream
  try {
    upstream = await fetch(`${PYTHON_API_URL}/api/workzilla/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(600_000),
    })
  } catch {
    res.write('data: {"error":"Cannot connect to Python service"}\n\n')
    res.write('data: {"done":true}\n\n')
    return res.end()
  }

  const reader = upstream.body.getReader()
  const decoder = new TextDecoder()
  req.on('close', () => reader.cancel())

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      res.write(decoder.decode(value))
    }
  } catch {}
  finally { res.end() }
}
