import { useLogStream } from '../hooks/useLogStream'

export default function LogMonitor({ isActive }) {
  const { progress, lastMsg } = useLogStream(isActive)

  if (!isActive && !lastMsg) return null

  return (
    <div className="log-statusbar">
      <div className="log-progress-bar">
        <div className="log-progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <span className="log-status-msg">
        {lastMsg || '// connecting...'}
      </span>
    </div>
  )
}
