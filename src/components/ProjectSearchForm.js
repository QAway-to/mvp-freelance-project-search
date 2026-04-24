import { useState } from 'react'
import SearchTab from './SearchTab'
import UrlTab from './UrlTab'

const STATUS_MAP = {
  waiting: { cls: 'dot-idle', label: 'idle' },
  running: { cls: 'dot-running', label: 'searching' },
  success: { cls: 'dot-success', label: 'done' },
  error:   { cls: 'dot-error',   label: 'error' },
}

export default function ProjectSearchForm({ onSearch, onParseUrl, isLoading, status }) {
  const [activeTab, setActiveTab] = useState('search')
  const dot = STATUS_MAP[status] || STATUS_MAP.waiting

  return (
    <div>
      <div className="tab-strip">
        <button
          type="button"
          className={`tab ${activeTab === 'search' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          search
        </button>
        <button
          type="button"
          className={`tab ${activeTab === 'url' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('url')}
        >
          url
        </button>
        <span className="tab-status">
          <span className={`dot ${dot.cls}`} />
          {dot.label}
        </span>
      </div>

      {activeTab === 'search'
        ? <SearchTab onSearch={onSearch} isLoading={isLoading} />
        : <UrlTab onParseUrl={onParseUrl} isLoading={isLoading} />
      }
    </div>
  )
}
