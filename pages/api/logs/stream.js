const PYTHON_API_URL = process.env.PYTHON_API_URL

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).end()
  }

  if (!PYTHON_API_URL) {
    return res.status(503).json({ error: 'UPSTREAM_NOT_CONFIGURED' })
  }

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('X-Accel-Buffering', 'no')
  res.flushHeaders()

  let upstream
  try {
    upstream = await fetch(`${PYTHON_API_URL}/logs/stream`, {
      headers: { Accept: 'text/event-stream' },
    })
  } catch {
    res.write('data: {"level":"ERROR","message":"Cannot connect to Python service"}\n\n')
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
  } catch {
    // client disconnected
  } finally {
    res.end()
  }
}
