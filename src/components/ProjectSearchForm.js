import { useState, useEffect } from 'react'
import SearchTab from './SearchTab'
import UrlTab from './UrlTab'
import ProjectResults from './ProjectResults'

const STATUS_MAP = {
  waiting: { cls: 'dot-idle',    label: 'idle' },
  running: { cls: 'dot-running', label: 'searching' },
  success: { cls: 'dot-success', label: 'done' },
  error:   { cls: 'dot-error',   label: 'error' },
}

export default function ProjectSearchForm({ onSearch, onParseUrl, isLoading, status, projects = [], platform = 'kwork', authHeaders = {} }) {
  const [activeTab, setActiveTab] = useState('search')
  const dot = STATUS_MAP[status] || STATUS_MAP.waiting

  useEffect(() => {
    if (isLoading) setActiveTab('responses')
  }, [isLoading])

  return (
    <div>
      <div className="tab-strip">
        <button
          type="button"
          className={`tab ${activeTab === 'search' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('search')}
          disabled={isLoading}
        >
          search
        </button>
        {platform === 'kwork' && (
          <button
            type="button"
            className={`tab ${activeTab === 'url' ? 'tab-active' : ''}`}
            onClick={() => setActiveTab('url')}
            disabled={isLoading}
          >
            url
          </button>
        )}
        <button
          type="button"
          className={`tab ${activeTab === 'responses' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('responses')}
        >
          responses{!isLoading && projects.length > 0 ? ` (${projects.length})` : ''}
        </button>
        <span className="tab-status">
          <span className={`dot ${dot.cls}`} />
          {dot.label}
        </span>
      </div>

      {activeTab === 'search' && platform === 'kwork' && (
        <SearchTab onSearch={onSearch} isLoading={isLoading} />
      )}
      {activeTab === 'search' && platform === 'workzilla' && (
        <div style={{ paddingTop: '8px' }}>
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={() => onSearch()}
            disabled={isLoading}
          >
            {isLoading ? '> searching...' : '> search workzilla'}
          </button>
        </div>
      )}
      {activeTab === 'url' && (
        <UrlTab onParseUrl={onParseUrl} isLoading={isLoading} />
      )}
      {activeTab === 'responses' && (
        isLoading
          ? (
            <div className="responses-collecting">
              <span className="responses-spinner" />
              <span className="responses-collecting-text">
                // wait — collecting responses...
              </span>
            </div>
          )
          : <ProjectResults projects={projects} platform={platform} authHeaders={authHeaders} />
      )}
    </div>
  )
}
