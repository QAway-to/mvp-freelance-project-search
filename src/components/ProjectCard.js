import { useState } from 'react'

// Срок выполнения — точные варианты из vue-select формы отклика Kwork (new_offer).
const SROK_OPTIONS = [
  '1 день', '2 дня', '3 дня', '4 дня', '5 дней', '6 дней',
  '7 дней', '10 дней', '2 недели', '3 недели', '1 месяц', '2 месяца',
]

export default function ProjectCard({ project, platform = 'kwork', authHeaders = {} }) {
  const [isCardExpanded, setIsCardExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)

  const [cpState, setCpState] = useState('idle') // idle | loading | done | error
  const [cpText, setCpText] = useState('')
  const [respondState, setRespondState] = useState('idle') // idle | confirm | sending | done | error
  const [srok, setSrok] = useState('3 дня') // срок выполнения, выбирается вручную перед откликом

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
    if (!project.description) {
      setCpState('error')
      setCpText('')
      return
    }
    setCpState('loading')
    setCpText('')
    setRespondState('idle')
    try {
      const res = await fetch('/api/projects/cp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          description: project.description,
          budget: project.budget,
          title: project.title,
          files: project.files || [],
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
        const endpoint = platform === 'workzilla' ? '/api/workzilla/respond' : '/api/projects/respond'
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders },
          body: JSON.stringify({ url: project.url, cp_text: cpText, duration: srok }),
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
        <div className="project-card-header-right">
          {scoreLabel && (
            <span className={`project-score ${scoreClass}`}>{scoreLabel}</span>
          )}
          <button
            type="button"
            className="btn-text card-expand-btn"
            onClick={() => setIsCardExpanded(v => !v)}
          >
            {isCardExpanded ? '[ collapse ]' : '[ expand ]'}
          </button>
        </div>
      </div>

      {!isCardExpanded && (
        <div className="project-meta project-meta-collapsed">
          {project.budget && (
            <span><span className="meta-key">бюджет </span>{project.budget}</span>
          )}
          {project.timeLeft != null && (
            <span><span className="meta-key">time </span>{
              isNaN(Number(project.timeLeft))
                ? project.timeLeft
                : `${Number(project.timeLeft).toFixed(2)}h`
            }</span>
          )}
          {project.proposals != null && (
            <span><span className="meta-key">откликов </span>{project.proposals}</span>
          )}
        </div>
      )}

      {isCardExpanded && (
        <>
          {project.description && (
            <div className="project-desc-wrap">
              <p className="project-description">{project.description}</p>
            </div>
          )}

          <div className="project-meta">
            {project.timeLeft != null && (
              <span><span className="meta-key">time </span>{
                isNaN(Number(project.timeLeft))
                  ? project.timeLeft
                  : `${Number(project.timeLeft).toFixed(2)}h`
              }</span>
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
              {cpState === 'loading' ? 'генерирую…' : cpState === 'done' ? 'дать кп ещё раз' : 'дать кп'}
            </button>
            <select
              className="srok-select"
              value={srok}
              onChange={(e) => setSrok(e.target.value)}
              title="срок выполнения для отклика"
            >
              {SROK_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>

          {cpState === 'error' && (
            <p className="cp-error">
              {!project.description ? 'Нет описания — КП невозможно сгенерировать.' : 'Ошибка генерации КП. Проверь DEEPSEEK_API_KEY.'}
            </p>
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
        </>
      )}
    </div>
  )
}
