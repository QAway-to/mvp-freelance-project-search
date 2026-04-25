const PYTHON_API_URL = process.env.PYTHON_API_URL

export default async function handler(req, res) {
  if (!PYTHON_API_URL) {
    return res.status(503).json({ error: 'PYTHON_API_URL not set' })
  }

  try {
    const upstream = await fetch(`${PYTHON_API_URL}/debug`, {
      signal: AbortSignal.timeout(10_000),
    })
    const data = await upstream.json()
    return res.status(200).json(data)
  } catch (err) {
    return res.status(502).json({ error: 'upstream unreachable', detail: err.message })
  }
}
