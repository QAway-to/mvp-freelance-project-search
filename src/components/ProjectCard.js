import { useState } from 'react'

const TRUNCATE_LEN = 150

export default function ProjectCard({ project }) {
  const hasLongDesc = project.description && project.description.length > TRUNCATE_LEN
  const [isExpanded, setIsExpanded] = useState(!hasLongDesc)
  const [copied, setCopied] = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)

  const [cpState, setCpState] = useState('idle') // idle | loading | done | error
  const [cpText, setCpText] = useState('')
  const [respondState, setRespondState] = useState('idle') // idle | confirm | sending | done | error

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

  async function handleGenerateCp() {
    setCpState('loading')
    setCpText('')
    setRespondState('idle')
    try {
      const res = await fetch('/api/projects/cp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: project.description,
          budget: project.budget,
          title: project.title,
        }),
      })
      const data = await res.json()
      if (data.proposal) {
        setCpText(data.proposal)
        setCpState('done')
      } else {
        setCpState('error')
      }
    } catch {
      setCpState('error')
    }
  }

  async function handleSubmitRespond() {
    if (respondState === 'idle') {
      setRespondState('confirm')
      return
    }
    if (respondState === 'confirm') {
      setRespondState('sending')
      try {
        const res = await fetch('/api/projects/respond', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: project.url, cp_text: cpText }),
        })
        const data = await res.json()
        setRespondState(data.success ? 'done' : 'error')
      } catch {
        setRespondState('error')
      }
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
        {project.timeLeft != null && (
          <span><span className="meta-key">time </span>{Number(project.timeLeft).toFixed(2)}h</span>
        )}
        {project.budget && (
          <span><span className="meta-key">бюджет </span>{project.budget}</span>
        )}
        {project.proposals != null && (
          <span><span className="meta-key">предложений </span>{project.proposals}</span>
        )}
      </div>

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
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={handleGenerateCp}
          disabled={cpState === 'loading'}
        >
          {cpState === 'loading' ? 'генерирую…' : cpState === 'done' ? 'переписать кп' : 'сгенерировать кп'}
        </button>
      </div>

      {cpState === 'error' && (
        <p className="cp-error">Ошибка генерации КП. Проверь OPENROUTER_API_KEY.</p>
      )}

      {cpState === 'done' && cpText && (
        <div className="cp-section">
          <div className="cp-label">коммерческое предложение</div>
          <pre className="cp-text">{cpText}</pre>
          <div className="cp-actions">
            {respondState === 'done' && (
              <span className="cp-status cp-status-ok">✓ отклик отправлен</span>
            )}
            {respondState === 'error' && (
              <span className="cp-status cp-status-err">✗ ошибка отправки</span>
            )}
            {respondState !== 'done' && (
              <>
                {respondState === 'confirm' && (
                  <span className="cp-confirm-hint">уверен? нажми ещё раз →</span>
                )}
                <button
                  type="button"
                  className={`btn btn-sm ${respondState === 'confirm' ? 'btn-primary' : ''}`}
                  onClick={handleSubmitRespond}
                  disabled={respondState === 'sending'}
                >
                  {respondState === 'sending' ? 'отправляю…'
                    : respondState === 'confirm' ? '✓ подтвердить отклик'
                    : 'отправить отклик'}
                </button>
                {respondState === 'confirm' && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => setRespondState('idle')}
                  >
                    отмена
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
