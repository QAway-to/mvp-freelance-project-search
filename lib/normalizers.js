function normalizePriceToString(price) {
  if (price == null) return null
  return new Intl.NumberFormat('ru-RU').format(price) + ' ₽'
}

function normalizeProject(raw) {
  const scores = raw.scores || {}
  return {
    id: raw.id,
    url: raw.url,
    title: raw.title,
    description: raw.description,
    budget: normalizePriceToString(raw.price),
    timeLeft: raw.timeLeft,
    hired: raw.hired,
    proposals: raw.proposals,
    evaluation: {
      totalScore: scores.totalScore != null ? scores.totalScore / 100 : 0,
      relevanceScore: scores.relevance != null ? scores.relevance / 100 : null,
      timeScore: scores.time != null ? scores.time / 100 : null,
      proposalsScore: scores.proposals != null ? scores.proposals / 100 : null,
      reasoning: null,
    },
  }
}

module.exports = { normalizeProject }
