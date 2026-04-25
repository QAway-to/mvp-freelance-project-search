import { useEffect, useRef, useState } from 'react'
import { useLogStream } from '../hooks/useLogStream'

const LEVEL_CLASS = {
  ERROR: 'log-error',
  WARNING: 'log-warn',
  WARN: 'log-warn',
  INFO: 'log-info',
  DEBUG: 'log-dim',
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString('ru-RU', { hour12: false })
  } catch {
    return ''
  }
}

export default function LogMonitor({ isActive }) {
  const { lines, clear } = useLogStream(isActive)
  const [collapsed, setCollapsed] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!collapsed && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, collapsed])

  if (lines.length === 0 && !isActive) return null

  return (
    <div className="log-monitor">
      <div className="log-header">
        <span className="log-title">
          {isActive && <span className="dot dot-running" style={{ display: 'inline-block', marginRight: 6 }} />}
          agent log
        </span>
        <div className="log-actions">
          <button type="button" className="btn-text" onClick={clear}>clear</button>
          <button type="button" className="btn-text" onClick={() => setCollapsed(v => !v)}>
            {collapsed ? '[ expand ]' : '[ collapse ]'}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="log-body">
          {lines.length === 0 && (
            <span className="log-dim">// waiting for events...</span>
          )}
          {lines.map((line, i) => (
            <div key={i} className={`log-line ${LEVEL_CLASS[line.level] || 'log-dim'}`}>
              <span className="log-ts">{formatTime(line.timestamp)}</span>
              <span className="log-lvl">{(line.level || 'INFO').slice(0, 4)}</span>
              <span className="log-msg">{line.message}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
