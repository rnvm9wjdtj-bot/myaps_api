/**
 * MyAPS 监控面板 JavaScript
 */

const API_BASE = '/monitor/api';
let resourceChart = null;
let refreshInterval = null;
let originalTitle = document.title;
let titleAlertInterval = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initResourceChart();
    fetchEnvironment();
    refreshAll();
    startAutoRefresh();
});

// 获取环境变量
async function fetchEnvironment() {
    try {
        const response = await fetch(`${API_BASE}/env`);
        const data = await response.json();
        updateTitleWithEnvironment(data);
    } catch (error) {
        console.error('获取环境变量失败:', error);
    }
}

// 更新title为环境变量
function updateTitleWithEnvironment(env) {
    const projectDir = env.project_dir || 'MyAPI';
    const projectJson = env.project_json.split('.')[0] || '';
    originalTitle = `${projectDir} ${projectJson} 监控面板`;
    document.title = originalTitle;
}

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
        // 刷新各个页面的数据
        fetchAPIRequests(),
        fetchOutboundRequests(),
        fetchDatabaseDetail(),
        fetchSchedulerPage(),
        fetchLogsPage(),
        fetchOverviewOutboundRequests()
    ]);
    updateLastUpdateTime();
    checkAlertConditions();
}

// 检查告警条件并更新title
function checkAlertConditions() {
    const hasDbError = checkDatabaseError();
    const hasUnreadLogs = checkUnreadLogs();
    const hasSystemError = checkSystemStatus();
    
    if (hasDbError || hasUnreadLogs || hasSystemError) {
        startTitleAlert(hasSystemError);
    } else {
        stopTitleAlert();
    }
}

// 检查系统状态
function checkSystemStatus() {
    const statusIndicator = document.getElementById('status-indicator');
    return statusIndicator && statusIndicator.classList.contains('error');
}

// 检查数据库错误
function checkDatabaseError() {
    // 检查概览页面的数据库状态
    const dbBadge = document.getElementById('db-badge');
    if (dbBadge && (dbBadge.classList.contains('warning') || dbBadge.classList.contains('error'))) {
        return true;
    }
    
    // 检查数据库详情页面的状态
    const dbDetailBadge = document.getElementById('db-detail-badge');
    if (dbDetailBadge && (dbDetailBadge.classList.contains('warning') || dbDetailBadge.classList.contains('error'))) {
        return true;
    }
    
    return false;
}

// 检查未读日志
function checkUnreadLogs() {
    // 检查日志页面的未读状态
    const unreadLogs = document.querySelectorAll('#logs-tbody tr.unread');
    const hasUnread = unreadLogs.length > 0;
    
    // 更新红点角标的显示
    const logsBadge = document.getElementById('logs-badge');
    if (logsBadge) {
        logsBadge.style.display = hasUnread ? 'inline-block' : 'none';
    }
    
    return hasUnread;
}

// 开始title闪烁
function startTitleAlert(hasSystemError) {
    if (titleAlertInterval) {
        clearInterval(titleAlertInterval);
    }
    
    let blinkState = 0;
    let blinkPattern;
    
    if (hasSystemError) {
        // 系统错误时的闪烁模式：红色禁止图标 + 完整文字
        blinkPattern = [
            `⛔ ${originalTitle}`,  // 状态1：红色禁止图标 + 完整文字
            `⛔`,                  // 状态2：红色禁止图标 + 无文字
            `⛔ ${originalTitle}`,  // 状态3：红色禁止图标 + 完整文字
            `⛔`                   // 状态4：红色禁止图标 + 无文字
        ];
    } else {
        // 普通告警时的闪烁模式
        blinkPattern = [
            `🚨 ${originalTitle}`,  // 状态1：红色图标 + 完整文字
            `🚨`,                  // 状态2：红色图标 + 无文字
            `⚠️ ${originalTitle}`,  // 状态3：黄色图标 + 完整文字
            `⚠️`                   // 状态4：黄色图标 + 无文字
        ];
    }
    
    titleAlertInterval = setInterval(() => {
        // 循环切换闪烁状态
        blinkState = (blinkState + 1) % blinkPattern.length;
        document.title = blinkPattern[blinkState];
        
        // 每完成一轮闪烁（4次）后暂停一下，形成节律
        if (blinkState === 0) {
            clearInterval(titleAlertInterval);
            setTimeout(() => {
                const hasDbError = checkDatabaseError();
                const hasUnreadLogs = checkUnreadLogs();
                const hasSystemError = checkSystemStatus();
                if (hasDbError || hasUnreadLogs || hasSystemError) {
                    startTitleAlert(hasSystemError);
                }
            }, 800); // 暂停时间，调整节律
        }
    }, 300); // 闪烁速度，调整闪烁频率
}

// 停止title闪烁
function stopTitleAlert() {
    if (titleAlertInterval) {
        clearInterval(titleAlertInterval);
        titleAlertInterval = null;
        document.title = originalTitle;
    }
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
    document.getElementById('memory-percent').textContent = `${memPercent}%`;
    document.getElementById('memory-usage').textContent = `${memValue} M`;
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
    
    // 更新数据库页签的红点角标
    const databaseBadge = document.getElementById('database-badge');
    if (databaseBadge) {
        databaseBadge.style.display = summary.unhealthy > 0 ? 'inline-block' : 'none';
    }

    // 更新连接列表
    const listEl = document.getElementById('db-list');
    const dbConnections = connections.connections || {};

    if (Object.keys(dbConnections).length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无数据库连接</div>';
        checkAlertConditions();
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
    
    checkAlertConditions();
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
    
    // 更新接收请求页签的红点角标（仅在异常状态发生变化时显示）
    const apiRequestsBadge = document.getElementById('api-requests-badge');
    if (apiRequestsBadge) {
        const hasErrors = summary.error_rate > 0;
        actualErrorState['api-requests'] = hasErrors;
        const confirmedHasError = badgeConfirmedHasError['api-requests'];
        const errorStateChanged = hasErrors !== confirmedHasError;
        apiRequestsBadge.style.display = errorStateChanged ? 'inline-block' : 'none';
    }

    // 更新状态码分布
    const statusCodesEl = document.getElementById('http-status-codes');
    const statusCodes = data.status_codes || {};

    if (Object.keys(statusCodes).length === 0) {
        statusCodesEl.innerHTML = '<div class="no-data">暂无接收请求</div>';
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
        pathsEl.innerHTML = '<div class="no-data">&nbsp;</div>';
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
        checkAlertConditions();
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
    
    checkAlertConditions();
}

// 更新最后更新时间
function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    document.getElementById('last-update').textContent = `最后更新: ${timeStr}`;
}

// 页面切换逻辑
let currentPage = 'overview';
// 记录用户点击页签时的异常状态（是否有异常）
let badgeConfirmedHasError = {
    'api-requests': false,
    'outbound-requests': false
};
// 记录实际的异常状态
let actualErrorState = {
    'api-requests': false,
    'outbound-requests': false
};

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
});

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.getAttribute('data-page');
            switchPage(page);
        });
    });
}

function switchPage(pageName) {
    if (currentPage === pageName) return;
    
    currentPage = pageName;
    
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-page') === pageName) {
            item.classList.add('active');
        }
    });
    
    document.querySelectorAll('.page-content').forEach(page => {
        page.style.display = 'none';
    });
    
    const targetPage = document.getElementById(`page-${pageName}`);
    if (targetPage) {
        targetPage.style.display = 'grid';
    }
    
    // 当切换到接收请求或发送请求页签时，关闭对应的红点角标并记录当前异常状态
    if (pageName === 'api-requests') {
        const apiRequestsBadge = document.getElementById('api-requests-badge');
        if (apiRequestsBadge) {
            // 记录点击时的异常状态（使用实际的异常状态）
            badgeConfirmedHasError['api-requests'] = actualErrorState['api-requests'];
            apiRequestsBadge.style.display = 'none';
        }
        fetchAPIRequests();
    } else if (pageName === 'outbound-requests') {
        const outboundRequestsBadge = document.getElementById('outbound-requests-badge');
        if (outboundRequestsBadge) {
            // 记录点击时的异常状态（使用实际的异常状态）
            badgeConfirmedHasError['outbound-requests'] = actualErrorState['outbound-requests'];
            outboundRequestsBadge.style.display = 'none';
        }
        fetchOutboundRequests();
    } else if (pageName === 'database') {
        fetchDatabaseDetail();
    } else if (pageName === 'scheduler') {
        fetchSchedulerPage();
    } else if (pageName === 'logs') {
        fetchLogsPage();
    }
}

// 数据库详情页面
async function fetchDatabaseDetail() {
    try {
        const response = await fetch(`${API_BASE}/database`);
        const data = await response.json();
        updateDatabaseDetailDisplay(data);
    } catch (error) {
        console.error('获取数据库详情失败:', error);
    }
}

function updateDatabaseDetailDisplay(data) {
    const tbodyEl = document.getElementById('db-detail-tbody');
    const connections = data.connections || {};
    const dbConnections = connections.connections || {};
    const pools = data.pool?.pools || {};
    
    if (Object.keys(dbConnections).length === 0) {
        tbodyEl.innerHTML = '<tr><td colspan="11" class="empty-state">暂无数据库连接</td></tr>';
        checkAlertConditions();
        return;
    }
    
    const badge = document.getElementById('db-detail-badge');
    const summary = connections.summary || {};
    if (summary.unhealthy === 0) {
        badge.textContent = '正常';
        badge.className = 'badge healthy';
    } else {
        badge.textContent = '异常';
        badge.className = 'badge error';
    }
    
    // 更新数据库页签的红点角标
    const databaseBadge = document.getElementById('database-badge');
    if (databaseBadge) {
        databaseBadge.style.display = summary.unhealthy > 0 ? 'inline-block' : 'none';
    }
    
    tbodyEl.innerHTML = Object.entries(dbConnections).map(([name, status]) => {
        const pool = pools[name] || {};
        const stats = pool.stats || {};
        
        let connectionUsagePercent = 0;
        if (pool.used_connections && pool.max_size) {
            connectionUsagePercent = Math.round((pool.used_connections / pool.max_size) * 100);
        }
        
        let lastCheckTime = '-';
        if (status.last_check) {
            const checkDate = new Date(status.last_check * 1000);
            lastCheckTime = `${checkDate.getHours().toString().padStart(2, '0')}:${checkDate.getMinutes().toString().padStart(2, '0')}:${checkDate.getSeconds().toString().padStart(2, '0')}`;
        }
        
        return `
        <tr>
            <td>${name}</td>
            <td class="status-${status.healthy ? 'healthy' : 'error'}">
                ${status.healthy ? '已连接' : (status.error || '断开')}
            </td>
            <td>${lastCheckTime}</td>
            <td>${pool.current_size !== undefined ? pool.current_size : '-'}</td>
            <td>${pool.max_size !== undefined ? pool.max_size : '-'}</td>
            <td>${pool.min_size !== undefined ? pool.min_size : '-'}</td>
            <td>${pool.idle_connections !== undefined ? pool.idle_connections : '-'}</td>
            <td>${pool.used_connections !== undefined ? pool.used_connections : '-'}</td>
            <td>
                ${pool.max_size ? `
                <div class="progress-bar">
                    <div class="progress-fill ${connectionUsagePercent >= 80 ? 'error' : connectionUsagePercent >= 60 ? 'warning' : ''}" style="width: ${connectionUsagePercent}%"></div>
                </div>
                <span style="display: block; margin-top: 4px; font-size: 12px;">${connectionUsagePercent}%</span>
                ` : '-'}
            </td>
            <td>${stats.total_processed || 0}</td>
            <td>${stats.batches_executed || 0}</td>
        </tr>
        `;
    }).join('');
    
    checkAlertConditions();
}

// API 请求页面
async function fetchAPIRequests() {
    try {
        const response = await fetch(`${API_BASE}/http`);
        const data = await response.json();
        updateAPIRequestsDisplay(data);
    } catch (error) {
        console.error('获取 API 请求失败:', error);
    }
}

function updateAPIRequestsDisplay(data) {
    const tbodyEl = document.getElementById('api-requests-tbody');
    let requests = data.recent_requests || [];
    
    // 根据时间戳倒序排序
    requests.sort((a, b) => b.timestamp - a.timestamp);
    
    // 更新接收请求页签的红点角标（仅在异常状态发生变化时显示）
    const apiRequestsBadge = document.getElementById('api-requests-badge');
    if (apiRequestsBadge) {
        const hasErrors = requests.some(req => req.status_code >= 400);
        actualErrorState['api-requests'] = hasErrors;
        const confirmedHasError = badgeConfirmedHasError['api-requests'];
        const errorStateChanged = hasErrors !== confirmedHasError;
        apiRequestsBadge.style.display = errorStateChanged ? 'inline-block' : 'none';
    }
    
    if (requests.length === 0) {
        tbodyEl.innerHTML = '<tr><td colspan="8" class="empty-state">暂无 API 请求记录</td></tr>';
        return;
    }
    
    tbodyEl.innerHTML = requests.map((req, index) => {
        const date = new Date(req.timestamp * 1000);
        const timeStr = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2,'0')}-${date.getDate().toString().padStart(2,'0')} ${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}:${date.getSeconds().toString().padStart(2,'0')}`;
        
        const methodClass = req.method.toLowerCase();
        const isSuccess = req.status_code < 400;
        const statusClass = isSuccess ? 'success' : 'error';
        const errorMsg = req.error_message || '';
        
        // 转义特殊字符，防止HTML属性值被截断
        const escapedPath = req.path.replace(/"/g, '&quot;');
        const escapedErrorMsg = errorMsg.replace(/"/g, '&quot;');
        
        // 根据响应时间设置样式
        const durationMs = req.duration * 1000;
        let durationClass = '';
        if (durationMs > 1000) {
            durationClass = 'duration-slow';
        } else if (durationMs > 500) {
            durationClass = 'duration-medium';
        }
        
        // 处理查询参数显示
        let queryParamsDisplay = '';
        if (req.query_params) {
            try {
                const parsedParams = JSON.parse(req.query_params);
                if (Object.keys(parsedParams).length > 0) {
                    queryParamsDisplay = Object.entries(parsedParams)
                        .map(([key, value]) => `${key}=${value}`)
                        .join('&');
                }
            } catch (e) {
                queryParamsDisplay = req.query_params;
            }
        }
        
        // 获取状态码描述
        const getStatusDescription = (statusCode) => {
            const statusDescriptions = {
                200: 'OK',
                201: 'Created',
                202: 'Accepted',
                204: 'No Content',
                400: 'Bad Request',
                401: 'Unauthorized',
                403: 'Forbidden',
                404: 'Not Found',
                405: 'Method Not Allowed',
                500: 'Internal Server Error',
                501: 'Not Implemented',
                502: 'Bad Gateway',
                503: 'Service Unavailable'
            };
            return statusDescriptions[statusCode] || '';
        };
        
        const statusDescription = getStatusDescription(req.status_code);
        const statusText = statusDescription ? `${req.status_code} ${statusDescription}` : `${req.status_code}`;
        
        return `
            <tr onclick="showRequestDetail(${index})" data-request-index="${index}">
                <td>${timeStr}</td>
                <td><span class="api-method ${methodClass}">${req.method}</span></td>
                <td style="font-family: monospace; font-size: 12px;">${req.path}</td>
                <td style="font-family: monospace; font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${queryParamsDisplay}">${queryParamsDisplay || '-'}</td>
                <td><span class="api-status ${statusClass}">${statusText}</span></td>
                <td class="${durationClass}">${durationMs.toFixed(0)}ms</td>
                <td>${req.client_ip}</td>
                <td class="error-message-cell" title="${escapedErrorMsg}">${errorMsg}</td>
            </tr>
        `;
    }).join('');
    
    // 存储请求数据，以便点击时使用
    window.apiRequestsData = data;
}

// 显示请求详情
function showRequestDetail(index) {
    const data = window.apiRequestsData;
    if (!data || !data.recent_requests || !data.recent_requests[index]) {
        console.error('请求数据不存在');
        return;
    }
    
    const req = data.recent_requests[index];
    const modalEl = document.getElementById('api-request-modal');
    const requestInfoEl = document.getElementById('api-detail-request-info');
    const requestBodyEl = document.getElementById('api-detail-request-body');
    const responseBodyEl = document.getElementById('api-detail-response-body');
    
    // 格式化时间
    const date = new Date(req.timestamp * 1000);
    const timeStr = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2,'0')}-${date.getDate().toString().padStart(2,'0')} ${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}:${date.getSeconds().toString().padStart(2,'0')}`;
    
    // 处理查询参数显示
    let queryParamsDisplay = '';
    if (req.query_params) {
        try {
            const parsedParams = JSON.parse(req.query_params);
            if (Object.keys(parsedParams).length > 0) {
                queryParamsDisplay = Object.entries(parsedParams)
                    .map(([key, value]) => `${key}=${value}`)
                    .join('&');
            }
        } catch (e) {
            queryParamsDisplay = req.query_params;
        }
    }
    
    // 获取状态码描述
    const getStatusDescription = (statusCode) => {
        const statusDescriptions = {
            200: 'OK',
            201: 'Created',
            202: 'Accepted',
            204: 'No Content',
            400: 'Bad Request',
            401: 'Unauthorized',
            403: 'Forbidden',
            404: 'Not Found',
            405: 'Method Not Allowed',
            500: 'Internal Server Error',
            501: 'Not Implemented',
            502: 'Bad Gateway',
            503: 'Service Unavailable'
        };
        return statusDescriptions[statusCode] || '';
    };
    
    const statusDescription = getStatusDescription(req.status_code);
    const statusText = statusDescription ? `${req.status_code} ${statusDescription}` : `${req.status_code}`;
    
    // 更新请求信息
    requestInfoEl.innerHTML = `
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">时间戳</span>
            <span class="api-detail-info-value">${timeStr}</span>
        </div>
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">方法</span>
            <span class="api-detail-info-value">${req.method}</span>
        </div>
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">路径</span>
            <span class="api-detail-info-value">${req.path}</span>
        </div>
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">查询参数</span>
            <span class="api-detail-info-value" style="font-family: monospace; font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${queryParamsDisplay}">${queryParamsDisplay || '-'}</span>
        </div>
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">状态码</span>
            <span class="api-detail-info-value">${statusText}</span>
        </div>
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">响应时间</span>
            <span class="api-detail-info-value">${(req.duration * 1000).toFixed(0)}ms</span>
        </div>
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">客户端IP</span>
            <span class="api-detail-info-value">${req.client_ip}</span>
        </div>
        ${req.error_message ? `
        <div class="api-detail-info-item">
            <span class="api-detail-info-label">错误信息</span>
            <span class="api-detail-info-value" style="color: var(--error-color)">${req.error_message}</span>
        </div>
        ` : ''}
    `;
    
    // 更新请求体
    if (req.request_body) {
        try {
            // 尝试格式化 JSON
            const parsedBody = JSON.parse(req.request_body);
            const formattedBody = JSON.stringify(parsedBody, null, 2);
            requestBodyEl.textContent = formattedBody;
        } catch (e) {
            // 如果不是 JSON，直接显示
            requestBodyEl.textContent = req.request_body;
        }
    } else {
        requestBodyEl.textContent = '无请求体';
    }
    
    // 更新响应体
    if (req.response_body) {
        try {
            // 尝试格式化 JSON
            const parsedBody = JSON.parse(req.response_body);
            const formattedBody = JSON.stringify(parsedBody, null, 2);
            responseBodyEl.textContent = formattedBody;
        } catch (e) {
            // 如果不是 JSON，直接显示
            responseBodyEl.textContent = req.response_body;
        }
    } else {
        responseBodyEl.textContent = '无响应体';
    }
    
    // 重置高亮按钮状态
    document.querySelectorAll('.section-actions button').forEach(btn => {
        if (btn.textContent === '已高亮') {
            btn.textContent = '高亮';
        }
    });
    

    
    // 显示模态对话框
    modalEl.style.display = 'flex';
    
    // 阻止背景滚动
    document.body.style.overflow = 'hidden';
}

// 隐藏请求详情
function hideRequestDetail() {
    const modalEl = document.getElementById('api-request-modal');
    modalEl.style.display = 'none';
    
    // 恢复背景滚动
    document.body.style.overflow = '';
}

// 高亮请求体
function highlightRequestBody() {
    const requestBodyEl = document.getElementById('api-detail-request-body');
    if (typeof Prism !== 'undefined' && requestBodyEl) {
        Prism.highlightElement(requestBodyEl);
        // 更新按钮状态
        const btn = document.querySelector('.section-actions button:nth-child(1)');
        if (btn) {
            btn.textContent = '已高亮';
        }
    }
}

// 高亮响应体
function highlightResponseBody() {
    const responseBodyEl = document.getElementById('api-detail-response-body');
    if (typeof Prism !== 'undefined' && responseBodyEl) {
        Prism.highlightElement(responseBodyEl);
        // 更新按钮状态
        const btn = document.querySelectorAll('.section-actions')[1].querySelector('button:nth-child(1)');
        if (btn) {
            btn.textContent = '已高亮';
        }
    }
}

// 复制请求体到剪贴板
function copyRequestBody() {
    const requestBodyEl = document.getElementById('api-detail-request-body');
    if (requestBodyEl) {
        navigator.clipboard.writeText(requestBodyEl.textContent)
            .then(() => {
                // 显示复制成功提示
                const btn = document.querySelector('.section-actions button:nth-child(2)');
                if (btn) {
                    const originalText = btn.textContent;
                    btn.textContent = '已复制';
                    setTimeout(() => {
                        btn.textContent = originalText;
                    }, 2000);
                }
            })
            .catch(err => {
                console.error('复制失败:', err);
            });
    }
}

// 复制响应体到剪贴板
function copyResponseBody() {
    const responseBodyEl = document.getElementById('api-detail-response-body');
    if (responseBodyEl) {
        navigator.clipboard.writeText(responseBodyEl.textContent)
            .then(() => {
                // 显示复制成功提示
                const btn = document.querySelectorAll('.section-actions')[1].querySelector('button:nth-child(2)');
                if (btn) {
                    const originalText = btn.textContent;
                    btn.textContent = '已复制';
                    setTimeout(() => {
                        btn.textContent = originalText;
                    }, 2000);
                }
            })
            .catch(err => {
                console.error('复制失败:', err);
            });
    }
}

function refreshAPIRequests() {
    fetchAPIRequests();
}

async function resetAPIStats() {
    try {
        await fetch(`${API_BASE}/http/reset`, { method: 'POST' });
        fetchAPIRequests();
    } catch (error) {
        console.error('重置 API 统计失败:', error);
    }
}

// 日志页面
async function fetchLogsPage() {
    try {
        const level = document.getElementById('log-page-level').value;
        const url = `${API_BASE}/logs?limit=100${level ? `&level=${level}` : ''}`;
        const response = await fetch(url);
        const data = await response.json();
        updateLogsPageDisplay(data.logs);
    } catch (error) {
        console.error('获取日志失败:', error);
    }
}

function updateLogsPageDisplay(logs) {
    const tbodyEl = document.getElementById('logs-tbody');
    
    if (logs.length === 0) {
        tbodyEl.innerHTML = '<tr><td colspan="5" class="empty-state">暂无日志记录</td></tr>';
        checkAlertConditions();
        return;
    }
    
    // 从 localStorage 获取已读状态
    const readStatus = getReadStatusFromStorage();
    
    tbodyEl.innerHTML = logs.map(log => {
        const date = new Date(log.timestamp * 1000);
        const timeStr = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2,'0')}-${date.getDate().toString().padStart(2,'0')} ${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}:${date.getSeconds().toString().padStart(2,'0')}`;
        
        // 确保 title 属性使用完整的消息内容
        const fullMessage = log.message || '';
        
        // 生成唯一日志 ID
        const logId = generateLogId(log.timestamp, log.module, log.message);
        
        // 检查是否已读
        const isRead = readStatus.has(logId);
        const readStatusClass = isRead ? 'read' : 'unread';
        const readIcon = isRead ? '✓' : '';
        
        // 转义消息中的特殊字符，防止HTML属性值被截断
        const escapedFullMessage = fullMessage
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        return `
            <tr data-log-id="${logId}" class="${readStatusClass}">
                <td>${timeStr}</td>
                <td><span class="log-level-badge ${log.level}">${log.level.toUpperCase()}</span></td>
                <td>${log.module}</td>
                <td class="log-message-cell" title="${escapedFullMessage}" data-full-message="${escapedFullMessage}">${log.message}</td>
                <td class="read-status-cell">
                    <span class="read-checkbox ${readStatusClass}" onclick="toggleLogReadStatus('${logId}')">${readIcon}</span>
                </td>
            </tr>
        `;
    }).join('');
    
    checkAlertConditions();
    checkUnreadLogs();
    
    // 悬停效果由全局事件委托处理
}

// 生成日志唯一 ID
function generateLogId(timestamp, module, message) {
    const str = `${timestamp}:${module}:${message}`;
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
}

// 从 localStorage 获取已读状态
function getReadStatusFromStorage() {
    try {
        const stored = localStorage.getItem('monitor_log_read_status');
        return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch (e) {
        console.error('读取已读状态失败:', e);
        return new Set();
    }
}

// 保存已读状态到 localStorage
function saveReadStatusToStorage(readStatus) {
    try {
        localStorage.setItem('monitor_log_read_status', JSON.stringify(Array.from(readStatus)));
    } catch (e) {
        console.error('保存已读状态失败:', e);
    }
}

// 切换日志已读状态
function toggleLogReadStatus(logId) {
    const readStatus = getReadStatusFromStorage();
    
    if (readStatus.has(logId)) {
        readStatus.delete(logId);
    } else {
        readStatus.add(logId);
    }
    
    saveReadStatusToStorage(readStatus);
    
    // 更新显示
    const row = document.querySelector(`tr[data-log-id="${logId}"]`);
    if (row) {
        const checkbox = row.querySelector('.read-checkbox');
        const isRead = readStatus.has(logId);
        
        if (isRead) {
            row.classList.remove('unread');
            row.classList.add('read');
            checkbox.classList.remove('unread');
            checkbox.classList.add('read');
            checkbox.textContent = '✓';
        } else {
            row.classList.remove('read');
            row.classList.add('unread');
            checkbox.classList.remove('read');
            checkbox.classList.add('unread');
            checkbox.textContent = '';
        }
    }
    
    checkAlertConditions();
    checkUnreadLogs();
}

// 初始化悬停效果
function initHoverEffect() {
    // 创建全局悬停元素
    const tooltip = document.createElement('div');
    tooltip.className = 'custom-tooltip';
    tooltip.style.position = 'absolute';
    tooltip.style.backgroundColor = '#f0f0f0'; // 烟灰底色
    tooltip.style.color = '#333';
    tooltip.style.padding = '10px 15px';
    tooltip.style.borderRadius = '8px'; // 圆角矩形框
    tooltip.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    tooltip.style.zIndex = '1000';
    tooltip.style.maxWidth = '500px';
    tooltip.style.wordBreak = 'break-word';
    tooltip.style.whiteSpace = 'pre-wrap'; // 保留空白字符和换行
    tooltip.style.display = 'none';
    document.body.appendChild(tooltip);
    
    // 使用事件委托处理悬停事件
    document.addEventListener('mouseenter', (e) => {
        if (e.target && typeof e.target.closest === 'function') {
            const cell = e.target.closest('.log-message-cell');
            if (cell) {
                // 获取完整的消息内容
                const fullMessage = cell.getAttribute('data-full-message');
                if (fullMessage !== null && fullMessage !== undefined) {
                    // 移除默认的 title 行为
                    cell.removeAttribute('title');
                    
                    // 显示悬停框
                    const rect = cell.getBoundingClientRect();
                    tooltip.style.left = `${rect.left}px`;
                    tooltip.style.top = `${rect.bottom + 10}px`;
                    tooltip.textContent = fullMessage || '';
                    tooltip.style.display = 'block';
                }
            }
        }
    });
    
    // 鼠标离开事件
    document.addEventListener('mouseleave', (e) => {
        if (e.target && typeof e.target.closest === 'function') {
            const cell = e.target.closest('.log-message-cell');
            if (cell) {
                tooltip.style.display = 'none';
            }
        }
    });
    
    // 确保鼠标离开页面时隐藏悬停框
    document.addEventListener('mousemove', (e) => {
        if (e.target && typeof e.target.closest === 'function') {
            const cell = e.target.closest('.log-message-cell');
            if (!cell) {
                tooltip.style.display = 'none';
            }
        } else {
            // 如果 e.target 不支持 closest 方法，直接隐藏悬停框
            tooltip.style.display = 'none';
        }
    });
}

// 批量标记已读
function markAllLogsAsRead() {
    const logRows = document.querySelectorAll('#logs-tbody tr[data-log-id]');
    const logIds = Array.from(logRows).map(row => row.getAttribute('data-log-id'));
    
    if (logIds.length === 0) {
        return;
    }
    
    const readStatus = getReadStatusFromStorage();
    logIds.forEach(id => readStatus.add(id));
    saveReadStatusToStorage(readStatus);
    
    // 刷新日志列表
    fetchLogsPage();
}

// 清空已读状态
function clearReadStatus() {
    try {
        localStorage.removeItem('monitor_log_read_status');
        
        // 刷新日志列表
        fetchLogsPage();
    } catch (e) {
        console.error('清空已读状态失败:', e);
    }
}

// 页面加载完成后初始化悬停效果
document.addEventListener('DOMContentLoaded', initHoverEffect);

function refreshLogsPage() {
    fetchLogsPage();
}

// 定时任务详情页面
async function fetchSchedulerPage() {
    try {
        const response = await fetch(`${API_BASE}/scheduler`);
        const data = await response.json();
        updateSchedulerDetailDisplay(data);
    } catch (error) {
        console.error('获取定时任务详情失败:', error);
    }
}

function updateSchedulerDetailDisplay(data) {
    const gridEl = document.getElementById('scheduler-detail-grid');
    const scheduler = data.scheduler || {};
    let jobs = data.jobs || [];
    
    // 更新徽章
    const badge = document.getElementById('scheduler-detail-badge');
    if (scheduler.running) {
        badge.textContent = '运行中';
        badge.className = 'badge healthy';
    } else {
        badge.textContent = '已停止';
        badge.className = 'badge warning';
    }
    
    if (jobs.length === 0) {
        gridEl.innerHTML = '<div class="empty-state">暂无定时任务</div>';
        return;
    }
    
    // 将系统级任务置顶显示
    // 系统级任务：project_files.check_db_health
    jobs.sort((a, b) => {
        const aIsSystem = (a.name || a.id).includes('project_files.check_db_health');
        const bIsSystem = (b.name || b.id).includes('project_files.check_db_health');
        if (aIsSystem && !bIsSystem) return -1;
        if (!aIsSystem && bIsSystem) return 1;
        return 0;
    });
    
    gridEl.innerHTML = jobs.map(job => {
        const lastRunTime = job.last_run_time ? formatDateTime(job.last_run_time) : '从未执行';
        const nextRunTime = job.next_run_time ? formatDateTime(job.next_run_time) : '未计划';
        const maxExecutionTime = job.max_execution_time ? `${job.max_execution_time.toFixed(2)} 秒` : '默认';
        const isSystemTask = (job.name || job.id).includes('project_files.check_db_health');
        
        return `
        <div class="scheduler-detail-item ${isSystemTask ? 'system-task' : ''}">
            <div class="scheduler-detail-header">
                <span class="scheduler-detail-name">${job.name || job.id}</span>
                <span class="scheduler-detail-status">
                    <span class="status-dot healthy"></span>
                    ${isSystemTask ? '系统任务' : '已注册'}
                </span>
            </div>
            <div class="scheduler-detail-info">
                <div class="scheduler-detail-row">
                    <span class="scheduler-detail-label">触发器</span>
                    <span class="scheduler-detail-value">${job.trigger || '未知'}</span>
                </div>
                <div class="scheduler-detail-row">
                    <span class="scheduler-detail-label">上次执行</span>
                    <span class="scheduler-detail-value">${lastRunTime}</span>
                </div>
                <div class="scheduler-detail-row">
                    <span class="scheduler-detail-label">下次执行</span>
                    <span class="scheduler-detail-value">${nextRunTime}</span>
                </div>
                <div class="scheduler-detail-row">
                    <span class="scheduler-detail-label">最大执行时间</span>
                    <span class="scheduler-detail-value">${maxExecutionTime}</span>
                </div>
                ${job.execution_time ? `
                <div class="scheduler-detail-row">
                    <span class="scheduler-detail-label">平均执行时间</span>
                    <span class="scheduler-detail-value">${(job.execution_time * 1000).toFixed(0)} ms</span>
                </div>
                ` : ''}
                ${job.last_error ? `
                <div class="scheduler-detail-row">
                    <span class="scheduler-detail-label">最后错误</span>
                    <span class="scheduler-detail-value" style="color: var(--error-color)">${job.last_error}</span>
                </div>
                ` : ''}
            </div>
        </div>
        `;
    }).join('');
}

function refreshSchedulerPage() {
    fetchSchedulerPage();
}

// 开关状态：是否显示内部请求
let showInternalRequests = false;

// 获取发送请求数据
async function fetchOutboundRequests() {
    try {
        const response = await fetch(`${API_BASE}/outbound-http/all`);
        const requests = await response.json();
        
        // 根据开关状态决定是否过滤本服务的请求
        const baseUrl = 'http://localhost:8000';
        const filteredRequests = showInternalRequests ? requests : requests.filter(request => {
            // 检查URL是否以baseUrl开头
            return !request.url.startsWith(baseUrl);
        });
        
        updateOutboundRequestsTable(filteredRequests);
        
        // 计算过滤后的请求统计信息
        const summary = calculateOutboundRequestsSummary(filteredRequests);
        updateOutboundHttpSummary({ summary });
    } catch (error) {
        console.error('获取发送请求数据失败:', error);
    }
}

// 切换内部请求显示状态
function toggleInternalRequests() {
    const checkbox = document.getElementById('show-internal-requests');
    showInternalRequests = checkbox.checked;
    fetchOutboundRequests();
}

// 计算发送请求统计信息
function calculateOutboundRequestsSummary(requests) {
    if (requests.length === 0) {
        return {
            total_requests: 0,
            error_rate: 0,
            avg_response_time: 0,
            requests_per_minute: 0
        };
    }
    
    const totalRequests = requests.length;
    const errorRequests = requests.filter(req => req.status_code >= 400).length;
    const totalResponseTime = requests.reduce((sum, req) => sum + req.duration, 0);
    
    return {
        total_requests: totalRequests,
        error_rate: (errorRequests / totalRequests) * 100,
        avg_response_time: totalResponseTime / totalRequests,
        requests_per_minute: 0 // 暂时设为0，因为前端无法准确计算每分钟请求数
    };
}

// 更新发送请求表格
function updateOutboundRequestsTable(requests) {
    const tableBody = document.getElementById('outbound-requests-table');
    if (!tableBody) return;
    
    tableBody.innerHTML = requests.map(request => formatOutboundRequestRow(request)).join('');
}

// 格式化发送请求行
function formatOutboundRequestRow(request) {
    const timestamp = new Date(request.timestamp * 1000).toLocaleString('zh-CN');
    const duration = (request.duration * 1000).toFixed(0);
    const statusClass = request.status_code >= 400 ? 'error' : 'success';
    const durationClass = request.duration > 1 ? 'slow' : '';
    
    return `
    <tr>
        <td>${timestamp}</td>
        <td class="method ${request.method.toLowerCase()}">${request.method}</td>
        <td class="url">${request.url}</td>
        <td class="status ${statusClass}">${request.status_code}</td>
        <td class="duration ${durationClass}">${duration}ms</td>
        <td>${request.module || 'unknown'}</td>
        <td class="error-message">${request.error_message || '-'}</td>
        <td>
            <button class="btn btn-sm" onclick="showOutboundRequestDetail(${JSON.stringify(request).replace(/"/g, '&quot;')})")">查看</button>
        </td>
    </tr>
    `;
}

// 显示发送请求详情
function showOutboundRequestDetail(request) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-overlay"></div>
        <div class="modal-content">
            <div class="modal-header">
                <h3>发送请求详情</h3>
                <button class="close-btn" onclick="this.closest('.modal').remove()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="detail-section">
                    <h4>基本信息</h4>
                    <table class="detail-table">
                        <tbody>
                            <tr>
                                <td class="detail-label">时间戳:</td>
                                <td class="detail-value">${new Date(request.timestamp * 1000).toLocaleString('zh-CN')}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">方法:</td>
                                <td class="detail-value">${request.method}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">URL:</td>
                                <td class="detail-value">${request.url}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">状态码:</td>
                                <td class="detail-value ${request.status_code >= 400 ? 'error' : 'success'}">${request.status_code}</td>
                            </tr>
                            <tr>
                                <td class="detail-label">响应时间:</td>
                                <td class="detail-value ${request.duration > 1 ? 'slow' : ''}">${(request.duration * 1000).toFixed(0)}ms</td>
                            </tr>
                            <tr>
                                <td class="detail-label">模块:</td>
                                <td class="detail-value">${request.module || 'unknown'}</td>
                            </tr>
                            ${request.error_message ? `
                            <tr>
                                <td class="detail-label">错误信息:</td>
                                <td class="detail-value error">${request.error_message}</td>
                            </tr>
                            ` : ''}
                        </tbody>
                    </table>
                </div>
                ${request.request_headers ? `
                <div class="detail-section">
                    <h4>请求头</h4>
                    <pre><code class="language-json">${JSON.stringify(request.request_headers, null, 2)}</code></pre>
                </div>
                ` : ''}
                ${request.request_body ? `
                <div class="detail-section">
                    <h4>请求体</h4>
                    <pre><code class="language-json">${typeof request.request_body === 'string' ? (function() {
                        try {
                            return JSON.stringify(JSON.parse(request.request_body), null, 2);
                        } catch (e) {
                            return request.request_body;
                        }
                    })() : JSON.stringify(request.request_body, null, 2)}</code></pre>
                </div>
                ` : ''}
                ${request.response_headers ? `
                <div class="detail-section">
                    <h4>响应头</h4>
                    <pre><code class="language-json">${JSON.stringify(request.response_headers, null, 2)}</code></pre>
                </div>
                ` : ''}
                ${request.response_body ? `
                <div class="detail-section">
                    <h4>响应体</h4>
                    <pre><code class="language-json">${typeof request.response_body === 'string' ? (function() {
                        try {
                            return JSON.stringify(JSON.parse(request.response_body), null, 2);
                        } catch (e) {
                            return request.response_body;
                        }
                    })() : JSON.stringify(request.response_body, null, 2)}</code></pre>
                </div>
                ` : ''}
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    Prism.highlightAll();
}

// 更新发送请求摘要
function updateOutboundHttpSummary(metrics) {
    const summary = metrics.summary || {};
    document.getElementById('outbound-total-requests').textContent = summary.total_requests || 0;
    document.getElementById('outbound-error-rate').textContent = (summary.error_rate || 0).toFixed(2) + '%';
    document.getElementById('outbound-avg-time').textContent = (summary.avg_response_time * 1000).toFixed(0) + 'ms';
    document.getElementById('outbound-rpm').textContent = summary.requests_per_minute || 0;
    
    // 更新发送请求页签的红点角标（仅在异常状态发生变化时显示）
    const outboundRequestsBadge = document.getElementById('outbound-requests-badge');
    if (outboundRequestsBadge) {
        const hasErrors = summary.error_rate > 0;
        actualErrorState['outbound-requests'] = hasErrors;
        const confirmedHasError = badgeConfirmedHasError['outbound-requests'];
        const errorStateChanged = hasErrors !== confirmedHasError;
        outboundRequestsBadge.style.display = errorStateChanged ? 'inline-block' : 'none';
    }
}

// 刷新发送请求数据
function refreshOutboundRequests() {
    fetchOutboundRequests();
}

// 重置发送请求统计
async function resetOutboundStats() {
    try {
        const response = await fetch(`${API_BASE}/outbound-http/reset`, { method: 'POST' });
        const data = await response.json();
        alert(data.message);
        fetchOutboundRequests();
    } catch (error) {
        console.error('重置发送请求统计失败:', error);
        alert('重置失败，请重试');
    }
}

// 获取并更新overview页面的发送请求数据
async function fetchOverviewOutboundRequests() {
    try {
        const response = await fetch(`${API_BASE}/outbound-http/all`);
        const requests = await response.json();
        
        // 过滤内部请求
        const baseUrl = 'http://localhost:8000';
        const filteredRequests = requests.filter(request => {
            return !request.url.startsWith(baseUrl);
        });
        
        // 计算统计信息
        const summary = calculateOutboundRequestsSummary(filteredRequests);
        
        // 更新overview页面的统计
        updateOverviewOutboundSummary(summary);
        
        // 更新overview页面的请求列表（显示最近5条）
        const recentRequests = filteredRequests.slice(0, 5);
        updateOverviewOutboundList(recentRequests);
        
        // 更新状态徽章
        const badge = document.getElementById('outbound-badge');
        if (badge) {
            if (summary.error_rate > 0) {
                badge.className = 'badge error';
                badge.textContent = '异常';
            } else {
                badge.className = 'badge healthy';
                badge.textContent = '正常';
            }
        }
        
        // 更新发送请求页签的红点角标（仅在异常状态发生变化时显示）
        const outboundRequestsBadge = document.getElementById('outbound-requests-badge');
        if (outboundRequestsBadge) {
            const hasErrors = summary.error_rate > 0;
            actualErrorState['outbound-requests'] = hasErrors;
            const confirmedHasError = badgeConfirmedHasError['outbound-requests'];
            const errorStateChanged = hasErrors !== confirmedHasError;
            outboundRequestsBadge.style.display = errorStateChanged ? 'inline-block' : 'none';
        }
    } catch (error) {
        console.error('获取overview页面发送请求数据失败:', error);
    }
}

// 更新overview页面的发送请求统计
function updateOverviewOutboundSummary(summary) {
    const totalEl = document.getElementById('outbound-total');
    const errorRateEl = document.getElementById('outbound-error-rate');
    const avgEl = document.getElementById('outbound-avg');
    
    if (totalEl) {
        totalEl.textContent = summary.total_requests || 0;
    }
    if (errorRateEl) {
        errorRateEl.textContent = (summary.error_rate || 0).toFixed(2) + '%';
        if (summary.error_rate > 0) {
            errorRateEl.classList.add('error');
        } else {
            errorRateEl.classList.remove('error');
        }
    }
    if (avgEl) {
        avgEl.textContent = (summary.avg_response_time * 1000).toFixed(0) + 'ms';
    }
}

// 更新overview页面的发送请求列表
function updateOverviewOutboundList(requests) {
    const listEl = document.getElementById('outbound-list');
    if (!listEl) return;
    
    if (requests.length === 0) {
        listEl.innerHTML = '<div class="no-data">暂无发送请求</div>';
        return;
    }
    
    listEl.innerHTML = requests.map(request => {
        const timestamp = new Date(request.timestamp * 1000).toLocaleString('zh-CN');
        const duration = (request.duration * 1000).toFixed(0);
        const statusClass = request.status_code >= 400 ? 'error' : 'success';
        
        return `
            <div class="outbound-item">
                <div class="outbound-header">
                    <span class="method ${request.method.toLowerCase()}">${request.method}</span>
                    <span class="timestamp">${timestamp}</span>
                </div>
                <div class="outbound-url">${request.url}</div>
                <div class="outbound-footer">
                    <span class="status ${statusClass}">${request.status_code}</span>
                    <span class="duration">${duration}ms</span>
                </div>
            </div>
        `;
    }).join('');
}
