function normalizeProject(raw) {
  if (!raw || typeof raw !== 'object') {
    return {
      id: '',
      title: '',
      description: '',
      budget: null,
      url: '',
      proposals: null,
      hired: null,
      timeLeft: null,
      evaluation: null,
    }
  }

  const ev = raw.evaluation && typeof raw.evaluation === 'object' ? raw.evaluation : {}
  const reasons = Array.isArray(ev.reasons) ? ev.reasons : []

  return {
    id: raw.id ?? '',
    title: raw.title ?? '',
    description: raw.description ?? '',
    budget: raw.budget ?? null,
    url: raw.url ?? '',
    proposals: raw.proposals ?? null,
    hired: raw.hired ?? null,
    timeLeft: raw.timeLeft ?? raw.time_left ?? null,
    evaluation: {
      score: ev.score ?? null,
      reasons,
      suitable: ev.suitable ?? null,
    },
  }
}

module.exports = { normalizeProject }
