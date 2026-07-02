import Head from 'next/head'
import { useState } from 'react'
import ProjectSearchForm from '../src/components/ProjectSearchForm'
import LogMonitor from '../src/components/LogMonitor'
import { useLocalStorage } from '../src/hooks/useLocalStorage'
import { useAuth } from '../src/hooks/useAuth'
import { useBackendWake } from '../src/hooks/useBackendWake'
import { logClientError } from '../src/utils/clientLogger'
import { pollJob } from '../lib/jobPolling'

const MAX_HISTORY = 10

function PasswordGate({ onLogin }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!value.trim()) return

    const res = await fetch('/api/debug', {
      headers: { 'x-webhook-password': value.trim() },
    })
    if (res.ok || res.status === 502 || res.status === 503) {
      onLogin(value.trim())
    } else {
      setError(true)
      setValue('')
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <form onSubmit={handleSubmit} style={{ width: '100%', maxWidth: 320 }} className="card">
        <h2 style={{ marginBottom: 16 }}>// auth required</h2>
        <div className="form-group">
          <label className="form-label">password</label>
          <input
            type="password"
            className="form-input"
            value={value}
            onChange={e => { setValue(e.target.value); setError(false) }}
            placeholder="enter password"
            autoFocus
          />
          {error && <span className="form-error">// неверный пароль</span>}
        </div>
        <button type="submit" className="btn btn-primary btn-block">
          &gt; enter
        </button>
      </form>
    </div>
  )
}

export default function Home() {
  const { password, login, logout, authHeaders } = useAuth()
  const backend = useBackendWake()
  const [platform, setPlatform] = useState('kwork')

  const [kworkProjects, setKworkProjects] = useState([])
  const [kworkStatus, setKworkStatus] = useState('waiting')
  const [kworkLoading, setKworkLoading] = useState(false)
  const [kworkError, setKworkError] = useState(null)

  const [wzProjects, setWzProjects] = useState([])
  const [wzStatus, setWzStatus] = useState('waiting')
  const [wzLoading, setWzLoading] = useState(false)
  const [wzError, setWzError] = useState(null)

  const [searchHistory, setSearchHistory] = useLocalStorage('search_history', [])

  const isLoading = platform === 'kwork' ? kworkLoading : wzLoading
  const status = platform === 'kwork' ? kworkStatus : wzStatus
  const projects = platform === 'kwork' ? kworkProjects : wzProjects
  const error = platform === 'kwork' ? kworkError : wzError

  if (!password) return <PasswordGate onLogin={login} />

  // Both searches run as server-side jobs consumed via short polls (see
  // lib/jobPolling.js) — a multi-minute request does not survive the Telegram
  // WebView suspending or Render's edge timeout, but 3-second polls do.
  const handleKworkSearch = async (searchParams) => {
    // Re-entrancy guard: the button's disabled={isLoading} commits async in
    // React 18, so a fast double-tap (common in mobile WebViews) can fire this
    // twice → two poll loops over the same job → every card duplicated.
    if (kworkLoading) return
    setKworkLoading(true)
    setKworkError(null)
    setKworkStatus('running')
    setKworkProjects([])

    let collected = []
    try {
      await pollJob({
        startPath: '/api/projects/search-start',
        statusPath: '/api/projects/search-status',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(searchParams),
        onBatch: (batch) => {
          collected = [...collected, ...batch]
          setKworkProjects(prev => [...prev, ...batch])
        },
      })
      setKworkStatus('success')
      setSearchHistory(prev => [{
        id: Date.now(), timestamp: new Date().toISOString(),
        params: { ...searchParams, platform: 'kwork' },
        projects: collected,
      }, ...prev].slice(0, MAX_HISTORY))
    } catch (err) {
      const message = err.code === 'JOB_NOT_FOUND'
        ? 'Сервер перезапустился во время поиска — запустите поиск ещё раз'
        : (err.message || 'network error')
      setKworkError(message)
      setKworkStatus('error')
      logClientError('search_failed', { endpoint: '/api/projects/search-start', message: err.message })
    } finally {
      setKworkLoading(false)
    }
  }

  const handleWzSearch = async () => {
    if (wzLoading) return
    setWzLoading(true)
    setWzError(null)
    setWzStatus('running')
    setWzProjects([])

    try {
      await pollJob({
        startPath: '/api/workzilla/search-start',
        statusPath: '/api/workzilla/search-status',
        headers: authHeaders,
        onBatch: (batch) => {
          for (const data of batch) {
            if (data._update) {
              setWzProjects(prev => prev.map(p =>
                p.id === data._update ? { ...p, description: data.description } : p
              ))
            } else {
              setWzProjects(prev => [...prev, data])
            }
          }
        },
      })
      setWzStatus('success')
    } catch (err) {
      const message = err.code === 'JOB_NOT_FOUND'
        ? 'Сервер перезапустился во время поиска — запустите поиск ещё раз'
        : (err.message || 'network error')
      setWzError(message)
      setWzStatus('error')
      logClientError('workzilla_search_failed', { endpoint: '/api/workzilla/search-start', message: err.message })
    } finally {
      setWzLoading(false)
    }
  }

  const handleParseUrl = async (url) => {
    setKworkLoading(true)
    setKworkError(null)
    setKworkStatus('running')

    try {
      const response = await fetch('/api/projects/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ url }),
      })
      const data = await response.json()

      if (data.status === 'success') {
        setKworkProjects([data.project])
        setKworkStatus('success')
      } else {
        setKworkError(data.message || 'failed to parse project')
        setKworkStatus('error')
      }
    } catch (err) {
      setKworkError(err.message || 'network error')
      setKworkStatus('error')
      logClientError('parse_failed', { endpoint: '/api/projects/parse', message: err.message })
    } finally {
      setKworkLoading(false)
    }
  }

  return (
    <>
      <Head>
        <title>freelance search</title>
        <meta name="description" content="Search and parse projects from freelance platforms" />
        <link rel="icon" href="/favicon.ico" />
      </Head>
      <main className="page">
        <header className="page-header">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h1>freelance_search</h1>
              <p className="subtitle">// kwork · workzilla · url parser · v1.1</p>
            </div>
            <button
              type="button"
              onClick={logout}
              style={{ fontSize: 11, opacity: 0.4, cursor: 'pointer', background: 'none', border: 'none', color: 'inherit' }}
              title="Log out"
            >
              // logout
            </button>
          </div>
        </header>

        <div className="platform-tabs">
          <button
            type="button"
            className={`platform-tab ${platform === 'kwork' ? 'platform-tab-active' : ''}`}
            onClick={() => setPlatform('kwork')}
          >
            kwork
          </button>
          <button
            type="button"
            className={`platform-tab ${platform === 'workzilla' ? 'platform-tab-active' : ''}`}
            onClick={() => setPlatform('workzilla')}
          >
            workzilla
          </button>
        </div>

        <div className={`card ${backend.state !== 'ready' ? 'card-gated' : ''}`}>
          {backend.state !== 'ready' && (
            <div className={`card-overlay ov-${backend.state}`}>
              {backend.state === 'warming' ? (
                <>
                  <span className="bw-spinner" />
                  <span className="bw-text">// бужу бэкенд… попытка {backend.attempt} · {backend.elapsed}s</span>
                  <span className="bw-hint">поиск откроется, как только сервис ответит</span>
                </>
              ) : (
                <>
                  <span className="bw-dot bw-dot-err" />
                  <span className="bw-text">// бэкенд не ответил за {backend.elapsed}s</span>
                  <button type="button" className="bw-action" onClick={backend.run}>разбудить ещё раз</button>
                </>
              )}
            </div>
          )}
          {platform === 'kwork' ? (
            <ProjectSearchForm
              onSearch={handleKworkSearch}
              onParseUrl={handleParseUrl}
              isLoading={kworkLoading}
              status={kworkStatus}
              projects={kworkProjects}
              platform="kwork"
              authHeaders={authHeaders}
            />
          ) : (
            <ProjectSearchForm
              onSearch={handleWzSearch}
              onParseUrl={null}
              isLoading={wzLoading}
              status={wzStatus}
              projects={wzProjects}
              platform="workzilla"
              authHeaders={authHeaders}
            />
          )}
          {error && (
            <div className="alert alert-error">// {error}</div>
          )}
        </div>

        <LogMonitor isActive={isLoading} password={password} />
      </main>
    </>
  )
}