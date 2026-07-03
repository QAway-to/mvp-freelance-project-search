const { requireAuth } = require('../../../lib/auth')
const { getRespondJobStatus } = require('../../../lib/pythonClient')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const jobId = (req.query.jobId || '').trim()
  if (!jobId) {
    return res.status(400).json({ status: 'error', message: 'jobId required' })
  }

  let result
  try {
    result = await getRespondJobStatus(jobId, req.query.since)
  } catch {
    return res.status(502).json({ status: 'error', message: 'UPSTREAM_DOWN' })
  }

  if (!result.success) {
    if (result.status === 404) {
      return res.status(404).json({ status: 'error', message: 'JOB_NOT_FOUND' })
    }
    const statusCode = result.error === 'UPSTREAM_TIMEOUT' ? 504 : 502
    return res.status(statusCode).json({ status: 'error', message: result.error || 'Poll failed' })
  }

  // The outcome dict is delivered as a single-item `items` array so the shared
  // pollJob helper (which reads data.projects || data.items) picks it up.
  const outcome = result.outcome || null
  return res.status(200).json({
    status: 'success',
    jobStatus: result.status,
    items: outcome ? [outcome] : [],
    nextSince: result.next_since,
    jobError: result.error || null,
  })
}
