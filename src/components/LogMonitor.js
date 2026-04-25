import { useEffect, useRef, useState } from 'react'
import { useLogStream } from '../hooks/useLogStream'

export default function LogMonitor({ isActive }) {
  const { lines } = useLogStream(isActive)
  const [lastMsg, setLastMsg] = useState('')

  useEffect(() => {
    if (lines.length === 0) return
    const last = lines[lines.length - 1]
    if (last?.message) setLastMsg(last.message)
  }, [lines])

  if (!isActive && !lastMsg) return null

  return (
    <div className="log-statusbar">
      {isActive && <div className="log-progress-bar"><div className="log-progress-fill" /></div>}
      <span className="log-status-msg">
        {isActive
          ? (lastMsg || '// connecting...')
          : `// done — ${lastMsg}`}
      </span>
    </div>
  )
}
