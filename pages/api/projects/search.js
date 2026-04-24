const { searchProjects } = require('../../../lib/pythonClient')
const { normalizeProject } = require('../../../lib/normalizers')

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { keywords, category, timeLeft, hiredMin, proposalsMax } = req.body

  if (!keywords || !keywords.trim()) {
    return res.status(400).json({ status: 'error', message: 'Keywords are required' })
  }

  let result
  try {
    result = await searchProjects({ keywords, category, timeLeft, hiredMin, proposalsMax })
  } catch {
    return res.status(502).json({ status: 'error', message: 'UPSTREAM_DOWN' })
  }

  if (!result.success) {
    const statusCode =
      result.error === 'UPSTREAM_TIMEOUT' ? 504
      : result.error === 'UPSTREAM_NOT_CONFIGURED' ? 503
      : 502
    return res.status(statusCode).json({
      status: 'error',
      message: result.error || 'Search failed',
    })
  }

  const projects = (result.data || []).map(normalizeProject)

  return res.status(200).json({
    status: 'success',
    projects,
    total: result.meta?.total ?? projects.length,
  })
}
