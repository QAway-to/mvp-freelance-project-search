const PYTHON_API_URL = process.env.PYTHON_API_URL

export default async function handler(req, res) {
  if (!PYTHON_API_URL) return res.status(200).json({ status: 'no_url' })
  try {
    const upstream = await fetch(`${PYTHON_API_URL}/health`, {
      signal: AbortSignal.timeout(90_000),
    })
    const data = await upstream.json()
    return res.status(200).json(data)
  } catch (err) {
    return res.status(200).json({ status: 'timeout', detail: err.message })
  }
}
