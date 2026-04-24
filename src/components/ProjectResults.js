import { useState, useMemo } from 'react'
import ProjectCard from './ProjectCard'
import { projectsToJson, projectsToCsv, downloadFile } from '../utils/export'

const SORT_OPTIONS = [
  { value: 'score',    label: 'score' },
  { value: 'budget',   label: 'budget' },
  { value: 'timeLeft', label: 'time' },
]

function parseBudget(str) {
  if (!str) return 0
  const num = parseInt(str.replace(/\D/g, ''))
  return isNaN(num) ? 0 : num
}

export default function ProjectResults({ projects }) {
  const [sortBy, setSortBy] = useState('score')
  const [sortDir, setSortDir] = useState('desc')

  const sorted = useMemo(() => {
    return [...projects].sort((a, b) => {
      let av, bv
      if (sortBy === 'score') {
        av = a.evaluation?.totalScore ?? 0
        bv = b.evaluation?.totalScore ?? 0
      } else if (sortBy === 'budget') {
        av = parseBudget(a.budget)
        bv = parseBudget(b.budget)
      } else {
        av = a.timeLeft ?? 999
        bv = b.timeLeft ?? 999
      }
      return sortDir === 'desc' ? bv - av : av - bv
    })
  }, [projects, sortBy, sortDir])

  const handleSortClick = (value) => {
    if (sortBy === value) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(value)
      setSortDir('desc')
    }
  }

  const handleExportJson = () =>
    downloadFile('projects.json', projectsToJson(projects), 'application/json')

  const handleExportCsv = () =>
    downloadFile('projects.csv', projectsToCsv(projects), 'text/csv;charset=utf-8')

  if (!projects.length) return null

  return (
    <div className="results-section">
      <div className="results-header">
        <span className="results-count">
          <span className="accent">{projects.length}</span>
          {' '}result{projects.length !== 1 ? 's' : ''}
        </span>
        <div className="results-controls">
          <div className="sort-controls">
            {SORT_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                className={`btn btn-sm ${sortBy === opt.value ? 'btn-active' : ''}`}
                onClick={() => handleSortClick(opt.value)}
              >
                {opt.label}
                {sortBy === opt.value ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
              </button>
            ))}
          </div>
          <div className="export-controls">
            <button type="button" className="btn btn-sm" onClick={handleExportJson}>
              json
            </button>
            <button type="button" className="btn btn-sm" onClick={handleExportCsv}>
              csv
            </button>
          </div>
        </div>
      </div>

      <div className="results-list">
        {sorted.map((project, i) => (
          <ProjectCard key={project.url || i} project={project} />
        ))}
      </div>
    </div>
  )
}
