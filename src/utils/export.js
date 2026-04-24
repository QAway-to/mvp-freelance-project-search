export function projectsToJson(projects) {
  return JSON.stringify(projects, null, 2)
}

export function projectsToCsv(projects) {
  if (!projects.length) return ''
  const headers = ['title', 'budget', 'timeLeft', 'hired', 'proposals', 'url', 'score']
  const escape = (val) => {
    const str = val == null ? '' : String(val)
    return str.includes(',') || str.includes('"') || str.includes('\n')
      ? `"${str.replace(/"/g, '""')}"`
      : str
  }
  const rows = projects.map(p =>
    headers.map(h => {
      if (h === 'score') {
        const raw = p.evaluation?.totalScore
        return escape(raw != null ? (raw * 100).toFixed(0) + '%' : '')
      }
      return escape(p[h])
    }).join(',')
  )
  return '﻿' + [headers.join(','), ...rows].join('\n')
}

export function downloadFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
