import Head from 'next/head';
import { useState } from 'react';
import ProjectSearchForm from '../src/components/ProjectSearchForm';
import ProjectResults from '../src/components/ProjectResults';

export default function Home() {
  const [projects, setProjects] = useState([]);
  const [status, setStatus] = useState('waiting');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (searchParams) => {
    setIsLoading(true);
    setError(null);
    setStatus('running');
    setProjects([]);

    try {
      const response = await fetch('/api/projects/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(searchParams),
      });

      const data = await response.json();

      if (data.status === 'success') {
        setProjects(data.projects || []);
        setStatus('success');
      } else {
        setError(data.message || 'Search failed');
        setStatus('error');
      }
    } catch (err) {
      setError(err.message || 'Network error');
      setStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleParseUrl = async (url) => {
    setIsLoading(true);
    setError(null);
    setStatus('running');

    try {
      const response = await fetch('/api/projects/parse', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();

      if (data.status === 'success') {
        setProjects([data.project]);
        setStatus('success');
      } else {
        setError(data.message || 'Failed to parse project');
        setStatus('error');
      }
    } catch (err) {
      setError(err.message || 'Network error');
      setStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <Head>
        <title>Freelance Project Search</title>
        <meta name="description" content="Search and parse projects from freelance platforms" />
        <link rel="icon" href="/favicon.ico" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </Head>
      <main className="page">
        <header className="page-header">
          <div>
            <h1>Freelance Project Search</h1>
            <p className="subtitle">
              Search and parse projects from freelance platforms with advanced filtering
            </p>
          </div>
        </header>

        <div className="card">
          <header className="card-header">
            <h2>Search Projects</h2>
          </header>
          <ProjectSearchForm
            onSearch={handleSearch}
            onParseUrl={handleParseUrl}
            isLoading={isLoading}
            status={status}
          />
          {error && (
            <div className="alert alert-error">
              <strong>Error:</strong> {error}
            </div>
          )}
        </div>

        {projects.length > 0 && (
          <ProjectResults projects={projects} />
        )}
      </main>
    </>
  );
}

