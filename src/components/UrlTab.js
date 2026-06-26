import { useState } from 'react'

// Accept a project view URL, a new_offer URL, or a bare project id.
const KWORK_PATTERN = /(?:kwork\.ru\/projects\/\d+|kwork\.ru\/new_offer\?project=\d+|^\s*\d+\s*$)/

export default function UrlTab({ onParseUrl, isLoading }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!url.trim()) { setError('введите url проекта или id'); return }
    if (!KWORK_PATTERN.test(url.trim())) {
      setError('формат: kwork.ru/projects/ID/view, kwork.ru/new_offer?project=ID или просто ID')
      return
    }
    setError(null)
    onParseUrl(url.trim())
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label className="form-label">
          kwork url <span className="form-hint">// /projects/ID или new_offer?project=ID</span>
        </label>
        <input
          type="text"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setError(null) }}
          placeholder="https://kwork.ru/new_offer?project=3205110"
          className="form-input"
          disabled={isLoading}
          autoComplete="off"
        />
        {error && <span className="form-error">// {error}</span>}
      </div>

      <button
        type="submit"
        disabled={isLoading || !url.trim()}
        className="btn btn-primary btn-block"
      >
        {isLoading ? '> loading...' : '> load project'}
      </button>
    </form>
  )
}
