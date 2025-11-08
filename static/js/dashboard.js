// Dashboard JavaScript for real-time updates
class Dashboard {
    constructor() {
        this.eventSource = null;
        this.logsContainer = document.getElementById('logs');
        this.agentStatus = document.getElementById('agent-status');
        this.projectsCount = document.getElementById('projects-count');
        this.suitableCount = document.getElementById('suitable-count');
        this.lastCheck = document.getElementById('last-check');
        this.startBtn = document.getElementById('start-btn');
        this.runSessionBtn = document.getElementById('run-session-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.clearLogsBtn = document.getElementById('clear-logs');
        this.sessionInfo = document.getElementById('session-info');
        this.sessionTime = document.getElementById('session-time');
        this.sessionStep = document.getElementById('session-step');

        this.init();
    }

    init() {
        this.bindEvents();
        // Load status immediately on init
        this.updateStatus().then(() => {
            // Start log stream after status is loaded
            this.startLogStream();
            // Update session info every second
            setInterval(() => this.updateSessionInfo(), 1000);
        });
    }

    bindEvents() {
        this.startBtn.addEventListener('click', () => this.startAgent());
        this.runSessionBtn.addEventListener('click', () => this.runSingleSession());
        this.stopBtn.addEventListener('click', () => this.stopAgent());
        this.clearLogsBtn.addEventListener('click', () => this.clearLogs());
    }

    startLogStream() {
        // Use simple polling instead of SSE for reliable line-by-line display
        this.logInterval = setInterval(() => {
            this.fetchLogs();
        }, 1000); // Update every second

        // Initial fetch
        this.fetchLogs();

        // Initial connection message
        this.addLogEntry({
            timestamp: new Date().toISOString(),
            level: 'INFO',
            message: 'Dashboard connected to log polling',
            module: 'dashboard'
        });
    }

    async fetchLogs() {
        try {
            const response = await fetch('/logs');
            if (response.ok) {
                const logText = await response.text();
                this.updateLogsDisplay(logText);
            }
        } catch (error) {
            console.error('Error fetching logs:', error);
        }
    }

    updateLogsDisplay(logText) {
        // Clear and set new content
        this.logsContainer.textContent = logText;

        // Auto-scroll to bottom
        this.logsContainer.scrollTop = this.logsContainer.scrollHeight;
    }

    addLogEntry(logData) {
        const entry = document.createElement('div');
        entry.className = `log-entry log-${logData.level.toLowerCase()}`;

        const timestamp = new Date(logData.timestamp).toLocaleTimeString();
        const level = logData.level.padEnd(8);
        const module = logData.module ? `[${logData.module}]` : '';
        let message = logData.message;

        // Highlight different log types with specific colors
        if (message.includes('[SELENIUM]')) {
            entry.style.color = '#4fc3f7';
            entry.style.borderLeftColor = '#4fc3f7';
            entry.style.fontWeight = '500';
        } else if (message.includes('[SESSION]')) {
            entry.style.color = '#ba68c8';
            entry.style.borderLeftColor = '#ba68c8';
            entry.style.fontWeight = '500';
        } else if (message.includes('[DEMO]')) {
            entry.style.color = '#ffb74d';
            entry.style.borderLeftColor = '#ffb74d';
            entry.style.fontWeight = '500';
        } else if (message.includes('[EVALUATION]')) {
            entry.style.color = '#81c784';
            entry.style.borderLeftColor = '#81c784';
        } else if (message.includes('[TELEGRAM]') || message.includes('[N8N]')) {
            entry.style.color = '#64b5f6';
            entry.style.borderLeftColor = '#64b5f6';
        }

        // Format log entry with better spacing
        entry.textContent = `${timestamp} │ ${level} │ ${module} ${message}`;

        this.logsContainer.appendChild(entry);
        // Auto-scroll to bottom with smooth behavior
        this.logsContainer.scrollTo({
            top: this.logsContainer.scrollHeight,
            behavior: 'smooth'
        });

        // Keep only last 1000 entries to prevent memory issues
        while (this.logsContainer.children.length > 1000) {
            this.logsContainer.removeChild(this.logsContainer.firstChild);
        }
        
        // Try to extract current step from message for session info
        this.extractSessionStep(message);
    }
    
    extractSessionStep(message) {
        // Extract step information from log messages
        if (message.includes('Step 1/3')) {
            this.sessionStep.textContent = 'Step 1/3: Searching projects...';
        } else if (message.includes('Step 2/3')) {
            this.sessionStep.textContent = 'Step 2/3: Evaluating projects...';
        } else if (message.includes('Step 3/3')) {
            this.sessionStep.textContent = 'Step 3/3: Sending notifications...';
        } else if (message.includes('[SELENIUM]')) {
            // Extract action from Selenium logs
            const match = message.match(/\[SELENIUM\]\s+(.+?)(?:\s+|$)/);
            if (match) {
                const action = match[1].replace(/[🔧✅⚠️❌🌐👁️⏱️💰📄🔍]/g, '').trim();
                this.sessionStep.textContent = `Selenium: ${action.substring(0, 40)}...`;
            }
        } else if (message.includes('[SESSION]')) {
            // Extract session step
            const match = message.match(/\[SESSION\]\s+(.+?)(?:\s+|$)/);
            if (match) {
                const action = match[1].replace(/[🚀🔍📊⏱️✅❌📈]/g, '').trim();
                this.sessionStep.textContent = `Session: ${action.substring(0, 40)}...`;
            }
        } else if (message.includes('[EVALUATION]')) {
            this.sessionStep.textContent = 'Evaluation: Processing projects...';
        } else if (message.includes('[DEMO]')) {
            this.sessionStep.textContent = 'Demo: Generating projects...';
        }
    }

    async updateStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            // Update agent status
            this.agentStatus.textContent = this.formatStatus(data.agent_a_status);
            this.agentStatus.className = `status-${data.agent_a_status}`;

            // Update buttons based on running status
            if (data.is_running) {
                this.startBtn.disabled = true;
                this.runSessionBtn.disabled = true;
                this.stopBtn.disabled = false;
            } else if (data.agent_a_status === 'running') {
                // Session is running but not continuous
                this.startBtn.disabled = true;
                this.runSessionBtn.disabled = true;
                this.stopBtn.disabled = false;
            } else {
                this.startBtn.disabled = false;
                this.runSessionBtn.disabled = false;
                this.stopBtn.disabled = true;
            }

            // Update stats
            this.projectsCount.textContent = data.projects_found || 0;
            this.suitableCount.textContent = data.suitable_projects || 0;
            this.lastCheck.textContent = data.last_check ?
                new Date(data.last_check).toLocaleString() : '-';

            // Update session info
            if (data.current_session) {
                this.sessionInfo.style.display = 'block';
                this.updateSessionInfo();
            } else {
                this.sessionInfo.style.display = 'none';
            }

        } catch (error) {
            console.error('Error updating status:', error);
        }

        // Update every 2 seconds for more responsive UI
        setTimeout(() => this.updateStatus(), 2000);
    }
    
    async updateSessionInfo() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            if (data.current_session) {
                const elapsed = data.current_session.elapsed_seconds;
                const minutes = Math.floor(elapsed / 60);
                const seconds = Math.floor(elapsed % 60);
                this.sessionTime.textContent = `${minutes}m ${seconds}s`;
                this.sessionStep.textContent = `Step ${data.current_session.steps || 0}`;
            }
        } catch (error) {
            // Silently fail
        }
    }

    formatStatus(status) {
        const statusMap = {
            'running': '🔄 Работает',
            'stopped': '⏹️ Остановлен',
            'waiting': '⏳ Ожидает',
            'error': '❌ Ошибка'
        };
        return statusMap[status] || status;
    }

    async startAgent() {
        try {
            this.startBtn.disabled = true;
            this.startBtn.textContent = '⏳ Запуск...';

            const response = await fetch('/agent/start', { method: 'POST' });
            const data = await response.json();

            if (data.status === 'started') {
                this.addLogEntry({
                    timestamp: new Date().toISOString(),
                    level: 'INFO',
                    message: '✅ Continuous agent started successfully',
                    module: 'dashboard'
                });
                // Update status to reflect running agent
                await this.updateStatus();
            } else if (data.status === 'already_running') {
                this.addLogEntry({
                    timestamp: new Date().toISOString(),
                    level: 'WARNING',
                    message: `⚠️ ${data.message}`,
                    module: 'dashboard'
                });
                this.startBtn.disabled = false;
                this.startBtn.textContent = '▶️ Запустить (Continuous)';
            } else {
                throw new Error(data.message);
            }

        } catch (error) {
            this.addLogEntry({
                timestamp: new Date().toISOString(),
                level: 'ERROR',
                message: `❌ Failed to start agent: ${error.message}`,
                module: 'dashboard'
            });
            this.startBtn.disabled = false;
            this.startBtn.textContent = '▶️ Запустить (Continuous)';
        }
    }
    
    async runSingleSession() {
        try {
            this.runSessionBtn.disabled = true;
            this.runSessionBtn.textContent = '⏳ Запуск сессии...';

            const response = await fetch('/agent/run-session', { method: 'POST' });
            const data = await response.json();

            if (data.status === 'session_started') {
                this.addLogEntry({
                    timestamp: new Date().toISOString(),
                    level: 'INFO',
                    message: '🚀 Single session started successfully',
                    module: 'dashboard'
                });
                // Update status to reflect running session
                await this.updateStatus();
            } else if (data.status === 'busy') {
                this.addLogEntry({
                    timestamp: new Date().toISOString(),
                    level: 'WARNING',
                    message: `⚠️ ${data.message}`,
                    module: 'dashboard'
                });
                this.runSessionBtn.disabled = false;
                this.runSessionBtn.textContent = '🚀 Запустить одну сессию';
            } else {
                throw new Error(data.message);
            }

        } catch (error) {
            this.addLogEntry({
                timestamp: new Date().toISOString(),
                level: 'ERROR',
                message: `❌ Failed to start session: ${error.message}`,
                module: 'dashboard'
            });
            this.runSessionBtn.disabled = false;
            this.runSessionBtn.textContent = '🚀 Запустить одну сессию';
        }
    }

    async stopAgent() {
        try {
            this.stopBtn.disabled = true;
            this.stopBtn.textContent = '⏳ Остановка...';

            const response = await fetch('/agent/stop', { method: 'POST' });
            const data = await response.json();

            if (data.status === 'stopped') {
                this.addLogEntry({
                    timestamp: new Date().toISOString(),
                    level: 'INFO',
                    message: 'Agent stopped successfully',
                    module: 'dashboard'
                });
            } else {
                throw new Error(data.message);
            }

        } catch (error) {
            this.addLogEntry({
                timestamp: new Date().toISOString(),
                level: 'ERROR',
                message: `Failed to stop agent: ${error.message}`,
                module: 'dashboard'
            });
            this.stopBtn.disabled = false;
            this.stopBtn.textContent = '⏹️ Остановить';
        }
    }

    clearLogs() {
        // Clear logs display
        this.logsContainer.textContent = '';

        // Add cleared message
        this.logsContainer.textContent = `[${new Date().toISOString().slice(0,19)}] INFO: Logs cleared by user\n`;

        // Auto-scroll to bottom
        this.logsContainer.scrollTop = this.logsContainer.scrollHeight;
    }

    destroy() {
        if (this.logInterval) {
            clearInterval(this.logInterval);
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.dashboard) {
        window.dashboard.destroy();
    }
});
