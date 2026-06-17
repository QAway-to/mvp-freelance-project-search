const PWD = process.env.WEBHOOK_PASSWORD

function isAuthenticated(req) {
  if (!PWD) return true
  const bearer = (req.headers['authorization'] ?? '').replace(/^Bearer\s+/i, '').trim()
  const header = (req.headers['x-webhook-password'] ?? '').trim()
  const query = (req.query?.token ?? '').trim()
  return bearer === PWD || header === PWD || query === PWD
}

function requireAuth(req, res) {
  if (isAuthenticated(req)) return false
  res.status(401).json({ error: 'Unauthorized' })
  return true
}

module.exports = { requireAuth }