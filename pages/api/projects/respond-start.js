const { requireAuth } = require('../../../lib/auth')
const { createRespondJob } = require('../../../lib/pythonClient')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { url, cp_text, duration, title, description } = req.body
  if (!url || !cp_text) {
    return res.status(400).json({ status: 'error', message: 'url and cp_text required' })
  }

  let result
  try {
    result = await createRespondJob({ url, cp_text, duration, title, description })
  } catch {
    return res.status(502).json({ status: 'error', message: 'UPSTREAM_DOWN' })
  }

  if (!result.success) {
    const statusCode =
      result.error === 'UPSTREAM_TIMEOUT' ? 504
      : result.error === 'UPSTREAM_NOT_CONFIGURED' ? 503
      : 502
    return res.status(statusCode).json({ status: 'error', message: result.error || 'Start failed' })
  }

  return res.status(200).json({ status: 'success', jobId: result.job_id, reused: !!result.reused })
}
