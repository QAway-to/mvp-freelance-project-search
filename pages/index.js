import Head from 'next/head'
import { useState } from 'react'
import ProjectSearchForm from '../src/components/ProjectSearchForm'
import ProjectResults from '../src/components/ProjectResults'
import LogMonitor from '../src/components/LogMonitor'

export default function Home() {
  const [projects, setProjects] = useState([])
  const [status, setStatus] = useState('waiting')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSearch = async (searchParams) => {
    setIsLoading(true)
    setError(null)
    setStatus('running')
    setProjects([])

    try {
      const response = await fetch('/api/projects/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(searchParams),
      })
      const data = await response.json()

      if (data.status === 'success') {
        setProjects(data.projects || [])
        setStatus('success')
      } else {
        setError(data.message || 'search failed')
        setStatus('error')
      }
    } catch (err) {
      setError(err.message || 'network error')
      setStatus('error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleParseUrl = async (url) => {
    setIsLoading(true)
    setError(null)
    setStatus('running')

    try {
      const response = await fetch('/api/projects/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      const data = await response.json()

      if (data.status === 'success') {
        setProjects([data.project])
        setStatus('success')
      } else {
        setError(data.message || 'failed to parse project')
        setStatus('error')
      }
    } catch (err) {
      setError(err.message || 'network error')
      setStatus('error')
    } finally {
      setIsLoading(false)
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
          <p className="subtitle">// kwork.ru · keyword + url parser · v1.0</p>
        </header>

        <div className="card">
          <ProjectSearchForm
            onSearch={handleSearch}
            onParseUrl={handleParseUrl}
            isLoading={isLoading}
            status={status}
          />
          {error && (
            <div className="alert alert-error">// {error}</div>
          )}
        </div>

        <LogMonitor isActive={isLoading} />

        <ProjectResults projects={projects} />
      </main>
    </>
  )
}
