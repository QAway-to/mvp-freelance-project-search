const { requireAuth } = require('../../../lib/auth')
const { parseProject } = require('../../../lib/pythonClient')
const { normalizeProject } = require('../../../lib/normalizers')

// project view URL, new_offer URL, or a bare project id (backend extracts the id)
const KWORK_URL_PATTERN = /(?:kwork\.ru\/projects\/\d+|kwork\.ru\/new_offer\?project=\d+|^\s*\d+\s*$)/

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { url } = req.body

  if (!url || !url.trim()) {
    return res.status(400).json({ status: 'error', message: 'URL is required' })
  }

  if (!KWORK_URL_PATTERN.test(url.trim())) {
    return res.status(400).json({
      status: 'error',
      message: 'Expected kwork.ru/projects/ID, kwork.ru/new_offer?project=ID, or a project ID',
    })
  }

  let result
  try {
    result = await parseProject(url.trim())
  } catch {
    return res.status(502).json({ status: 'error', message: 'UPSTREAM_DOWN' })
  }

  if (!result.success) {
    const statusCode =
      result.error === 'UPSTREAM_TIMEOUT' ? 504
      : result.error === 'UPSTREAM_NOT_CONFIGURED' ? 503
      : result.error === 'PARSE_FAILED' ? 422
      : 502
    return res.status(statusCode).json({ status: 'error', message: result.error || 'Failed to parse project' })
  }

  return res.status(200).json({ status: 'success', project: normalizeProject(result.data) })
}