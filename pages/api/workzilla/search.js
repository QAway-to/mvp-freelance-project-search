const { requireAuth } = require('../../../../lib/auth')
const { searchWorkzilla } = require('../../../lib/pythonClient')
const { normalizeProject } = require('../../../lib/normalizers')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const result = await searchWorkzilla()

  if (!result.success) {
    return res.status(502).json({ status: 'error', message: result.error || 'Search failed' })
  }

  const projects = (result.data || []).map(normalizeProject)
  return res.status(200).json({ status: 'success', projects, total: projects.length })
}