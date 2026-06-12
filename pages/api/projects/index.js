const { getProjects } = require('../../../lib/pythonClient')

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const result = await getProjects()

  if (!result.success) {
    const statusCode =
      result.error === 'UPSTREAM_NOT_CONFIGURED' ? 503
      : result.error === 'UPSTREAM_TIMEOUT' ? 504
      : 502
    return res.status(statusCode).json({ status: 'error', message: result.error })
  }

  return res.status(200).json(result)
}
