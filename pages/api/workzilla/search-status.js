const { requireAuth } = require('../../../lib/auth')
const { getWorkzillaJobStatus } = require('../../../lib/pythonClient')

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
    result = await getWorkzillaJobStatus(jobId, req.query.since)
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

  // Items pass through raw: the stream mixes project cards with {_update, description}
  // enrich events, and the frontend already merges those by id (SSE-era logic).
  return res.status(200).json({
    status: 'success',
    jobStatus: result.status,
    truncated: !!result.truncated,
    items: result.results || [],
    nextSince: result.next_since,
    total: result.total,
    jobError: result.error || null,
  })
}
