import { useState, useEffect, useRef } from 'react'
import { useLocalStorage } from '../hooks/useLocalStorage'
import { KWORK_CATEGORY_GROUPS } from '../constants/kworkCategories'

export default function SearchTab({ onSearch, isLoading }) {
  const [timeLeft, setTimeLeft] = useState('72')
  const [hiredMin, setHiredMin] = useState('')
  const [proposalsMax, setProposalsMax] = useState('')
  // Persisted: the categories the user works with. Empty = no filter (all).
  const [categories, setCategories] = useLocalStorage('kwork_categories', [])
  const [showCats, setShowCats] = useState(false)
  const onSearchRef = useRef(onSearch)

  useEffect(() => { onSearchRef.current = onSearch }, [onSearch])

  const selected = new Set(categories)

  const toggleCat = (id) => {
    setCategories(
      categories.includes(id) ? categories.filter(c => c !== id) : [...categories, id]
    )
  }

  const toggleGroup = (group) => {
    const ids = group.subcats.map(s => s.id)
    const allOn = ids.every(id => selected.has(id))
    const base = categories.filter(c => !ids.includes(c))
    setCategories(allOn ? base : [...base, ...ids])
  }

  const clearCats = () => setCategories([])

  const buildParams = () => ({
    keywords: '',
    timeLeft: timeLeft ? parseInt(timeLeft, 10) : null,
    hiredMin: hiredMin ? parseInt(hiredMin, 10) : null,
    proposalsMax: proposalsMax ? parseInt(proposalsMax, 10) : null,
    categories,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSearchRef.current(buildParams())
  }

  return (
    <form onSubmit={handleSubmit}>
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

      <div className="form-group">
        <button
          type="button"
          className="btn btn-block"
          onClick={() => setShowCats(v => !v)}
          disabled={isLoading}
        >
          {showCats ? '▾' : '▸'} категории{categories.length ? ` (${categories.length})` : ' — все'}
        </button>

        {showCats && (
          <div className="cat-picker">
            <div className="cat-picker-actions">
              <button type="button" className="btn btn-sm" onClick={clearCats} disabled={isLoading}>
                сбросить (все)
              </button>
            </div>
            {KWORK_CATEGORY_GROUPS.map(group => {
              const ids = group.subcats.map(s => s.id)
              const allOn = ids.every(id => selected.has(id))
              return (
                <div key={group.id} className="cat-group">
                  <button
                    type="button"
                    className="cat-group-title"
                    onClick={() => toggleGroup(group)}
                    disabled={isLoading}
                  >
                    {allOn ? '☑' : '☐'} {group.name}
                  </button>
                  <div className="cat-subs">
                    {group.subcats.map(sub => (
                      <label key={sub.id} className="cat-sub">
                        <input
                          type="checkbox"
                          checked={selected.has(sub.id)}
                          onChange={() => toggleCat(sub.id)}
                          disabled={isLoading}
                        />
                        {sub.name}
                      </label>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="btn btn-primary btn-block"
      >
        {isLoading ? '> searching...' : '> search'}
      </button>
    </form>
  )
}
