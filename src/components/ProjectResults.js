export default function ProjectResults({ projects }) {
  if (!projects || projects.length === 0) {
    return null;
  }

  const getScoreBadge = (score) => {
    if (!score) return null;
    
    let className = 'project-score';
    if (score >= 0.8) {
      className += ' score-high';
    } else if (score >= 0.5) {
      className += ' score-medium';
    } else {
      className += ' score-low';
    }

    return (
      <span className={className}>
        Score: {(score * 100).toFixed(0)}%
      </span>
    );
  };

  const formatBudget = (budget) => {
    if (!budget) return 'Not specified';
    return budget;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString();
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="card" style={{ marginTop: '24px' }}>
      <header className="card-header">
        <h2>Search Results</h2>
        <p>Found {projects.length} project(s)</p>
      </header>
      <div className="results-list">
        {projects.map((project, index) => (
          <div key={index} className="project-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
              <h3 className="project-title">{project.title || 'Untitled'}</h3>
              {project.evaluation && getScoreBadge(project.evaluation.totalScore)}
            </div>
            
            {project.description && (
              <p className="project-description">
                {project.description.length > 300 
                  ? `${project.description.substring(0, 300)}...` 
                  : project.description}
              </p>
            )}

            <div className="project-meta">
              {project.budget && (
                <span>
                  <strong>Budget:</strong> {formatBudget(project.budget)}
                </span>
              )}
              {project.url && (
                <span>
                  <a href={project.url} target="_blank" rel="noopener noreferrer" style={{ color: '#60a5fa' }}>
                    View Project
                  </a>
                </span>
              )}
              {project.evaluation && (
                <>
                  {project.evaluation.relevanceScore !== undefined && (
                    <span>
                      <strong>Relevance:</strong> {(project.evaluation.relevanceScore * 100).toFixed(0)}%
                    </span>
                  )}
                  {project.evaluation.timeScore !== undefined && (
                    <span>
                      <strong>Time Score:</strong> {(project.evaluation.timeScore * 100).toFixed(0)}%
                    </span>
                  )}
                  {project.evaluation.proposalsScore !== undefined && (
                    <span>
                      <strong>Proposals Score:</strong> {(project.evaluation.proposalsScore * 100).toFixed(0)}%
                    </span>
                  )}
                </>
              )}
            </div>

            {project.evaluation && project.evaluation.reasoning && (
              <div style={{ marginTop: '12px', padding: '12px', background: 'rgba(15, 23, 42, 0.6)', borderRadius: '8px', fontSize: '0.85rem', color: '#9ca3af' }}>
                <strong>Evaluation:</strong> {project.evaluation.reasoning}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

