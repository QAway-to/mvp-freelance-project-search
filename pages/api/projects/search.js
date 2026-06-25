const { requireAuth } = require('../../../lib/auth')
const { searchProjects } = require('../../../lib/pythonClient')
const { normalizeProject } = require('../../../lib/normalizers')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { keywords, timeLeft, hiredMin, proposalsMax, budgetMin, budgetMax, categories } = req.body

  let result
  try {
    result = await searchProjects({ keywords, timeLeft, hiredMin, proposalsMax, budgetMin, budgetMax, categories })
  } catch {
    return res.status(502).json({ status: 'error', message: 'UPSTREAM_DOWN' })
  }

  if (!result.success) {
    const statusCode =
      result.error === 'UPSTREAM_TIMEOUT' ? 504
      : result.error === 'UPSTREAM_NOT_CONFIGURED' ? 503
      : 502
    return res.status(statusCode).json({ status: 'error', message: result.error || 'Search failed' })
  }

  const projects = (result.data || []).map(normalizeProject)
  return res.status(200).json({ status: 'success', projects, total: projects.length })
}