import { useState } from 'react';

export default function ProjectSearchForm({ onSearch, onParseUrl, isLoading, status }) {
  const [keywords, setKeywords] = useState('');
  const [kworkUrl, setKworkUrl] = useState('');
  const [timeLeft, setTimeLeft] = useState('');
  const [hiredMin, setHiredMin] = useState('');
  const [proposalsMax, setProposalsMax] = useState('');

  // Filter to allow only Cyrillic characters
  const filterCyrillicOnly = (text) => {
    return text.replace(/[^а-яА-ЯёЁ\s,.-]/g, '');
  };

  const handleKeywordsChange = (e) => {
    const filtered = filterCyrillicOnly(e.target.value);
    setKeywords(filtered);
  };

  const handleKeywordsPaste = (e) => {
    e.preventDefault();
    const pastedText = (e.clipboardData || window.clipboardData).getData('text');
    const filtered = filterCyrillicOnly(pastedText);
    setKeywords(filtered);
  };

  const handleSearch = (e) => {
    e.preventDefault();
    
    if (!keywords.trim()) {
      alert('Please enter keywords');
      return;
    }

    onSearch({
      keywords: keywords.trim(),
      timeLeft: timeLeft ? parseInt(timeLeft) : null,
      hiredMin: hiredMin ? parseInt(hiredMin) : null,
      proposalsMax: proposalsMax ? parseInt(proposalsMax) : null,
    });
  };

  const handleParseUrl = async (e) => {
    e.preventDefault();
    
    if (!kworkUrl.trim()) {
      alert('Please enter a project URL');
      return;
    }

    // Validate Kwork URL
    const kworkUrlPattern = /^https:\/\/kwork\.ru\/projects\/\d+\/view$/;
    if (!kworkUrlPattern.test(kworkUrl.trim())) {
      alert('Invalid URL format. Expected: https://kwork.ru/projects/XXXXX/view');
      return;
    }

    onParseUrl(kworkUrl.trim());
  };

  const getStatusBadge = () => {
    const statusClasses = {
      waiting: 'status-waiting',
      running: 'status-running',
      success: 'status-success',
      error: 'status-error',
    };
    
    const statusLabels = {
      waiting: 'Waiting',
      running: 'Searching...',
      success: 'Success',
      error: 'Error',
    };

    return (
      <span className={`status-badge ${statusClasses[status] || 'status-waiting'}`}>
        {statusLabels[status] || status}
      </span>
    );
  };

  return (
    <form onSubmit={handleSearch}>
      <div className="form-group">
        <label className="form-label">Or paste Kwork project URL:</label>
        <input
          type="url"
          value={kworkUrl}
          onChange={(e) => setKworkUrl(e.target.value)}
          placeholder="https://kwork.ru/projects/2996436/view"
          pattern="https://kwork\.ru/projects/\d+/view"
          className="form-input"
          disabled={isLoading}
        />
        <button
          type="button"
          onClick={handleParseUrl}
          disabled={isLoading}
          className="btn"
          style={{ marginTop: '8px', width: '100%' }}
        >
          Load Project from URL
        </button>
      </div>

      <div className="form-group">
        <label className="form-label">Keywords (Cyrillic only)</label>
        <input
          type="text"
          value={keywords}
          onChange={handleKeywordsChange}
          onPaste={handleKeywordsPaste}
          placeholder="Enter keywords (Cyrillic letters, spaces, commas)"
          pattern="[а-яА-ЯёЁ\s,.-]*"
          className="form-input"
          disabled={isLoading}
        />
      </div>

      <div className="form-group form-group-row">
        <div className="form-field-inline">
          <label className="form-label-inline">Time Left ≤</label>
          <input
            type="number"
            value={timeLeft}
            onChange={(e) => setTimeLeft(e.target.value)}
            placeholder="hours max"
            min="0"
            step="1"
            className="form-input-inline"
            disabled={isLoading}
          />
        </div>
        <div className="form-field-inline">
          <label className="form-label-inline">Hired Min</label>
          <input
            type="number"
            value={hiredMin}
            onChange={(e) => setHiredMin(e.target.value)}
            placeholder="%"
            min="0"
            max="100"
            step="1"
            className="form-input-inline"
            disabled={isLoading}
          />
        </div>
        <div className="form-field-inline">
          <label className="form-label-inline">Proposals Max</label>
          <input
            type="number"
            value={proposalsMax}
            onChange={(e) => setProposalsMax(e.target.value)}
            placeholder="max"
            min="0"
            step="1"
            className="form-input-inline"
            disabled={isLoading}
          />
        </div>
      </div>

      <div className="form-group">
        <button
          type="submit"
          disabled={isLoading || !keywords.trim()}
          className="btn btn-primary"
          style={{ width: '100%' }}
        >
          {isLoading ? 'Searching...' : 'Search Projects'}
        </button>
      </div>

      <div className="form-group">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '0.9rem', color: '#9ca3af' }}>Status:</span>
          {getStatusBadge()}
        </div>
      </div>
    </form>
  );
}

