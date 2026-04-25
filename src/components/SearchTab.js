import { useState, useEffect, useRef } from 'react'
import { useLocalStorage } from '../hooks/useLocalStorage'
import { KWORK_CATEGORIES } from '../../lib/kworkCategories'

const DEFAULT_CATEGORY = 41

const filterCyrillic = (text) => text.replace(/[^а-яА-ЯёЁ\s,.-]/g, '')

export default function SearchTab({ onSearch, isLoading }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState(DEFAULT_CATEGORY)
  const [timeLeft, setTimeLeft] = useState('')
  const [hiredMin, setHiredMin] = useState('')
  const [proposalsMax, setProposalsMax] = useState('')
  const [error, setError] = useState(null)
  const [history, setHistory] = useLocalStorage('recent_searches', [])
  const lastSearchedRef = useRef('')
  const onSearchRef = useRef(onSearch)

  useEffect(() => { onSearchRef.current = onSearch }, [onSearch])

  const buildParams = (q) => ({
    keywords: q,
    ...(category !== DEFAULT_CATEGORY ? { category } : {}),
    timeLeft: timeLeft ? parseInt(timeLeft, 10) : null,
    hiredMin: hiredMin ? parseInt(hiredMin, 10) : null,
    proposalsMax: proposalsMax ? parseInt(proposalsMax, 10) : null,
  })

  const pushHistory = (q) => {
    const trimmed = q.trim()
    if (!trimmed) return
    setHistory(prev => [trimmed, ...prev.filter(h => h !== trimmed)].slice(0, 5))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!query.trim()) { setError('введите ключевые слова'); return }
    setError(null)
    lastSearchedRef.current = query.trim()
    pushHistory(query.trim())
    onSearchRef.current(buildParams(query.trim()))
  }

  const handleChipClick = (chip) => {
    setQuery(chip)
    setError(null)
    lastSearchedRef.current = chip
    pushHistory(chip)
    onSearchRef.current(buildParams(chip))
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label className="form-label">
          category
        </label>
        <select
          value={category}
          onChange={(e) => setCategory(parseInt(e.target.value, 10))}
          className="form-input"
          disabled={isLoading}
        >
          {KWORK_CATEGORIES.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.labelRu}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">
          keywords <span className="form-hint">// кириллица</span>
        </label>
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(filterCyrillic(e.target.value)); setError(null) }}
          onPaste={(e) => {
            e.preventDefault()
            const text = (e.clipboardData || window.clipboardData).getData('text')
            setQuery(filterCyrillic(text))
          }}
          placeholder="разработка сайта, парсинг..."
          className="form-input"
          disabled={isLoading}
          autoComplete="off"
        />
        {error && <span className="form-error">// {error}</span>}
        {history.length > 0 && (
          <div className="history-chips">
            {history.map((chip) => (
              <button
                key={chip}
                type="button"
                className="chip"
                onClick={() => handleChipClick(chip)}
                disabled={isLoading}
              >
                {chip}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="form-group form-group-row">
        <div className="form-field-inline">
          <label className="form-label-inline">time ≤</label>
          <input
            type="number"
            value={timeLeft}
            onChange={(e) => setTimeLeft(e.target.value)}
            placeholder="часов"
            min="0"
            className="form-input-inline"
            disabled={isLoading}
          />
        </div>
        <div className="form-field-inline">
          <label className="form-label-inline">hired ≥</label>
          <input
            type="number"
            value={hiredMin}
            onChange={(e) => setHiredMin(e.target.value)}
            placeholder="%"
            min="0"
            max="100"
            className="form-input-inline"
            disabled={isLoading}
          />
        </div>
        <div className="form-field-inline">
          <label className="form-label-inline">proposals ≤</label>
          <input
            type="number"
            value={proposalsMax}
            onChange={(e) => setProposalsMax(e.target.value)}
            placeholder="макс"
            min="0"
            className="form-input-inline"
            disabled={isLoading}
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading || !query.trim()}
        className="btn btn-primary btn-block"
      >
        {isLoading ? '> searching...' : '> search'}
      </button>
    </form>
  )
}
