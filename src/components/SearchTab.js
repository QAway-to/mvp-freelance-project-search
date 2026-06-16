import { useState, useEffect, useRef } from 'react'

export default function SearchTab({ onSearch, isLoading }) {
  const [timeLeft, setTimeLeft] = useState('72')
  const [hiredMin, setHiredMin] = useState('')
  const [proposalsMax, setProposalsMax] = useState('')
  const onSearchRef = useRef(onSearch)

  useEffect(() => { onSearchRef.current = onSearch }, [onSearch])

  const buildParams = () => ({
    keywords: '',
    timeLeft: timeLeft ? parseInt(timeLeft, 10) : null,
    hiredMin: hiredMin ? parseInt(hiredMin, 10) : null,
    proposalsMax: proposalsMax ? parseInt(proposalsMax, 10) : null,
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
