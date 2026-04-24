import { useState, useEffect, useRef } from 'react'
import { useDebounce } from '../hooks/useDebounce'
import { useLocalStorage } from '../hooks/useLocalStorage'

const filterCyrillic = (text) => text.replace(/[^а-яА-ЯёЁ\s,.-]/g, '')

export default function SearchTab({ onSearch, isLoading }) {
  const [query, setQuery] = useState('')
  const [timeLeft, setTimeLeft] = useState('')
  const [hiredMin, setHiredMin] = useState('')
  const [proposalsMax, setProposalsMax] = useState('')
  const [error, setError] = useState(null)
  const [history, setHistory] = useLocalStorage('recent_searches', [])
  const lastSearchedRef = useRef('')
  const onSearchRef = useRef(onSearch)

  useEffect(() => { onSearchRef.current = onSearch }, [onSearch])

  const debouncedQuery = useDebounce(query, 600)

  const buildParams = (q) => ({
    keywords: q,
    timeLeft: timeLeft ? parseInt(timeLeft) : null,
    hiredMin: hiredMin ? parseInt(hiredMin) : null,
    proposalsMax: proposalsMax ? parseInt(proposalsMax) : null,
  })

  const pushHistory = (q) => {
    const trimmed = q.trim()
    if (!trimmed) return
    setHistory(prev => [trimmed, ...prev.filter(h => h !== trimmed)].slice(0, 5))
  }

  useEffect(() => { lastSearchedRef.current = '' }, [timeLeft, hiredMin, proposalsMax])

  useEffect(() => {
    if (debouncedQuery.length >= 3 && debouncedQuery !== lastSearchedRef.current) {
      lastSearchedRef.current = debouncedQuery
      pushHistory(debouncedQuery)
      onSearchRef.current(buildParams(debouncedQuery))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, timeLeft, hiredMin, proposalsMax])

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
