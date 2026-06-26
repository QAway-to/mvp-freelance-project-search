const { requireAuth } = require('../../../lib/auth')
const { submitRespond } = require('../../../lib/pythonClient')

export default async function handler(req, res) {
  if (requireAuth(req, res)) return

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { url, cp_text, duration, title } = req.body
  if (!url || !cp_text) {
    return res.status(400).json({ success: false, message: 'url and cp_text required' })
  }

  const result = await submitRespond({ url, cp_text, duration, title })

  if (!result.success) {
    return res.status(422).json({ success: false, message: result.message || 'Failed to submit' })
  }

  return res.status(200).json({ success: true })
}