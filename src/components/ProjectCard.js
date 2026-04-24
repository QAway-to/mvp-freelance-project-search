import { useState } from 'react'

const TRUNCATE_LEN = 150

export default function ProjectCard({ project }) {
  const hasLongDesc = project.description && project.description.length > TRUNCATE_LEN
  const [isExpanded, setIsExpanded] = useState(!hasLongDesc)
  const [copied, setCopied] = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)

  const score = project.evaluation?.totalScore
  const scoreLabel = score != null ? `${(score * 100).toFixed(0)}%` : null
  const scoreClass = score >= 0.8 ? 'score-high' : score >= 0.5 ? 'score-medium' : 'score-low'

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(project.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyFailed(true)
      setTimeout(() => setCopyFailed(false), 2000)
    }
  }

  return (
    <div className="project-card">
      <div className="project-card-header">
        <h3 className="project-title">{project.title || 'untitled'}</h3>
        {scoreLabel && (
          <span className={`project-score ${scoreClass}`}>{scoreLabel}</span>
        )}
      </div>

      {project.description && (
        <div className="project-desc-wrap">
          <p className="project-description">
            {isExpanded || !hasLongDesc
              ? project.description
              : `${project.description.substring(0, TRUNCATE_LEN)}…`}
          </p>
          {hasLongDesc && (
            <button type="button" className="btn-text" onClick={() => setIsExpanded(v => !v)}>
              {isExpanded ? '[ collapse ]' : '[ expand ]'}
            </button>
          )}
        </div>
      )}

      <div className="project-meta">
        {project.budget && (
          <span><span className="meta-key">budget</span>{project.budget}</span>
        )}
        {project.timeLeft != null && (
          <span><span className="meta-key">time</span>{project.timeLeft}h</span>
        )}
        {project.hired != null && (
          <span><span className="meta-key">hired</span>{project.hired}%</span>
        )}
        {project.proposals != null && (
          <span><span className="meta-key">props</span>{project.proposals}</span>
        )}
      </div>

      {project.evaluation?.reasoning && (
        <div className="project-reasoning">
          <span className="meta-key">// </span>{project.evaluation.reasoning}
        </div>
      )}

      <div className="project-actions">
        {project.url && (
          <>
            <a href={project.url} target="_blank" rel="noopener noreferrer" className="btn btn-sm">
              open ↗
            </a>
            <button type="button" className="btn btn-sm" onClick={handleCopy}>
              {copied ? 'copied ✓' : copyFailed ? 'failed ✗' : 'copy url'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
