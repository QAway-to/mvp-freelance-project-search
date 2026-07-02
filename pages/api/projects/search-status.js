const { requireAuth } = require('../../../lib/auth')
const { getSearchJobStatus } = require('../../../lib/pythonClient')
const { normalizeProject } = require('../../../lib/normalizers')

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
    result = await getSearchJobStatus(jobId, req.query.since)
  } catch {
    return res.status(502).json({ status: 'error', message: 'UPSTREAM_DOWN' })
  }

  if (!result.success) {
    // 404 = the backend restarted (in-memory job store) — the client shows
    // a distinct "server restarted, retry" message instead of a generic error.
    if (result.status === 404) {
      return res.status(404).json({ status: 'error', message: 'JOB_NOT_FOUND' })
    }
    const statusCode = result.error === 'UPSTREAM_TIMEOUT' ? 504 : 502
    return res.status(statusCode).json({ status: 'error', message: result.error || 'Poll failed' })
  }

  const projects = (result.results || []).map(normalizeProject)
  return res.status(200).json({
    status: 'success',
    jobStatus: result.status,
    progress: result.progress || null,
    truncated: !!result.truncated,
    projects,
    nextSince: result.next_since,
    total: result.total,
    jobError: result.error || null,
  })
}
