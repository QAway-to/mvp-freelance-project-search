// Receives client-side error reports (see src/utils/clientLogger.js) and writes
// them to stderr so they appear in the Render logs for the kwork-ui service.
//
// Intentionally unauthenticated: it's reached via navigator.sendBeacon, which
// can't set the x-webhook-password header. The body is size-capped to keep this
// from being turned into a log-spam amplifier.

export const config = { api: { bodyParser: { sizeLimit: '8kb' } } }

export default function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { event, endpoint, message, page, userAgent, ts } = req.body || {}

  console.error('[client-error]', JSON.stringify({
    event: event || 'unknown',
    endpoint: endpoint || null,
    message: message || null,
    page: page || null,
    userAgent: userAgent || null,
    ts: ts || new Date().toISOString(),
  }))

  return res.status(204).end()
}
