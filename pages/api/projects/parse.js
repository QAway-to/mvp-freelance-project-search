// API endpoint for parsing a single project by URL
// Note: This uses mock data for demonstration
// Replace with actual parsing logic (Selenium/Puppeteer) for production

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { url } = req.body;

    if (!url || !url.trim()) {
      return res.status(400).json({
        status: 'error',
        message: 'URL is required',
      });
    }

    // Validate Kwork URL
    const kworkUrlPattern = /^https:\/\/kwork\.ru\/projects\/(\d+)\/view$/;
    const match = url.trim().match(kworkUrlPattern);

    if (!match) {
      return res.status(400).json({
        status: 'error',
        message: 'Invalid Kwork URL format. Expected: https://kwork.ru/projects/XXXXX/view',
      });
    }

    const projectId = match[1];

    // Simulate parsing delay
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Mock parsed project data
    const mockProject = {
      title: `Parsed Project #${projectId}`,
      description: `This is a parsed project from Kwork. Project ID: ${projectId}. Detailed description of the project requirements, tasks, and expected deliverables.`,
      budget: '25 000 ₽',
      url: url,
      projectId: projectId,
      loadedFromUrl: true,
      evaluation: {
        totalScore: 0.88,
        relevanceScore: 0.9,
        timeScore: 0.85,
        proposalsScore: 0.9,
        reasoning: 'Project loaded successfully with good metrics',
      },
      timeLeft: 18,
      hired: 30,
      proposals: 4,
    };

    return res.status(200).json({
      status: 'success',
      project: mockProject,
    });

  } catch (error) {
    console.error('Parse error:', error);
    return res.status(500).json({
      status: 'error',
      message: error.message || 'Failed to parse project',
    });
  }
}

