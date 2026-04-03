/**
 * MyAPS 监控面板 JavaScript
 */

const API_BASE = '/monitor/api';
let resourceChart = null;
let refreshInterval = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initResourceChart();
    refreshAll();
    startAutoRefresh();
});

// 自动刷新
function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    refreshInterval = setInterval(refreshAll, 10000);
}

// 刷新所有数据
async function refreshAll() {
    await Promise.all([
        fetchHealth(),
        fetchResource(),
        fetchDatabase(),
        fetchScheduler(),
        fetchHTTP(),
        fetchAlerts(),
        fetchLogs()
    ]);
    updateLastUpdateTime();
}

// 获取健康状态
async function fetchHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        updateHealthStatus(data);
    } catch (error) {
        console.error('获取健康状态失败:', error);
        setSystemStatus('error', '连接失败');
    }
}

// 更新健康状态显示
function updateHealthStatus(data) {
    const indicator = document.getElementById('status-indicator');
    const statusMap = {
        'healthy': { text: '● 系统正常', class: 'healthy' },
        'degraded': { text: '● 部分警告', class: 'warning' },
        'unhealthy': { text: '● 系统异常', class: 'error' }
    };

    const status = statusMap[data.status] || statusMap['unhealthy'];
    indicator.textContent = status.text;
    indicator.className = `status ${status.class}`;
}

// 设置系统状态
function setSystemStatus(status, text) {
    const indicator = document.getElementById('status-indicator');
    indicator.textContent = `● ${text}`;
    indicator.className = `status ${status}`;
}

// 获取资源指标
async function fetchResource() {
    try {
        const response = await fetch(`${API_BASE}/resource`);
        const data = await response.json();
        updateResourceDisplay(data);
    } catch (error) {
        console.error('获取资源指标失败:', error);
    }
}

// 更新资源显示
function updateResourceDisplay(data) {
    if (data.error) {
        document.getElementById('resource-badge').textContent = '错误';
        document.getElementById('resource-badge').className = 'badge error';
        return;
    }

    // CPU
    const cpuValue = data.cpu?.system || 0;
    document.getElementById('cpu-value').textContent = `${cpuValue}%`;
    const cpuBar = document.getElementById('cpu-bar');
    cpuBar.style.width = `${Math.min(cpuValue, 100)}%`;
    cpuBar.className = `progress-fill ${getProgressClass(cpuValue)}`;

    // 内存
    const memValue = data.memory?.rss || 0;
    const memPercent = data.memory?.percent || 0;
    document.getElementById('memory-value').textContent = `${memValue} MB (${memPercent}%)`;
    const memBar = document.getElementById('memory-bar');
    memBar.style.width = `${Math.min(memPercent, 100)}%`;
    memBar.className = `progress-fill ${getProgressClass(memPercent)}`;

    // 线程数
    document.getElementById('threads-value').textContent = data.threads || '--';

    // 运行时间
    document.getElementById('uptime-value').textContent = formatUptime(data.uptime || 0);

    // 更新图表
    updateResourceChart(cpuValue, memPercent);

    // 更新徽章
    const badge = document.getElementById('resource-badge');
    badge.textContent = '运行中';
    badge.className = 'badge healthy';
}

// 获取进度条颜色类
function getProgressClass(value) {
    if (value >= 80) return 'error';
    if (value >= 60) return 'warning';
    return '';
}

// 格式化运行时间
function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) {
        return `${days}天 ${hours}小时`;
    } else if (hours > 0) {
        return `${hours}小时 ${minutes}分钟`;
    } else {
        return `${minutes}分钟`;
    }
}

// 初始化资源图表
function initResourceChart() {
    const ctx = document.getElementById('resource-chart').getContext('2d');
    resourceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'CPU %',
                    data: [],
                    borderColor: '#1890ff',
                    backgroundColor: 'rgba(24, 144, 255, 0.1)',
                    fill: true,
                    tension: 0.4
                },
                {
                    label: '内存 %',
                    data: [],
                    borderColor: '#52c41a',
                    backgroundColor: 'rgba(82, 196, 26, 0.1)',
                    fill: true,
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100
                }
            },
            plugins: {
                legend: {
                    position: 'top'
                }
            },
            animation: {
                duration: 300
            }
        }
    });
}

// 更新资源图表
function updateResourceChart(cpu, memory) {
    const now = new Date();
    const timeLabel = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;

    resourceChart.data.labels.push(timeLabel);
    resourceChart.data.datasets[0].data.push(cpu);
    resourceChart.data.datasets[1].data.push(memory);

    // 保持最多20个数据点
    if (resourceChart.data.labels.length > 20) {
        resourceChart.data.labels.shift();
        resourceChart.data.datasets[0].data.shift();
        resourceChart.data.datasets[1].data.shift();
    }

    resourceChart.update('none');
}

// 获取数据库指标
async function fetchDatabase() {
    try {
        const response = await fetch(`${API_BASE}/database`);
        const data = await response.json();
        updateDatabaseDisplay(data);
    } catch (error) {
        console.error('获取数据库指标失败:', error);
    }
}

// 更新数据库显示
function updateDatabaseDisplay(data) {
    const connections = data.connections || {};
    const summary = connections.summary || {};

    // 更新汇总
    document.getElementById('db-total').textContent = summary.total || 0;
    document.getElementById('db-healthy').textContent = summary.healthy || 0;
    document.getElementById('db-unhealthy').textContent = summary.unhealthy || 0;

    // 更新徽章
    const badge = document.getElementById('db-badge');
    if (summary.unhealthy === 0) {
        badge.textContent = '正常';
        badge.className = 'badge healthy';
    } else {
        badge.textContent = '异常';
        badge.className = 'badge warning';
    }

    // 更新连接列表
    const listEl = document.getElementById('db-list');
    const dbConnections = connections.connections || {};

    if (Object.keys(dbConnections).length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无数据库连接</div>';
        return;
    }

    listEl.innerHTML = Object.entries(dbConnections).map(([name, status]) => `
        <div class="db-item">
            <span class="db-name">${name}</span>
            <span class="db-status">
                <span class="status-dot ${status.healthy ? 'healthy' : 'error'}"></span>
                ${status.healthy ? '正常' : (status.error || '异常')}
            </span>
        </div>
    `).join('');
}

// 获取定时任务指标
async function fetchScheduler() {
    try {
        const response = await fetch(`${API_BASE}/scheduler`);
        const data = await response.json();
        updateSchedulerDisplay(data);
    } catch (error) {
        console.error('获取定时任务指标失败:', error);
    }
}

// 更新定时任务显示
function updateSchedulerDisplay(data) {
    const scheduler = data.scheduler || {};
    const jobs = data.jobs || [];

    // 更新调度器状态
    const statusEl = document.getElementById('scheduler-status');
    const badge = document.getElementById('scheduler-badge');

    if (scheduler.running) {
        statusEl.textContent = '运行中';
        statusEl.style.color = '#52c41a';
        badge.textContent = '运行中';
        badge.className = 'badge healthy';
    } else {
        statusEl.textContent = '已停止';
        statusEl.style.color = '#faad14';
        badge.textContent = '已停止';
        badge.className = 'badge warning';
    }

    // 更新任务数量
    document.getElementById('job-count').textContent = jobs.length;

    // 更新任务列表
    const listEl = document.getElementById('job-list');

    if (jobs.length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无定时任务</div>';
        return;
    }

    listEl.innerHTML = jobs.map(job => `
        <div class="job-item">
            <div class="job-info">
                <span class="job-name">${job.name || job.id}</span>
                <span class="job-trigger">${job.trigger}</span>
            </div>
            <span class="job-next">${job.next_run_time ? formatDateTime(job.next_run_time) : '未计划'}</span>
        </div>
    `).join('');
}

// 格式化日期时间
function formatDateTime(isoString) {
    const date = new Date(isoString);
    return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
}

// 获取告警
async function fetchAlerts() {
    try {
        const response = await fetch(`${API_BASE}/alerts?limit=10`);
        const data = await response.json();
        updateAlertsDisplay(data.alerts || []);
    } catch (error) {
        console.error('获取告警失败:', error);
    }
}

// 获取 HTTP 指标
async function fetchHTTP() {
    try {
        const response = await fetch(`${API_BASE}/http`);
        const data = await response.json();
        updateHTTPDisplay(data);
    } catch (error) {
        console.error('获取 HTTP 指标失败:', error);
    }
}

// 更新 HTTP 显示
function updateHTTPDisplay(data) {
    const summary = data.summary || {};

    // 更新汇总数据
    document.getElementById('http-total').textContent = summary.total_requests || 0;
    document.getElementById('http-error-rate').textContent = (summary.error_rate || 0) + '%';
    document.getElementById('http-avg-time').textContent = ((summary.avg_response_time || 0) * 1000).toFixed(0) + 'ms';
    document.getElementById('http-rpm').textContent = summary.requests_per_minute || 0;

    // 更新徽章
    const badge = document.getElementById('http-badge');
    const errorRate = summary.error_rate || 0;
    if (errorRate < 1) {
        badge.textContent = '正常';
        badge.className = 'badge healthy';
    } else if (errorRate < 5) {
        badge.textContent = '警告';
        badge.className = 'badge warning';
    } else {
        badge.textContent = '异常';
        badge.className = 'badge error';
    }

    // 更新状态码分布
    const statusCodesEl = document.getElementById('http-status-codes');
    const statusCodes = data.status_codes || {};

    if (Object.keys(statusCodes).length === 0) {
        statusCodesEl.innerHTML = '<div class="empty-state">暂无数据</div>';
    } else {
        statusCodesEl.innerHTML = Object.entries(statusCodes).map(([code, count]) => {
            const codeClass = code.startsWith('2') ? 'success' : (code.startsWith('3') ? 'redirect' : 'error');
            return `
                <div class="status-code-item">
                    <span class="status-code ${codeClass}">${code}</span>
                    <span>${count}</span>
                </div>
            `;
        }).join('');
    }

    // 更新路径统计
    const pathsEl = document.getElementById('http-paths');
    const pathStats = data.path_stats || {};

    if (Object.keys(pathStats).length === 0) {
        pathsEl.innerHTML = '<div class="empty-state">暂无路径数据</div>';
    } else {
        const sortedPaths = Object.entries(pathStats)
            .sort((a, b) => b[1].count - a[1].count)
            .slice(0, 10);

        pathsEl.innerHTML = sortedPaths.map(([path, stats]) => `
            <div class="http-path-item">
                <div class="http-path-info">
                    <span class="http-path-name">${path}</span>
                    <div class="http-path-stats">
                        <span>平均: ${(stats.avg_time * 1000).toFixed(0)}ms</span>
                        ${stats.errors > 0 ? `<span style="color: var(--error-color)">错误: ${stats.errors}</span>` : ''}
                        ${stats.slow_requests > 0 ? `<span style="color: var(--warning-color)">慢请求: ${stats.slow_requests}</span>` : ''}
                    </div>
                </div>
                <span class="http-path-count">${stats.count}</span>
            </div>
        `).join('');
    }
}

// 更新告警显示
function updateAlertsDisplay(alerts) {
    const listEl = document.getElementById('alert-list');

    if (alerts.length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无告警</div>';
        return;
    }

    listEl.innerHTML = alerts.map(alert => `
        <div class="alert-item ${alert.level}">
            <span class="alert-message">${alert.message}</span>
            <span class="alert-time">${formatTimeAgo(alert.timestamp)}</span>
        </div>
    `).join('');
}

// 格式化相对时间
function formatTimeAgo(timestamp) {
    const now = new Date();
    const date = new Date(timestamp * 1000);
    const diff = now.getTime() / 1000 - timestamp;

    // 今天
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    // 昨天
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    // 前天
    const dayBeforeYesterday = new Date(today);
    dayBeforeYesterday.setDate(dayBeforeYesterday.getDate() - 2);

    const logDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    // 判断是否是今天、昨天、前天
    let dayLabel = '';
    if (logDate.getTime() === today.getTime()) {
        dayLabel = '今天';
    } else if (logDate.getTime() === yesterday.getTime()) {
        dayLabel = '昨天';
    } else if (logDate.getTime() === dayBeforeYesterday.getTime()) {
        dayLabel = '前天';
    } else {
        // 显示具体日期
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const day = date.getDate().toString().padStart(2, '0');
        return `${month}-${day}`;
    }

    // 今天、昨天、前天显示具体时间
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${dayLabel} ${hours}:${minutes}`;
}

// 清空告警
async function clearAlerts() {
    try {
        await fetch(`${API_BASE}/alerts/clear`, { method: 'POST' });
        fetchAlerts();
    } catch (error) {
        console.error('清空告警失败:', error);
    }
}

// 获取日志
async function fetchLogs() {
    try {
        const level = document.getElementById('log-level').value;
        const url = `${API_BASE}/logs?limit=20${level ? `&level=${level}` : ''}`;
        const response = await fetch(url);
        const data = await response.json();
        updateLogsDisplay(data.logs);
    } catch (error) {
        console.error('获取日志失败:', error);
    }
}

// 更新日志显示
function updateLogsDisplay(logs) {
    const listEl = document.getElementById('log-list');

    if (logs.length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无日志</div>';
        return;
    }

    listEl.innerHTML = logs.map(log => `
        <div class="log-item ${log.level}">
            <div class="log-header">
                <div class="log-level ${log.level}">${log.level === 'warning' ? '警告' : '错误'}</div>
                <div class="log-info">
                    <span class="log-module">${log.module}</span>
                    <span class="log-time">${formatTimeAgo(log.timestamp)}</span>
                </div>
            </div>
            <div class="log-message">${log.message}</div>
            ${log.traceback ? `<div class="log-traceback">${log.traceback}</div>` : ''}
        </div>
    `).join('');
}

// 更新最后更新时间
function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    document.getElementById('last-update').textContent = `最后更新: ${timeStr}`;
}
