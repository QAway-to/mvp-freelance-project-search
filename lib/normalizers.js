function normalizeProject(raw) {
  const ev = raw.evaluation || {}
  const reasons = Array.isArray(ev.reasons) ? ev.reasons : []
  return {
    id: raw.id,
    url: raw.url,
    title: raw.title,
    description: raw.description,
    budget: raw.budget || null,
    timeLeft: raw.timeLeft ?? raw.urgency_hours ?? null,
    hired: raw.hired ?? null,
    proposals: raw.proposals ?? null,
    evaluation: {
      totalScore: ev.score != null ? ev.score : 0,
      relevanceScore: ev.score != null ? ev.score : 0,
      timeScore: null,
      proposalsScore: null,
      reasoning: reasons.length > 0 ? reasons[0] : null,
    },
  }
}

module.exports = { normalizeProject }
