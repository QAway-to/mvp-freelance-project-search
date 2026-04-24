import { useState } from 'react'

const KWORK_PATTERN = /^https:\/\/kwork\.ru\/projects\/\d+\/view$/

export default function UrlTab({ onParseUrl, isLoading }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!url.trim()) { setError('введите url проекта'); return }
    if (!KWORK_PATTERN.test(url.trim())) {
      setError('формат: https://kwork.ru/projects/XXXXX/view')
      return
    }
    setError(null)
    onParseUrl(url.trim())
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label className="form-label">
          kwork url <span className="form-hint">// /projects/ID/view</span>
        </label>
        <input
          type="url"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setError(null) }}
          placeholder="https://kwork.ru/projects/2996436/view"
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
