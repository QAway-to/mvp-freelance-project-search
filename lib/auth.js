const PWD = process.env.WEBHOOK_PASSWORD

/**
 * Returns true if request is authenticated.
 * Accepts: Authorization: Bearer <pwd>  OR  x-webhook-password: <pwd> header.
 * If WEBHOOK_PASSWORD is not set, always allows (dev mode).
 */
function isAuthenticated(req) {
  if (!PWD) return true
  const bearer = (req.headers['authorization'] ?? '').replace(/^Bearer\s+/i, '').trim()
  const header = (req.headers['x-webhook-password'] ?? '').trim()
  return bearer === PWD || header === PWD
}

function requireAuth(req, res) {
  if (isAuthenticated(req)) return false
  res.status(401).json({ error: 'Unauthorized' })
  return true
}

module.exports = { requireAuth }