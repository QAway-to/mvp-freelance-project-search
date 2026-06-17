const { requireAuth } = require('../../../../lib/auth')
const { generateCp } = require('../../../lib/pythonClient')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { description, budget, title } = req.body
  if (!description) {
    return res.status(400).json({ error: 'description required' })
  }

  const result = await generateCp({ description, budget, title })

  if (!result.proposal) {
    return res.status(502).json({ error: 'CP generation failed' })
  }

  return res.status(200).json({ proposal: result.proposal })
}