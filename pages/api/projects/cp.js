const { requireAuth } = require('../../../lib/auth')
const { generateCp } = require('../../../lib/pythonClient')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { description, budget, title, files } = req.body
  if (!description) {
    return res.status(400).json({ error: 'description required' })
  }

  let result
  try {
    result = await generateCp({ description, budget, title, files })
  } catch {
    return res.status(502).json({ error: 'UPSTREAM_DOWN' })
  }

  if (!result.proposal) {
    // Forward the real reason so the UI can stop blaming the API key for what
    // are usually cold-start / timeout failures (backend generates CP fine).
    const statusCode =
      result.error === 'UPSTREAM_TIMEOUT' ? 504
      : result.error === 'UPSTREAM_NOT_CONFIGURED' ? 503
      : result.error === 'UPSTREAM_DOWN' ? 502
      // Real backend non-2xx (e.g. 500 from a generation exception) — pass the
      // actual status through so the UI shows a genuine failure, not "down".
      : result.error === 'UPSTREAM_ERROR' ? (result.status || 502)
      : 502
    return res.status(statusCode).json({ error: result.error || 'CP generation failed' })
  }

  return res.status(200).json({ proposal: result.proposal })
}