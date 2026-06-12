import { useState } from 'react'

function formatTime(iso) {
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function ParamBadge({ label, value }) {
  if (!value && value !== 0) return null
  return (
    <span className="param-badge">
      {label}: <span className="accent">{value}</span>
    </span>
  )
}

function HistoryEntry({ entry, onRerun }) {
  const [open, setOpen] = useState(false)
  const { params, projects, timestamp } = entry

  return (
    <div className="history-entry">
      <div className="history-entry-header" onClick={() => setOpen(o => !o)}>
        <span className="history-meta">
          <span className="accent">{formatTime(timestamp)}</span>
          {' · '}
          <span>{params.keywords || '(без ключевых слов)'}</span>
          {' · '}
          <span className="accent">{projects.length}</span> results
        </span>
        <div className="history-entry-actions">
          <button
            type="button"
            className="btn btn-sm"
            onClick={(e) => { e.stopPropagation(); onRerun(params) }}
          >
            re-run
          </button>
          <span className="history-toggle">{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className="history-entry-body">
          <div className="history-params">
            <ParamBadge label="time≤" value={params.timeLeft ? `${params.timeLeft}h` : null} />
            <ParamBadge label="budget≥" value={params.budgetMin ? `${params.budgetMin}₽` : null} />
            <ParamBadge label="hired≥" value={params.hiredMin ? `${params.hiredMin}%` : null} />
            <ParamBadge label="proposals≤" value={params.proposalsMax} />
          </div>
          {projects.length === 0 ? (
            <p className="history-empty">// no results</p>
          ) : (
            <ul className="history-results">
              {projects.map((p, i) => (
                <li key={p.url || i} className="history-result-item">
                  <a href={p.url} target="_blank" rel="noreferrer" className="history-result-title">
                    {p.title}
                  </a>
                  <span className="history-result-meta">
                    {p.budget && <span>{p.budget}</span>}
                    {p.evaluation?.score != null && (
                      <span className="accent"> · score {(p.evaluation.score * 100).toFixed(0)}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default function SearchHistory({ history, onRerun, onClear }) {
  if (!history || history.length === 0) return null

  return (
    <div className="card history-section">
      <div className="history-header">
        <span className="section-title">// search history</span>
        <button type="button" className="btn btn-sm" onClick={onClear}>clear</button>
      </div>
      {history.map(entry => (
        <HistoryEntry key={entry.id} entry={entry} onRerun={onRerun} />
      ))}
    </div>
  )
}
