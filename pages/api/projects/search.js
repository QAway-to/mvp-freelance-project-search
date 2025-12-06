// API endpoint for searching freelance projects
// Note: This uses mock data for demonstration
// Replace with actual API integration for production

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { keywords, timeLeft, hiredMin, proposalsMax } = req.body;

    if (!keywords || !keywords.trim()) {
      return res.status(400).json({
        status: 'error',
        message: 'Keywords are required',
      });
    }

    // Simulate search delay
    await new Promise(resolve => setTimeout(resolve, 1500));

    // Mock projects data
    const mockProjects = [
      {
        title: `Проект по теме "${keywords}"`,
        description: `Детальное описание проекта связанного с ключевыми словами: ${keywords}. Требуется выполнение задач связанных с разработкой и консалтингом.`,
        budget: '15 000 ₽',
        url: 'https://kwork.ru/projects/123456/view',
        evaluation: {
          totalScore: 0.85,
          relevanceScore: 0.9,
          timeScore: 0.8,
          proposalsScore: 0.85,
          reasoning: 'High relevance match with good project metrics',
        },
        timeLeft: 12,
        hired: 35,
        proposals: 3,
      },
      {
        title: `Заказ: ${keywords}`,
        description: `Ищем специалиста для работы над проектом. Требования: опыт работы с указанными технологиями, ответственность, соблюдение сроков.`,
        budget: '20 000 ₽',
        url: 'https://kwork.ru/projects/123457/view',
        evaluation: {
          totalScore: 0.72,
          relevanceScore: 0.75,
          timeScore: 0.7,
          proposalsScore: 0.7,
          reasoning: 'Good match with acceptable metrics',
        },
        timeLeft: 24,
        hired: 45,
        proposals: 5,
      },
      {
        title: `Нужен ${keywords}`,
        description: `Описание проекта и требований к исполнителю. Детальная информация о задачах и ожидаемых результатах.`,
        budget: '10 000 ₽',
        url: 'https://kwork.ru/projects/123458/view',
        evaluation: {
          totalScore: 0.65,
          relevanceScore: 0.7,
          timeScore: 0.6,
          proposalsScore: 0.65,
          reasoning: 'Moderate relevance with standard metrics',
        },
        timeLeft: 36,
        hired: 50,
        proposals: 8,
      },
    ];

    // Apply filters
    let filteredProjects = mockProjects;

    if (timeLeft !== null && timeLeft !== undefined) {
      filteredProjects = filteredProjects.filter(p => p.timeLeft <= timeLeft);
    }

    if (hiredMin !== null && hiredMin !== undefined) {
      filteredProjects = filteredProjects.filter(p => p.hired >= hiredMin);
    }

    if (proposalsMax !== null && proposalsMax !== undefined) {
      filteredProjects = filteredProjects.filter(p => p.proposals <= proposalsMax);
    }

    // Sort by relevance score
    filteredProjects.sort((a, b) => {
      const scoreA = a.evaluation?.totalScore || 0;
      const scoreB = b.evaluation?.totalScore || 0;
      return scoreB - scoreA;
    });

    return res.status(200).json({
      status: 'success',
      projects: filteredProjects,
      total: filteredProjects.length,
    });

  } catch (error) {
    console.error('Search error:', error);
    return res.status(500).json({
      status: 'error',
      message: error.message || 'Search failed',
    });
  }
}

