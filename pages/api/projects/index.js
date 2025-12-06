// API endpoint for getting all found projects
export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // This endpoint would return stored projects
  // For MVP, return empty array
  return res.status(200).json({
    status: 'success',
    projects: [],
    total: 0,
  });
}

