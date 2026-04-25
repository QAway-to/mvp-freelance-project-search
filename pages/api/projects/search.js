const { searchProjects } = require('../../../lib/pythonClient')
const { normalizeProject } = require('../../../lib/normalizers')

function parseBudgetAmount(budgetStr) {
  if (!budgetStr) return null
  const digits = budgetStr.replace(/\D/g, '')
  return digits ? parseInt(digits, 10) : null
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { keywords, category, timeLeft, budgetMin, hiredMin, proposalsMax } = req.body

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

  let projects = (result.data || []).map(normalizeProject)

  if (budgetMin) {
    const min = parseInt(budgetMin, 10)
    projects = projects.filter(p => {
      const amount = parseBudgetAmount(p.budget)
      return amount === null || amount >= min
    })
  }

  return res.status(200).json({
    status: 'success',
    projects,
    total: projects.length,
  })
}
