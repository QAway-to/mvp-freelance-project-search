import Head from 'next/head'
import { useState } from 'react'
import ProjectSearchForm from '../src/components/ProjectSearchForm'
import LogMonitor from '../src/components/LogMonitor'
import { useLocalStorage } from '../src/hooks/useLocalStorage'

const MAX_HISTORY = 10

export default function Home() {
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

  const handleKworkSearch = async (searchParams) => {
    setKworkLoading(true)
    setKworkError(null)
    setKworkStatus('running')
    setKworkProjects([])

    try {
      const response = await fetch('/api/projects/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(searchParams),
      })
      const data = await response.json()

      if (data.status === 'success') {
        setKworkProjects(data.projects || [])
        setKworkStatus('success')
        setSearchHistory(prev => [{
          id: Date.now(), timestamp: new Date().toISOString(),
          params: { ...searchParams, platform: 'kwork' },
          projects: data.projects || [],
        }, ...prev].slice(0, MAX_HISTORY))
      } else {
        setKworkError(data.message || 'search failed')
        setKworkStatus('error')
      }
    } catch (err) {
      setKworkError(err.message || 'network error')
      setKworkStatus('error')
    } finally {
      setKworkLoading(false)
    }
  }

  const handleWzSearch = async () => {
    setWzLoading(true)
    setWzError(null)
    setWzStatus('running')
    setWzProjects([])

    try {
      const response = await fetch('/api/workzilla/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const data = await response.json()

      if (data.status === 'success') {
        setWzProjects(data.projects || [])
        setWzStatus('success')
      } else {
        setWzError(data.message || 'search failed')
        setWzStatus('error')
      }
    } catch (err) {
      setWzError(err.message || 'network error')
      setWzStatus('error')
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
        headers: { 'Content-Type': 'application/json' },
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
          <h1>freelance_search</h1>
          <p className="subtitle">// kwork · workzilla · url parser · v1.1</p>
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

        <div className="card">
          {platform === 'kwork' ? (
            <ProjectSearchForm
              onSearch={handleKworkSearch}
              onParseUrl={handleParseUrl}
              isLoading={kworkLoading}
              status={kworkStatus}
              projects={kworkProjects}
              platform="kwork"
            />
          ) : (
            <ProjectSearchForm
              onSearch={handleWzSearch}
              onParseUrl={null}
              isLoading={wzLoading}
              status={wzStatus}
              projects={wzProjects}
              platform="workzilla"
            />
          )}
          {error && (
            <div className="alert alert-error">// {error}</div>
          )}
        </div>

        <LogMonitor isActive={isLoading} />
      </main>
    </>
  )
}
