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
        this.stopBtn = document.getElementById('stop-btn');
        this.clearLogsBtn = document.getElementById('clear-logs');

        this.init();
    }

    init() {
        this.bindEvents();
        this.startLogStream();
        this.updateStatus();
    }

    bindEvents() {
        this.startBtn.addEventListener('click', () => this.startAgent());
        this.stopBtn.addEventListener('click', () => this.stopAgent());
        this.clearLogsBtn.addEventListener('click', () => this.clearLogs());
    }

    startLogStream() {
        this.eventSource = new EventSource('/logs/stream');

        this.eventSource.onmessage = (event) => {
            try {
                const logData = JSON.parse(event.data);
                this.addLogEntry(logData);
            } catch (e) {
                console.error('Error parsing log data:', e);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            this.addLogEntry({
                timestamp: new Date().toISOString(),
                level: 'ERROR',
                message: 'Connection to log stream lost. Retrying...',
                module: 'dashboard'
            });

            // Auto-reconnect after 5 seconds
            setTimeout(() => {
                if (this.eventSource.readyState === EventSource.CLOSED) {
                    this.startLogStream();
                }
            }, 5000);
        };

        // Initial connection message
        this.addLogEntry({
            timestamp: new Date().toISOString(),
            level: 'INFO',
            message: 'Dashboard connected to log stream',
            module: 'dashboard'
        });
    }

    addLogEntry(logData) {
        const entry = document.createElement('div');
        entry.className = `log-entry log-${logData.level.toLowerCase()}`;

        const timestamp = new Date(logData.timestamp).toLocaleTimeString();
        const level = logData.level.padEnd(8);
        const module = logData.module ? `[${logData.module}]` : '';
        const message = logData.message;

        entry.textContent = `${timestamp} ${level} ${module} ${message}`;

        this.logsContainer.appendChild(entry);
        this.logsContainer.scrollTop = this.logsContainer.scrollHeight;

        // Keep only last 1000 entries to prevent memory issues
        while (this.logsContainer.children.length > 1000) {
            this.logsContainer.removeChild(this.logsContainer.firstChild);
        }
    }

    async updateStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            // Update agent status
            this.agentStatus.textContent = this.formatStatus(data.agent_a_status);
            this.agentStatus.className = `status-${data.agent_a_status}`;

            // Update buttons
            if (data.agent_a_status === 'running') {
                this.startBtn.disabled = true;
                this.stopBtn.disabled = false;
            } else {
                this.startBtn.disabled = false;
                this.stopBtn.disabled = true;
            }

            // Update stats
            this.projectsCount.textContent = data.projects_found || 0;
            this.lastCheck.textContent = data.last_check ?
                new Date(data.last_check).toLocaleString() : '-';

        } catch (error) {
            console.error('Error updating status:', error);
        }

        // Update every 5 seconds
        setTimeout(() => this.updateStatus(), 5000);
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
                    message: 'Agent started successfully',
                    module: 'dashboard'
                });
            } else {
                throw new Error(data.message);
            }

        } catch (error) {
            this.addLogEntry({
                timestamp: new Date().toISOString(),
                level: 'ERROR',
                message: `Failed to start agent: ${error.message}`,
                module: 'dashboard'
            });
            this.startBtn.disabled = false;
            this.startBtn.textContent = '▶️ Запустить';
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
        this.logsContainer.innerHTML = '';
        this.addLogEntry({
            timestamp: new Date().toISOString(),
            level: 'INFO',
            message: 'Logs cleared',
            module: 'dashboard'
        });
    }

    destroy() {
        if (this.eventSource) {
            this.eventSource.close();
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
