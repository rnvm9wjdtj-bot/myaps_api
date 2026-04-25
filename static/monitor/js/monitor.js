/**
 * MyAPS 监控面板 JavaScript
 */

const API_BASE = '/monitor/api';
let resourceChart = null;
let refreshInterval = null;
let originalTitle = document.title;
let titleAlertInterval = null;

// 存储实际错误状态
let actualErrorState = {};
// 存储已确认的错误状态（用于比较状态变化）
let badgeConfirmedHasError = {};
// WebSocket 连接
let ws = null;
let wsReconnectInterval = null;
let wsReconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 3000;

// 超时机制
let lastActivityTime = Date.now();
let inactivityTimeout = null;
const INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000; // 当连续不活动 30分钟时，触发超时
let isInactive = false;

// 数据缓存机制
const CACHE_DURATION = {
    environment: 60 * 60 * 1000, // 环境信息缓存1小时
    health: 30 * 1000, // 健康状态缓存30秒
    resource: 5 * 1000, // 资源信息缓存5秒
    time: 60 * 1000 // 时间格式化缓存1分钟
};

const CACHE_LIMIT = {
    data: 100, // 数据缓存最大条目数
    time: 500, // 时间格式化缓存最大条目数
    dom: 200 // DOM元素缓存最大条目数
};

const dataCache = {};

// DOM元素缓存
const domCache = {};

// 时间格式化缓存
const timeCache = {};

// 页面加载时设置默认日期
window.addEventListener('DOMContentLoaded', function() {
    const today = new Date().toISOString().split('T')[0];
    
    // 设置接收请求日期选择器的默认值
    const datePicker = document.getElementById('api-date-picker');
    if (datePicker) {
        datePicker.value = today;
    }
    
    // 设置发送请求日期选择器的默认值
    const outboundDatePicker = document.getElementById('outbound-date-picker');
    if (outboundDatePicker) {
        outboundDatePicker.value = today;
    }
});

// 获取DOM元素，优先从缓存中获取
function getElement(id) {
    if (!domCache[id]) {
        // 检查DOM缓存大小
        if (Object.keys(domCache).length >= CACHE_LIMIT.dom) {
            // 移除最早的缓存项
            const oldestKey = Object.keys(domCache)[0];
            delete domCache[oldestKey];
        }
        domCache[id] = document.getElementById(id);
    }
    return domCache[id];
}

// 从localStorage加载已确认的错误状态
function loadBadgeConfirmedHasError() {
    try {
        const stored = localStorage.getItem('badgeConfirmedHasError');
        if (stored) {
            badgeConfirmedHasError = JSON.parse(stored);
        }
    } catch (error) {
        console.error('加载已确认错误状态失败:', error);
        badgeConfirmedHasError = {};
    }
}

// 检查缓存是否有效
function isCacheValid(key) {
    const cacheItem = dataCache[key];
    if (!cacheItem) return false;
    const now = Date.now();
    return now - cacheItem.timestamp < CACHE_DURATION[key];
}

// 获取缓存数据
function getCachedData(key) {
    if (isCacheValid(key)) {
        return dataCache[key].data;
    }
    return null;
}

// 更新缓存数据
function updateCache(key, data) {
    // 检查数据缓存大小
    if (Object.keys(dataCache).length >= CACHE_LIMIT.data) {
        // 移除最早的缓存项
        let oldestKey = null;
        let oldestTimestamp = Infinity;
        Object.entries(dataCache).forEach(([k, v]) => {
            if (v.timestamp < oldestTimestamp) {
                oldestTimestamp = v.timestamp;
                oldestKey = k;
            }
        });
        if (oldestKey) {
            delete dataCache[oldestKey];
        }
    }
    dataCache[key] = {
        data: data,
        timestamp: Date.now()
    };
}

// 清理过期缓存
function cleanupCache() {
    const now = Date.now();
    
    // 清理数据缓存
    Object.entries(dataCache).forEach(([key, item]) => {
        if (now - item.timestamp >= CACHE_DURATION[key] || !CACHE_DURATION[key]) {
            delete dataCache[key];
        }
    });
    
    // 清理时间缓存
    if (Object.keys(timeCache).length >= CACHE_LIMIT.time) {
        // 保留最近使用的缓存项
        const sortedKeys = Object.keys(timeCache).sort((a, b) => {
            return timeCache[b].timestamp - timeCache[a].timestamp;
        });
        const keysToRemove = sortedKeys.slice(CACHE_LIMIT.time);
        keysToRemove.forEach(key => {
            delete timeCache[key];
        });
    }
}

// 定期清理缓存
setInterval(cleanupCache, 5 * 60 * 1000); // 每5分钟清理一次

// 节流函数
function throttle(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 保存已确认的错误状态到localStorage
function saveBadgeConfirmedHasError() {
    try {
        localStorage.setItem('badgeConfirmedHasError', JSON.stringify(badgeConfirmedHasError));
    } catch (error) {
        console.error('保存已确认错误状态失败:', error);
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
    // 加载已确认的错误状态
    loadBadgeConfirmedHasError();
    initResourceChart();
    initRedisCharts();
    fetchEnvironment();
    // 无论当前在哪个页面，都获取一次日志数据来检查未读状态
    await fetchLogsPage();
    await refreshAll();
    startAutoRefresh();
    initWebSocket();
    startInactivityTimer();
    
    // 设置默认日期为今天
    const today = new Date().toISOString().split('T')[0];
    const datePicker = document.getElementById('api-date-picker');
    if (datePicker) {
        datePicker.value = today;
    }
    
    // 监听用户活动
    window.addEventListener('mousemove', resetInactivityTimer);
    window.addEventListener('keydown', resetInactivityTimer);
    window.addEventListener('scroll', resetInactivityTimer);
    window.addEventListener('click', resetInactivityTimer);
});

// 启动不活动计时器
function startInactivityTimer() {
    if (inactivityTimeout) {
        clearTimeout(inactivityTimeout);
    }
    inactivityTimeout = setTimeout(handleInactivityTimeout, INACTIVITY_TIMEOUT_MS);
}

// 重置不活动计时器
function resetInactivityTimer() {
    lastActivityTime = Date.now();
    if (isInactive) {
        // 如果之前处于不活动状态，更新状态但不自动重连
        isInactive = false;
        console.log('用户活动，更新监控状态但不自动重连');
    }
    startInactivityTimer();
}

// 处理不活动超时
function handleInactivityTimeout() {
    isInactive = true;
    console.log('用户长时间不活动，断开 WebSocket 连接并停止数据刷新');
    
    // 断开 WebSocket 连接
    closeWebSocket();
    
    // 停止自动刷新
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
    
    // 显示提示信息
    const statusIndicator = document.getElementById('status-indicator');
    if (statusIndicator) {
        statusIndicator.textContent = '● 监控已暂停（长时间未活动）';
        statusIndicator.className = 'status warning';
    }
    
    // 显示超时提示模态框
    showInactivityModal();
}

// 显示超时提示模态框
function showInactivityModal() {
    const modal = document.getElementById('inactivity-modal');
    if (modal) {
        modal.style.display = 'block';
    }
}

// 隐藏超时提示模态框
function hideInactivityModal() {
    const modal = document.getElementById('inactivity-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// 恢复监控
function resumeMonitoring() {
    console.log('用户手动恢复监控');
    
    // 隐藏模态框
    hideInactivityModal();
    
    // 重置不活动状态
    isInactive = false;
    
    // 重新建立 WebSocket 连接
    initWebSocket();
    
    // 重新启动自动刷新
    startAutoRefresh();
    
    // 立即刷新一次数据
    refreshAll();
    
    // 重置不活动计时器
    resetInactivityTimer();
}

// WebSocket 心跳相关变量
let wsHeartbeatInterval = null;
const WS_HEARTBEAT_INTERVAL = 30000; // 心跳间隔，30秒
const WS_RECONNECT_BASE_DELAY = 1000; // 基础重连延迟
const WS_MAX_RECONNECT_DELAY = 30000; // 最大重连延迟

// 初始化 WebSocket 连接
function initWebSocket() {
    // 如果用户不活动，不建立 WebSocket 连接
    if (isInactive) {
        console.log('用户不活动，跳过 WebSocket 连接初始化');
        return;
    }
    
    // 构建 WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/monitor/ws`;
    
    // 关闭现有连接
    if (ws) {
        try {
            ws.close(1000, '重新连接');
        } catch (error) {
            console.error('关闭 WebSocket 连接失败:', error);
        }
        ws = null;
    }
    
    // 清除心跳定时器
    if (wsHeartbeatInterval) {
        clearInterval(wsHeartbeatInterval);
        wsHeartbeatInterval = null;
    }
    
    // 创建新连接
    try {
        ws = new WebSocket(wsUrl);
        
        // 连接建立
        ws.onopen = function() {
            console.log('WebSocket 连接已建立');
            wsReconnectAttempts = 0;
            if (wsReconnectInterval) {
                clearInterval(wsReconnectInterval);
                wsReconnectInterval = null;
            }
            
            // 启动心跳
            startWebSocketHeartbeat();
        };
        
        // 接收消息
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'monitor_data') {
                    handleWebSocketData(data.data);
                } else if (data.type === 'heartbeat_response') {
                    // 心跳响应处理
                }
            } catch (error) {
                console.error('解析 WebSocket 消息失败:', error);
            }
        };
        
        // 连接关闭
        ws.onclose = function(event) {
            console.log(`WebSocket 连接已关闭: ${event.code} - ${event.reason}`);
            // 清除心跳定时器
            if (wsHeartbeatInterval) {
                clearInterval(wsHeartbeatInterval);
                wsHeartbeatInterval = null;
            }
            // 只有在非手动关闭的情况下才尝试重连
            if (event.code !== 1000) {
                attemptReconnect();
            }
        };
        
        // 连接错误
        ws.onerror = function(error) {
            console.error('WebSocket 错误:', error);
        };
    } catch (error) {
        console.error('创建 WebSocket 连接失败:', error);
        attemptReconnect();
    }
}

// 启动 WebSocket 心跳
function startWebSocketHeartbeat() {
    // 清除现有心跳定时器
    if (wsHeartbeatInterval) {
        clearInterval(wsHeartbeatInterval);
        wsHeartbeatInterval = null;
    }
    
    // 设置新的心跳定时器
    wsHeartbeatInterval = setInterval(function() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            try {
                ws.send(JSON.stringify({ type: 'heartbeat', timestamp: Date.now() }));
            } catch (error) {
                console.error('发送 WebSocket 心跳失败:', error);
                // 发送失败时尝试重连
                attemptReconnect();
            }
        } else if (ws && ws.readyState === WebSocket.CLOSED) {
            // 连接已关闭，尝试重连
            attemptReconnect();
        }
    }, WS_HEARTBEAT_INTERVAL);
}

// 尝试重新连接
function attemptReconnect() {
    if (isInactive) {
        console.log('用户不活动，跳过 WebSocket 重连');
        return;
    }
    
    if (wsReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error('WebSocket 重连失败，已达到最大尝试次数');
        if (wsReconnectInterval) {
            clearInterval(wsReconnectInterval);
            wsReconnectInterval = null;
        }
        return;
    }
    
    wsReconnectAttempts++;
    console.log(`尝试重新连接 WebSocket (${wsReconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
    
    if (wsReconnectInterval) {
        clearInterval(wsReconnectInterval);
    }
    
    const delay = Math.min(
        RECONNECT_DELAY * Math.pow(2, wsReconnectAttempts - 1),
        30000
    );
    
    wsReconnectInterval = setTimeout(() => {
        initWebSocket();
    }, delay);
}

// 处理 WebSocket 数据
function handleWebSocketData(data) {
    // 如果用户不活动，不处理 WebSocket 数据
    if (isInactive) {
        console.log('用户不活动，跳过 WebSocket 数据处理');
        return;
    }
    
    // 检查系统状态是否为错误
    const statusIndicator = getElement('status-indicator');
    const isSystemError = statusIndicator && statusIndicator.classList.contains('error');
    
    // 如果系统状态正常，才处理数据并更新最后更新时间
    if (!isSystemError) {
        // 更新资源指标
        if (data.resource) {
            updateResourceDisplay(data.resource);
        }
        
        // 更新数据库指标
        if (data.database) {
            updateDatabaseDisplay(data.database);
        }
        
        // 更新调度器指标
        if (data.scheduler) {
            updateSchedulerDisplay(data.scheduler);
        }
        
        // 更新 HTTP 指标
        if (data.http) {
            updateHTTPDisplay(data.http);
        }
        
        // 更新对外 HTTP 指标
        if (data.outbound_http) {
            // 这里可以添加对外 HTTP 指标的更新逻辑
        }
        
        // 更新告警
        if (data.alerts) {
            updateAlertsDisplay(data.alerts);
        }
        
        // 更新日志数据
        if (data.logs) {
            updateLogsPageDisplay(data.logs);
        }
        
        // 更新 API 请求数据
        if (data.api_requests) {
            updateAPIRequestsDisplay(data.api_requests);
        }
        
        // 更新发送请求数据
        if (data.outbound_requests) {
            updateOutboundRequestsDisplay(data.outbound_requests);
        }
        
        // 更新事件辅助模块数据
        if (data.event_helpers) {
            updateEventHelpersDisplay(data.event_helpers);
        }
        
        // 更新 Redis 指标
        if (data.redis) {
            updateRedisDisplay(data.redis);
        }
        
        // 更新最后更新时间
        updateLastUpdateTime();
    }
    
    // 检查告警条件
    checkAlertConditions();
}

// 更新发送请求显示
function updateOutboundRequestsDisplay(data) {
    let requests = data.recent_requests || [];
    
    // 计算24小时前的时间戳
    const twentyFourHoursAgo = Date.now() / 1000 - (24 * 60 * 60);
    
    // 根据开关状态决定是否过滤本服务的请求，同时过滤最近24小时的请求
    const filteredRequests = showInternalRequests ? 
        requests.filter(request => request.timestamp >= twentyFourHoursAgo) : 
        requests.filter(request => {
            // 检查URL是否包含localhost或127.0.0.1，同时检查时间
            return !request.url.includes('localhost') && !request.url.includes('127.0.0.1') && request.timestamp >= twentyFourHoursAgo;
        });
    
    updateOutboundRequestsTable(filteredRequests);
    
    // 如果需要标记为已读，则将所有400+请求标记为已读
    if (shouldMarkOutboundRequestsAsRead) {
        const readStatus = getOutboundRequestReadStatus();
        filteredRequests.forEach(req => {
            if (req.status_code >= 400) {
                const requestId = generateOutboundRequestId(req.timestamp, req.method, req.url, req.status_code);
                readStatus.add(requestId);
            }
        });
        saveOutboundRequestReadStatus(readStatus);
        shouldMarkOutboundRequestsAsRead = false;
    }
    
    // 获取已读状态
    const readStatus = getOutboundRequestReadStatus();
    
    // 检查是否有未读的400+请求
    const hasUnreadErrors = filteredRequests.some(req => {
        if (req.status_code >= 400) {
            const requestId = generateOutboundRequestId(req.timestamp, req.method, req.url, req.status_code);
            return !readStatus.has(requestId);
        }
        return false;
    });
    
    // 更新发送请求页签的红点角标
    const outboundRequestsBadge = document.getElementById('outbound-requests-badge');
    if (outboundRequestsBadge) {
        outboundRequestsBadge.style.display = hasUnreadErrors ? 'inline-block' : 'none';
    }
}

// 关闭 WebSocket 连接
function closeWebSocket() {
    if (ws) {
        ws.close();
        ws = null;
    }
    if (wsReconnectInterval) {
        clearInterval(wsReconnectInterval);
        wsReconnectInterval = null;
    }
}

// 获取环境变量
async function fetchEnvironment() {
    // 检查缓存
    const cachedData = getCachedData('environment');
    if (cachedData) {
        updateTitleWithEnvironment(cachedData);
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/env`);
        const data = await response.json();
        updateCache('environment', data);
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
    // 使用节流函数限制refreshAll的执行频率
    const throttledRefreshAll = throttle(refreshAll, 5000); // 最多每5秒执行一次
    refreshInterval = setInterval(throttledRefreshAll, 10000);
}

// 获取 Redis 指标
async function fetchRedis() {
    try {
        const response = await fetch(`${API_BASE}/overview`);
        const data = await response.json();
        if (data.redis) {
            updateRedisDisplay(data.redis);
        }
    } catch (error) {
        console.error('获取 Redis 指标失败:', error);
    }
}

// 刷新所有数据
async function refreshAll() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过数据刷新');
        return;
    }
    
    try {
        // 先检查健康状态
        await fetchHealth();
        
        // 检查系统状态是否为错误（只有连接失败才算是系统错误）
        const statusIndicator = getElement('status-indicator');
        const statusText = statusIndicator ? statusIndicator.textContent : '';
        const isSystemError = statusIndicator && statusIndicator.classList.contains('error') && statusText.includes('连接失败');
        
        // 如果系统状态不是连接失败，继续获取其他数据
        if (!isSystemError) {
            // 基础数据，无论哪个页面都需要刷新
            await Promise.all([
                fetchResource(),
                fetchDatabase(),
                fetchScheduler(),
                fetchHTTP(),
                fetchAlerts(),
                fetchOverviewOutboundRequests(),
                fetchRedis(),
                // 无论在哪个页面都刷新日志列表、API 请求记录和发送请求记录
                fetchLogsPage(),
                fetchAPIRequests(),
                fetchOutboundRequests()
            ]);
            
            // 只刷新当前页面的特定数据
            switch (currentPage) {
                case 'database':
                    await Promise.all([
                        fetchDatabaseDetail(),
                        fetchEventStats()
                    ]);
                    break;
                case 'scheduler':
                    await fetchSchedulerPage();
                    break;
                case 'event-helpers':
                    await Promise.all([
                        fetchEventStats(),
                        fetchEventHelpers(),
                        fetchDeadLetterStats()
                    ]);
                    break;
            }
            
            updateLastUpdateTime();
        }
        
        checkAlertConditions();
    } catch (error) {
        console.error('刷新数据失败:', error);
    }
}

// 检查告警条件并更新title
function checkAlertConditions() {
    const hasDbError = checkDatabaseError();
    const hasDatabaseOffline = checkDatabaseOffline();
    const hasUnreadLogs = checkUnreadLogs();
    const hasSystemError = checkSystemStatus();
    
    if (hasDbError || hasUnreadLogs || hasSystemError) {
        startTitleAlert(hasSystemError, hasDatabaseOffline);
    } else {
        stopTitleAlert();
    }
}

// 检查系统状态（后端失连）
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

// 检查数据库离线
function checkDatabaseOffline() {
    // 检查概览页面的数据库状态
    const dbBadge = document.getElementById('db-badge');
    if (dbBadge && dbBadge.classList.contains('error')) {
        return true;
    }
    
    // 检查数据库详情页面的状态
    const dbDetailBadge = document.getElementById('db-detail-badge');
    if (dbDetailBadge && dbDetailBadge.classList.contains('error')) {
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
function startTitleAlert(hasSystemError, hasDatabaseOffline) {
    if (titleAlertInterval) {
        clearInterval(titleAlertInterval);
    }
    
    let blinkState = 0;
    let blinkPattern;
    
    if (hasSystemError || hasDatabaseOffline) {
        // 后端失连或数据库离线时的闪烁模式：红色禁止图标 + 完整文字
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
                const hasDatabaseOffline = checkDatabaseOffline();
                const hasUnreadLogs = checkUnreadLogs();
                const hasSystemError = checkSystemStatus();
                if (hasDbError || hasUnreadLogs || hasSystemError) {
                    startTitleAlert(hasSystemError, hasDatabaseOffline);
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
    const indicator = getElement('status-indicator');
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
    const indicator = getElement('status-indicator');
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
        const resourceBadge = getElement('resource-badge');
        resourceBadge.textContent = '错误';
        resourceBadge.className = 'badge error';
        return;
    }

    // CPU
    const cpuValue = data.cpu?.system || 0;
    getElement('cpu-value').textContent = `${cpuValue}%`;
    const cpuBar = getElement('cpu-bar');
    cpuBar.style.width = `${Math.min(cpuValue, 100)}%`;
    cpuBar.className = `progress-fill ${getProgressClass(cpuValue)}`;

    // 内存
    const memValue = data.memory?.rss || 0;
    const memPercent = data.memory?.percent || 0;
    getElement('memory-percent').textContent = `${memPercent}%`;
    getElement('memory-usage').textContent = `${memValue} M`;
    const memBar = getElement('memory-bar');
    memBar.style.width = `${Math.min(memPercent, 100)}%`;
    memBar.className = `progress-fill ${getProgressClass(memPercent)}`;

    // 线程数
    getElement('threads-value').textContent = data.threads || '--';

    // 运行时间
    getElement('uptime-value').textContent = formatUptime(data.uptime || 0);

    // 更新图表
    updateResourceChart(cpuValue, memPercent);

    // 更新徽章
    const badge = getElement('resource-badge');
    badge.textContent = '运行中';
    badge.className = 'badge healthy';
}

// 获取进度条颜色类
function getProgressClass(value) {
    if (value >= 80) return 'error';
    if (value >= 60) return 'warning';
    return '';
}

// 存储上一次的告警列表
let previousAlerts = [];

// 格式化运行时间
function formatUptime(seconds) {
    // 检查缓存
    const cacheKey = `uptime_${seconds}`;
    if (timeCache[cacheKey] && Date.now() - timeCache[cacheKey].timestamp < CACHE_DURATION.time) {
        return timeCache[cacheKey].value;
    }
    
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    let result;
    if (days > 0) {
        result = `${days}d ${hours}h`;
    } else if (hours > 0) {
        result = `${hours}h ${minutes}m`;
    } else {
        result = `${minutes}m`;
    }
    
    // 更新缓存
    timeCache[cacheKey] = {
        value: result,
        timestamp: Date.now()
    };
    
    return result;
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
    const mainDb = data.main_db;

    // 更新汇总
    getElement('db-total').textContent = summary.total || 0;
    getElement('db-healthy').textContent = summary.healthy || 0;
    getElement('db-unhealthy').textContent = summary.unhealthy || 0;

    // 更新徽章
    const badge = getElement('db-badge');
    if (summary.unhealthy === 0) {
        badge.textContent = '正常';
        badge.className = 'badge healthy';
    } else {
        badge.textContent = '异常';
        badge.className = 'badge warning';
    }
    
    // 更新数据库页签的红点角标
    const databaseBadge = getElement('database-badge');
    if (databaseBadge) {
        databaseBadge.style.display = summary.unhealthy > 0 ? 'inline-block' : 'none';
    }

    // 更新连接列表
    const listEl = getElement('db-list');
    const dbConnections = connections.connections || {};

    if (Object.keys(dbConnections).length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无数据库连接</div>';
        checkAlertConditions();
        return;
    }

    // 使用文档片段进行批量DOM操作
    const fragment = document.createDocumentFragment();
    Object.entries(dbConnections).forEach(([name, status]) => {
        const dbItem = document.createElement('div');
        dbItem.className = 'db-item';
        dbItem.innerHTML = `
            <span class="db-name">${name === mainDb ? 'Ⓜ️ ' + name : name}</span>
            <span class="db-status">
                <span class="status-dot ${status.healthy ? 'healthy' : 'error'}"></span>
                ${status.healthy ? '正常' : (status.error || '异常')}
            </span>
        `;
        fragment.appendChild(dbItem);
    });
    
    // 清空并添加新内容
    listEl.innerHTML = '';
    listEl.appendChild(fragment);
    
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
    const statusEl = getElement('scheduler-status');
    const badge = getElement('scheduler-badge');

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
    getElement('job-count').textContent = jobs.length;

    // 更新任务列表（如果元素存在）
    const listEl = getElement('job-list');
    if (listEl) {
        if (jobs.length === 0) {
            listEl.innerHTML = '<div class="empty-state">暂无定时任务</div>';
            return;
        }

        // 使用文档片段进行批量DOM操作
        const fragment = document.createDocumentFragment();
        jobs.forEach(job => {
            const jobItem = document.createElement('div');
            jobItem.className = 'job-item';
            jobItem.innerHTML = `
                <div class="job-info">
                    <span class="job-name">${job.name || job.id}</span>
                    <span class="job-trigger">${job.trigger}</span>
                </div>
                <span class="job-next">${job.next_run_time ? formatDateTime(job.next_run_time) : '未计划'}</span>
            `;
            fragment.appendChild(jobItem);
        });
        
        // 清空并添加新内容
        listEl.innerHTML = '';
        listEl.appendChild(fragment);
    }
}

// 格式化日期时间
function formatDateTime(dateValue) {
    if (!dateValue) return '从未执行';
    
    // 检查缓存
    const cacheKey = `datetime_${dateValue}`;
    if (timeCache[cacheKey] && Date.now() - timeCache[cacheKey].timestamp < CACHE_DURATION.time) {
        return timeCache[cacheKey].value;
    }
    
    let date;
    if (typeof dateValue === 'number') {
        // 处理时间戳（秒）
        date = new Date(dateValue * 1000);
    } else if (typeof dateValue === 'string') {
        // 处理ISO字符串
        date = new Date(dateValue);
    } else {
        // 处理其他格式
        date = new Date(dateValue);
    }
    
    if (isNaN(date.getTime())) {
        return '从未执行';
    }
    
    const result = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    
    // 更新缓存
    timeCache[cacheKey] = {
        value: result,
        timestamp: Date.now()
    };
    
    return result;
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
    const recentRequests = data.recent_requests || [];
    
    // 计算24小时前的时间戳
    const twentyFourHoursAgo = Date.now() / 1000 - (24 * 60 * 60);
    
    // 过滤最近24小时的请求
    const filteredRequests = recentRequests.filter(request => request.timestamp >= twentyFourHoursAgo);
    
    // 重新计算24小时内的汇总数据
    const totalRequests = filteredRequests.length;
    const errorRequests = filteredRequests.filter(req => req.status_code >= 400).length;
    const totalResponseTime = filteredRequests.reduce((sum, req) => sum + req.duration, 0);
    const errorRate = totalRequests > 0 ? (errorRequests / totalRequests) * 100 : 0;
    const avgResponseTime = totalRequests > 0 ? totalResponseTime / totalRequests : 0;
    
    const summary = {
        total_requests: totalRequests,
        error_rate: errorRate,
        avg_response_time: avgResponseTime,
        requests_per_minute: 0
    };

    // 更新汇总数据
    getElement('http-total').textContent = summary.total_requests || 0;
    getElement('http-error-rate').textContent = (summary.error_rate || 0).toFixed(2) + '%';
    getElement('http-avg-time').textContent = ((summary.avg_response_time || 0) * 1000).toFixed(0) + 'ms';
    getElement('http-rpm').textContent = summary.requests_per_minute || 0;

    // 更新徽章
    const badge = getElement('http-badge');
    const errorRateValue = summary.error_rate || 0;
    if (errorRateValue < 1) {
        badge.textContent = '正常';
        badge.className = 'badge healthy';
    } else if (errorRateValue < 5) {
        badge.textContent = '警告';
        badge.className = 'badge warning';
    } else {
        badge.textContent = '异常';
        badge.className = 'badge error';
    }
    
    // 更新接收请求页签的红点角标（仅在异常状态发生变化时显示）
    const apiRequestsBadge = getElement('api-requests-badge');
    if (apiRequestsBadge) {
        const hasErrors = summary.error_rate > 0;
        actualErrorState['api-requests'] = hasErrors;
        const confirmedHasError = badgeConfirmedHasError['api-requests'];
        const errorStateChanged = hasErrors !== confirmedHasError;
        apiRequestsBadge.style.display = errorStateChanged ? 'inline-block' : 'none';
        // 更新已确认的错误状态，确保下次比较正确
        badgeConfirmedHasError['api-requests'] = hasErrors;
        // 保存已确认的错误状态到localStorage
        saveBadgeConfirmedHasError();
    }

    // 更新状态码分布（如果元素存在）
    const statusCodesEl = getElement('http-status-codes');
    if (statusCodesEl) {
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
    }

    // 更新路径统计（如果元素存在）
    const pathsEl = getElement('http-paths');
    if (pathsEl) {
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
}

// 更新告警显示
function updateAlertsDisplay(alerts) {
    const listEl = getElement('alert-list');

    if (alerts.length === 0) {
        listEl.innerHTML = '<div class="empty-state">暂无告警</div>';
        previousAlerts = [];
        return;
    }

    // 生成告警类型标识
    const getAlertType = (alert) => {
        return `${alert.source}_${alert.message.split(':')[0]}`;
    };

    // 生成告警HTML
    const alertElements = alerts.map(alert => {
        const alertType = getAlertType(alert);
        // 检查是否是更新的告警
        const isUpdated = previousAlerts.some(prevAlert => {
            return getAlertType(prevAlert) === alertType && prevAlert.timestamp !== alert.timestamp;
        });
        const updatedClass = isUpdated ? 'alert-updated' : '';
        
        return `
            <div class="alert-item ${alert.level} ${updatedClass}">
                <span class="alert-message">${alert.message}</span>
                <span class="alert-time">${formatDateTime(alert.timestamp, 'date')}</span>
            </div>
        `;
    }).join('');

    listEl.innerHTML = alertElements;

    // 为更新的告警添加闪烁效果
    const updatedAlerts = listEl.querySelectorAll('.alert-updated');
    updatedAlerts.forEach(alertEl => {
        // 添加闪烁动画类
        alertEl.classList.add('alert-flashing');
        // 10秒后移除闪烁效果
        setTimeout(() => {
            alertEl.classList.remove('alert-flashing');
        }, 10000);
    });

    // 更新上一次的告警列表
    previousAlerts = [...alerts];
}

// 统一的日期时间格式化函数
function formatDateTime(timestamp, format = 'relative') {
    // 检查缓存
    const cacheKey = `datetime_${timestamp}_${format}`;
    if (timeCache[cacheKey] && Date.now() - timeCache[cacheKey].timestamp < CACHE_DURATION.time) {
        return timeCache[cacheKey].value;
    }
    
    const now = new Date();
    let date;
    let timestampSec;
    
    if (typeof timestamp === 'string') {
        // 处理ISO字符串格式
        date = new Date(timestamp);
        timestampSec = date.getTime() / 1000;
    } else {
        // 处理数字时间戳（秒）
        date = new Date(timestamp * 1000);
        timestampSec = timestamp;
    }
    
    const diff = now.getTime() / 1000 - timestampSec;
    
    let result;
    
    switch (format) {
        case 'relative':
            // 相对时间格式：刚刚、X分钟前、X小时前、X天前
            if (diff < 60) {
                result = '刚刚';
            } else if (diff < 3600) {
                result = Math.floor(diff / 60) + '分钟前';
            } else if (diff < 86400) {
                result = Math.floor(diff / 3600) + '小时前';
            } else {
                result = Math.floor(diff / 86400) + '天前';
            }
            break;
            
        case 'date':
            // 日期格式：今天 HH:MM、昨天 HH:MM、前天 HH:MM、MM-DD
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            const dayBeforeYesterday = new Date(today);
            dayBeforeYesterday.setDate(dayBeforeYesterday.getDate() - 2);
            const logDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            
            let dayLabel = '';
            if (logDate.getTime() === today.getTime()) {
                dayLabel = '今天';
            } else if (logDate.getTime() === yesterday.getTime()) {
                dayLabel = '昨天';
            } else if (logDate.getTime() === dayBeforeYesterday.getTime()) {
                dayLabel = '前天';
            } else {
                const month = (date.getMonth() + 1).toString().padStart(2, '0');
                const day = date.getDate().toString().padStart(2, '0');
                dayLabel = `${month}-${day}`;
            }
            
            const hours = date.getHours().toString().padStart(2, '0');
            const minutes = date.getMinutes().toString().padStart(2, '0');
            result = `${dayLabel} ${hours}:${minutes}`;
            break;
            
        case 'datetime':
            // 完整日期时间格式：今天 HH:MM:SS、昨天 HH:MM:SS、前天 HH:MM:SS、MM-DD HH:MM:SS
            const todayFull = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const yesterdayFull = new Date(todayFull);
            yesterdayFull.setDate(yesterdayFull.getDate() - 1);
            const dayBeforeYesterdayFull = new Date(todayFull);
            dayBeforeYesterdayFull.setDate(dayBeforeYesterdayFull.getDate() - 2);
            const logDateFull = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            
            let dayLabelFull = '';
            if (logDateFull.getTime() === todayFull.getTime()) {
                dayLabelFull = '今天';
            } else if (logDateFull.getTime() === yesterdayFull.getTime()) {
                dayLabelFull = '昨天';
            } else if (logDateFull.getTime() === dayBeforeYesterdayFull.getTime()) {
                dayLabelFull = '前天';
            } else {
                const month = (date.getMonth() + 1).toString().padStart(2, '0');
                const day = date.getDate().toString().padStart(2, '0');
                dayLabelFull = `${month}-${day}`;
            }
            
            const hoursFull = date.getHours().toString().padStart(2, '0');
            const minutesFull = date.getMinutes().toString().padStart(2, '0');
            const secondsFull = date.getSeconds().toString().padStart(2, '0');
            result = `${dayLabelFull} ${hoursFull}:${minutesFull}:${secondsFull}`;
            break;
            
        default:
            // 默认格式：YYYY-MM-DD HH:MM
            const year = date.getFullYear();
            const month = (date.getMonth() + 1).toString().padStart(2, '0');
            const day = date.getDate().toString().padStart(2, '0');
            const hoursDefault = date.getHours().toString().padStart(2, '0');
            const minutesDefault = date.getMinutes().toString().padStart(2, '0');
            result = `${year}-${month}-${day} ${hoursDefault}:${minutesDefault}`;
    }
    
    // 更新缓存
    timeCache[cacheKey] = {
        value: result,
        timestamp: Date.now()
    };
    
    return result;
}

// 获取状态码描述
function getStatusDescription(statusCode) {
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
}

// 清空告警
async function clearAlerts() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过告警清空');
        return;
    }
    
    try {
        await fetch(`${API_BASE}/alerts/clear`, { method: 'POST' });
        fetchAlerts();
    } catch (error) {
        console.error('清空告警失败:', error);
    }
}

// Redis 图表实例
let redisConnectionsChart = null;
let redisBufferChart = null;

// 初始化 Redis 图表
function initRedisCharts() {
    // 初始化连接池使用情况图表
    const connectionsCtx = document.getElementById('redis-connections-chart');
    if (connectionsCtx) {
        redisConnectionsChart = new Chart(connectionsCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: '使用连接数',
                    data: [],
                    borderColor: '#1890ff',
                    backgroundColor: 'rgba(24, 144, 255, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    }
                }
            }
        });
    }
    
    // 初始化缓冲大小变化图表
    const bufferCtx = document.getElementById('redis-buffer-chart');
    if (bufferCtx) {
        redisBufferChart = new Chart(bufferCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: '缓冲大小 (MB)',
                    data: [],
                    borderColor: '#52c41a',
                    backgroundColor: 'rgba(82, 196, 26, 0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    }
                }
            }
        });
    }
}

// 更新 Redis 监控显示
function updateRedisDisplay(data) {
    // 更新状态指示器
    const statusIndicator = document.getElementById('redis-status');
    const redisBadge = document.getElementById('redis-badge');
    
    if (data.healthy) {
        statusIndicator.textContent = '健康';
        statusIndicator.className = 'status healthy';
        redisBadge.textContent = '正常';
        redisBadge.className = 'badge healthy';
    } else {
        statusIndicator.textContent = '异常';
        statusIndicator.className = 'status error';
        redisBadge.textContent = '异常';
        redisBadge.className = 'badge error';
    }
    
    // 更新主机信息
    document.getElementById('redis-host').textContent = data.host || '-';
    document.getElementById('redis-port').textContent = data.port || '-';
    document.getElementById('redis-db').textContent = data.db || '-';
    
    // 更新连接池信息
    document.getElementById('redis-connections-used').textContent = data.connections_used || 0;
    document.getElementById('redis-connections-max').textContent = data.connections_max || 0;
    document.getElementById('redis-connection-usage').textContent = (data.connection_usage || 0).toFixed(2) + '%';
    
    // 更新缓冲信息
    document.getElementById('redis-buffer-size').textContent = formatBytes(data.buffer_size || 0);
    document.getElementById('redis-buffer-threshold').textContent = formatBytes(data.buffer_threshold || 0);
    document.getElementById('redis-buffer-usage').textContent = (data.buffer_usage || 0).toFixed(2) + '%';
    
    // 更新图表
    updateRedisCharts(data);
}

// 更新 Redis 图表
function updateRedisCharts(data) {
    const now = new Date();
    const timeLabel = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    
    // 更新连接池使用情况图表
    if (redisConnectionsChart) {
        redisConnectionsChart.data.labels.push(timeLabel);
        redisConnectionsChart.data.datasets[0].data.push(data.connections_used || 0);
        
        // 保持最多20个数据点
        if (redisConnectionsChart.data.labels.length > 20) {
            redisConnectionsChart.data.labels.shift();
            redisConnectionsChart.data.datasets[0].data.shift();
        }
        
        redisConnectionsChart.update('none');
    }
    
    // 更新缓冲大小变化图表
    if (redisBufferChart) {
        // 将字节转换为MB
        const bufferSizeMB = (data.buffer_size || 0) / (1024 * 1024);
        redisBufferChart.data.labels.push(timeLabel);
        redisBufferChart.data.datasets[0].data.push(bufferSizeMB);
        
        // 保持最多20个数据点
        if (redisBufferChart.data.labels.length > 20) {
            redisBufferChart.data.labels.shift();
            redisBufferChart.data.datasets[0].data.shift();
        }
        
        redisBufferChart.update('none');
    }
}

// 格式化字节大小
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 获取日志
async function fetchLogs() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过日志数据获取');
        return;
    }
    
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
    const listEl = getElement('log-list');

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
                    <span class="log-time">${formatDateTime(log.timestamp, 'date')}</span>
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
    const lastUpdateEl = getElement('last-update');
    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    
    // 添加动画效果
    lastUpdateEl.classList.add('update-flashing');
    
    // 更新时间
    lastUpdateEl.textContent = `最后更新  ${timeStr}`;
    
    // 1秒后移除动画效果
    setTimeout(() => {
        lastUpdateEl.classList.remove('update-flashing');
    }, 1000);
}

// 页面切换逻辑
let currentPage = 'overview';
// 标记是否需要将请求标记为已读
let shouldMarkAPIRequestsAsRead = false;
let shouldMarkOutboundRequestsAsRead = false;

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
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过页面切换时的数据刷新');
        return;
    }
    
    // 处理接收请求和发送请求的特殊逻辑，即使是当前页面也需要执行
    if (pageName === 'api-requests') {
        shouldMarkAPIRequestsAsRead = true;
        fetchAPIRequests();
    } else if (pageName === 'outbound-requests') {
        shouldMarkOutboundRequestsAsRead = true;
        fetchOutboundRequests();
    }
    
    // 如果是当前页面，只处理数据刷新和角标逻辑，不切换页面显示
    if (currentPage === pageName) return;
    
    currentPage = pageName;
    
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-page') === pageName) {
            item.classList.add('active');
        }
    });
    
    document.querySelectorAll('.page-content').forEach(page => {
        page.classList.remove('active');
    });
    
    const targetPage = document.getElementById(`page-${pageName}`);
    if (targetPage) {
        targetPage.classList.add('active');
    }
    
    // 处理其他页面的逻辑
    if (pageName === 'database') {
        fetchDatabaseDetail();
    } else if (pageName === 'scheduler') {
        fetchSchedulerPage();
    } else if (pageName === 'event-helpers') {
        fetchEventStats();
        fetchEventHelpers();
        fetchDeadLetterStats();
    } else if (pageName === 'logs') {
        fetchLogsPage();
    }
}



// 获取事件统计数据
async function fetchEventStats() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过事件统计数据获取');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/events`);
        const data = await response.json();
        updateEventStatsDisplay(data);
    } catch (error) {
        console.error('获取事件统计失败:', error);
    }
}

// 获取事件辅助模块数据
async function fetchEventHelpers() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过事件辅助模块数据获取');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/event-helpers`);
        const data = await response.json();
        updateEventHelpersDisplay(data);
    } catch (error) {
        console.error('获取事件辅助模块数据失败:', error);
    }
}

// 更新事件统计显示
function updateEventStatsDisplay(data) {
    const eventStats = data.event_stats || {};
    const summary = data.summary || {};
    
    document.getElementById('events-total-received').textContent = summary.total_received || 0;
    document.getElementById('events-total-processed').textContent = summary.total_processed || 0;
    document.getElementById('events-total-failed').textContent = summary.total_failed || 0;
    document.getElementById('events-total-pending').textContent = summary.total_pending || 0;
    document.getElementById('events-success-rate').textContent = (summary.overall_success_rate || 0).toFixed(1) + '%';
    document.getElementById('events-active-types').textContent = `${summary.active_event_types || 0} / ${summary.total_event_types || 0}`;
    
    const tbodyEl = document.getElementById('events-tbody');
    
    if (Object.keys(eventStats).length === 0) {
        tbodyEl.innerHTML = '<tr><td colspan="11" class="empty-state">暂无事件统计</td></tr>';
        return;
    }
    
    tbodyEl.innerHTML = Object.entries(eventStats).map(([eventType, stats]) => {
        const status = getEventStatus(stats);
        const statusClass = status === '正常' ? 'healthy' : status === '警告' ? 'warning' : 'error';
        
        let lastActivity = '-';
        if (stats.last_activity_time) {
            lastActivity = formatDateTime(stats.last_activity_time, 'relative');
        }
        
        const successRate = stats.success_rate || 0;
        const avgLatency = stats.avg_processing_latency || 0;
        
        return `
        <tr>
            <td>${stats.description || eventType}</td>
            <td>${stats.total_received || 0}</td>
            <td>${stats.pending_count || 0}</td>
            <td>${stats.total_processed || 0}</td>
            <td>${stats.total_failed || 0}</td>
            <td>${successRate.toFixed(1)}%</td>
            <td>${avgLatency.toFixed(1)}ms</td>
            <td>${stats.current_buffer_size || 0} / ${stats.batch_size || 0}</td>
            <td>${lastActivity}</td>
            <td><span class="badge ${statusClass}">${status}</span></td>
            <td>
                <button class="btn btn-small" onclick="flushEvent('${eventType}')">刷新</button>
            </td>
        </tr>
        `;
    }).join('');
}

// 获取事件状态
function getEventStatus(stats) {
    const pending = stats.pending_count || 0;
    const batchSize = stats.batch_size || 10000;
    const successRate = stats.success_rate || 100;
    
    if (pending >= batchSize * 5 || successRate < 80) {
        return '异常';
    } else if (pending >= batchSize * 2 || successRate < 95) {
        return '警告';
    }
    return '正常';
}

// 刷新事件统计
function refreshEventStats() {
    fetchEventStats();
}

// 刷新所有事件
async function flushAllEvents() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过事件刷新');
        return;
    }
    
    try {
        await fetch(`${API_BASE}/events/flush`, { method: 'POST' });
        fetchEventStats();
    } catch (error) {
        console.error('刷新事件失败:', error);
    }
}

// 刷新指定事件
async function flushEvent(eventType) {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过指定事件刷新');
        return;
    }
    
    try {
        await fetch(`${API_BASE}/events/flush?event_type=${encodeURIComponent(eventType)}`, { method: 'POST' });
        fetchEventStats();
    } catch (error) {
        console.error('刷新事件失败:', error);
    }
}

// 重置事件统计
async function resetEventStats() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过事件统计重置');
        return;
    }
    
    if (!confirm('确定要重置所有事件统计吗？')) {
        return;
    }
    try {
        await fetch(`${API_BASE}/events/reset-stats`, { method: 'POST' });
        fetchEventStats();
    } catch (error) {
        console.error('重置事件统计失败:', error);
    }
}

// 数据库详情页面
async function fetchDatabaseDetail() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过数据库详情数据获取');
        return;
    }
    
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
    const mainDb = data.main_db;
    
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
            <td>${name === mainDb ? 'Ⓜ️ ' + name : name}</td>
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
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过 API 请求数据获取');
        return;
    }
    
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
    
    // 计算24小时前的时间戳
    const twentyFourHoursAgo = Date.now() / 1000 - (24 * 60 * 60);
    
    // 根据开关状态决定是否过滤内部请求，同时过滤最近24小时的请求
    const filteredRequests = showAPIIntternalRequests ? 
        requests.filter(request => request.timestamp >= twentyFourHoursAgo) :
        requests.filter(request => {
            // 过滤掉客户端IP为127.0.0.1、localhost或::1的请求，同时检查时间
            return request.client_ip !== '127.0.0.1' && request.client_ip !== 'localhost' && request.client_ip !== '::1' && request.timestamp >= twentyFourHoursAgo;
        });
    
    // 根据时间戳倒序排序
    filteredRequests.sort((a, b) => b.timestamp - a.timestamp);
    
    // 如果需要标记为已读，则将所有400+请求标记为已读
    if (shouldMarkAPIRequestsAsRead) {
        const readStatus = getAPIRequestReadStatus();
        filteredRequests.forEach(req => {
            if (req.status_code >= 400) {
                const requestId = generateAPIRequestId(req.timestamp, req.method, req.path, req.status_code);
                readStatus.add(requestId);
            }
        });
        saveAPIRequestReadStatus(readStatus);
        shouldMarkAPIRequestsAsRead = false;
    }
    
    // 获取已读状态
    const readStatus = getAPIRequestReadStatus();
    
    // 检查是否有未读的400+请求
    const hasUnreadErrors = filteredRequests.some(req => {
        if (req.status_code >= 400) {
            const requestId = generateAPIRequestId(req.timestamp, req.method, req.path, req.status_code);
            return !readStatus.has(requestId);
        }
        return false;
    });
    
    // 更新接收请求页签的红点角标
    const apiRequestsBadge = document.getElementById('api-requests-badge');
    if (apiRequestsBadge) {
        apiRequestsBadge.style.display = hasUnreadErrors ? 'inline-block' : 'none';
    }
    
    if (filteredRequests.length === 0) {
        tbodyEl.innerHTML = '<tr><td colspan="9" class="empty-state">暂无 API 请求记录</td></tr>';
        return;
    }
    
    // 使用文档片段进行批量DOM操作
    const fragment = document.createDocumentFragment();
    
    filteredRequests.forEach((req, index) => {
        const timeStr = formatDateTime(req.timestamp, 'datetime');
        
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
        
        const statusDescription = getStatusDescription(req.status_code);
        const statusText = statusDescription ? `${req.status_code} ${statusDescription}` : `${req.status_code}`;
        
        const tr = document.createElement('tr');
        tr.onclick = () => showRequestDetail(index);
        tr.dataset.requestIndex = index;
        tr.innerHTML = `
            <td class="font-mono">${index + 1}</td>
            <td>${timeStr}</td>
            <td><span class="api-method ${methodClass}">${req.method}</span></td>
            <td class="font-mono" style="font-size: 12px;">${req.path}</td>
            <td class="font-mono" style="font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${queryParamsDisplay}">${queryParamsDisplay || '-'}</td>
            <td><span class="api-status ${statusClass}">${statusText}</span></td>
            <td class="${durationClass}">${durationMs.toFixed(0)}ms</td>
            <td>${req.client_ip}</td>
            <td class="error-message-cell" title="${escapedErrorMsg}">${errorMsg}</td>
        `;
        fragment.appendChild(tr);
    });
    
    // 清空并添加新内容
    tbodyEl.innerHTML = '';
    tbodyEl.appendChild(fragment);
    
    // 存储过滤和排序后的请求数据，以便点击时使用，限制最近100条
    const filteredAndSortedRequests = filteredRequests.slice(0, 100);
    window.apiRequestsData = {
        ...data,
        recent_requests: filteredAndSortedRequests
    };
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
            <span class="api-detail-info-value font-mono" style="font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${queryParamsDisplay}">${queryParamsDisplay || '-'}</span>
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
    
    // 清理请求体和响应体内容，避免内存泄漏
    const requestBodyEl = document.getElementById('api-detail-request-body');
    const responseBodyEl = document.getElementById('api-detail-response-body');
    if (requestBodyEl) {
        requestBodyEl.textContent = '';
    }
    if (responseBodyEl) {
        responseBodyEl.textContent = '';
    }
    
    // 重置高亮按钮状态
    document.querySelectorAll('.section-actions button').forEach(btn => {
        if (btn.textContent === '已高亮') {
            btn.textContent = '高亮';
        }
    });
}

// 高亮请求体
function highlightRequestBody() {
    const requestBodyEl = document.getElementById('api-detail-request-body');
    if (typeof Prism !== 'undefined' && requestBodyEl) {
        // 保存原始内容
        const originalContent = requestBodyEl.textContent;
        // 清理旧的高亮内容
        requestBodyEl.innerHTML = originalContent;
        // 重新高亮
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
        // 保存原始内容
        const originalContent = responseBodyEl.textContent;
        // 清理旧的高亮内容
        responseBodyEl.innerHTML = originalContent;
        // 重新高亮
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
        // 获取原始内容，无论是否高亮
        let content = requestBodyEl.textContent;
        // 如果高亮后textContent为空，尝试获取innerText
        if (!content || content.trim() === '') {
            content = requestBodyEl.innerText;
        }
        navigator.clipboard.writeText(content)
            .then(() => {
                // 显示复制成功提示
                const sectionActions = requestBodyEl.closest('.api-detail-section').querySelector('.section-actions');
                const btn = sectionActions ? sectionActions.querySelector('button:nth-child(2)') : null;
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
        // 获取原始内容，无论是否高亮
        let content = responseBodyEl.textContent;
        // 如果高亮后textContent为空，尝试获取innerText
        if (!content || content.trim() === '') {
            content = responseBodyEl.innerText;
        }
        navigator.clipboard.writeText(content)
            .then(() => {
                // 显示复制成功提示
                const sectionActions = responseBodyEl.closest('.api-detail-section').querySelector('.section-actions');
                const btn = sectionActions ? sectionActions.querySelector('button:nth-child(2)') : null;
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
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过 API 统计重置');
        return;
    }
    
    try {
        await fetch(`${API_BASE}/http/reset`, { method: 'POST' });
        fetchAPIRequests();
    } catch (error) {
        console.error('重置 API 统计失败:', error);
    }
}

// 按日期获取请求记录
async function fetchRequestsByDate() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过按日期获取请求记录');
        return;
    }
    
    const datePicker = document.getElementById('api-date-picker');
    const date = datePicker.value;
    
    if (!date) {
        alert('请选择日期');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/http/requests?date=${date}`);
        const data = await response.json();
        updateAPIRequestsTable(data.requests);
        
        // 更新页面标题，显示当前查询的日期
        const pageTitle = document.querySelector('#page-api-requests h2');
        if (pageTitle) {
            pageTitle.textContent = `接收请求记录 (${date})`;
        }
    } catch (error) {
        console.error('按日期获取请求记录失败:', error);
        alert('获取请求记录失败，请稍后重试');
    }
}

function updateAPIRequestsTable(requests) {
    const tableBody = document.getElementById('api-requests-tbody');
    if (!tableBody) return;
    
    // 限制存储最近100条数据
    const limitedRequests = requests.slice(0, 100);
    
    if (limitedRequests.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="9" class="empty-state">暂无 API 请求记录</td></tr>';
        return;
    }
    
    // 使用文档片段减少DOM操作次数
    const fragment = document.createDocumentFragment();
    
    limitedRequests.forEach((req, index) => {
        const timeStr = formatDateTime(req.timestamp, 'datetime');
        
        const methodClass = req.method.toLowerCase();
        const isSuccess = req.status_code < 400;
        const statusClass = isSuccess ? 'success' : 'error';
        const errorMsg = req.error_message || '';
        
        // 转义特殊字符，防止HTML属性值被截断
        const escapedPath = req.path.replace(/"/g, '&quot;');
        const escapedErrorMsg = errorMsg.replace(/"/g, '&quot;');
        
        // 根据响应时间设置样式
        const durationMs = req.response_time;
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
        
        const statusDescription = getStatusDescription(req.status_code);
        const statusText = statusDescription ? `${req.status_code} ${statusDescription}` : `${req.status_code}`;
        
        const tr = document.createElement('tr');
        tr.onclick = () => {
            // 存储当前请求数据，以便点击时使用
            window.apiRequestsData = {
                recent_requests: limitedRequests
            };
            showRequestDetail(index);
        };
        tr.dataset.requestIndex = index;
        tr.innerHTML = `
            <td class="font-mono">${index + 1}</td>
            <td>${timeStr}</td>
            <td><span class="api-method ${methodClass}">${req.method}</span></td>
            <td class="font-mono" style="font-size: 12px;">${req.path}</td>
            <td class="font-mono" style="font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${queryParamsDisplay}">${queryParamsDisplay || '-'}</td>
            <td><span class="api-status ${statusClass}">${statusText}</span></td>
            <td class="${durationClass}">${durationMs.toFixed(0)}ms</td>
            <td>${req.client_ip}</td>
            <td class="error-message-cell" title="${escapedErrorMsg}">${errorMsg}</td>
        `;
        fragment.appendChild(tr);
    });
    
    tableBody.innerHTML = '';
    tableBody.appendChild(fragment);
}

// 按日期获取对外请求记录
async function fetchOutboundRequestsByDate() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过按日期获取对外请求记录');
        return;
    }
    
    const datePicker = document.getElementById('outbound-date-picker');
    const date = datePicker.value;
    
    if (!date) {
        alert('请选择日期');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/outbound-http/requests?date=${date}`);
        const data = await response.json();
        updateOutboundRequestsTable(data.requests);
        
        // 更新页面标题，显示当前查询的日期
        const pageTitle = document.querySelector('#page-outbound-requests h2');
        if (pageTitle) {
            pageTitle.textContent = `发送请求记录 (${date})`;
        }
    } catch (error) {
        console.error('按日期获取对外请求记录失败:', error);
        alert('获取对外请求记录失败，请稍后重试');
    }
}

// 日志页面
async function fetchLogsPage() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过日志数据获取');
        return;
    }
    
    try {
        const level = document.getElementById('log-page-level').value;
        const url = `${API_BASE}/logs?limit=100${level ? `&level=${level}` : ''}`;
        const response = await fetch(url);
        const data = await response.json();
        // 确保data.logs存在
        updateLogsPageDisplay(data.logs || []);
    } catch (error) {
        console.error('获取日志失败:', error);
        // 发生错误时显示空日志
        updateLogsPageDisplay([]);
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
    
    // 过滤掉非 warning 和 error 级别的日志
    const warningErrorLogs = logs.filter(log => log.level === 'warning' || log.level === 'error');
    
    // 根据开关状态过滤日志
    const filteredLogs = showReadLogs ? warningErrorLogs : warningErrorLogs.filter(log => {
        const logId = generateLogId(log.timestamp, log.module, log.message);
        return !readStatus.has(logId);
    });
    
    if (filteredLogs.length === 0) {
        tbodyEl.innerHTML = '<tr><td colspan="5" class="empty-state">暂无日志记录</td></tr>';
        checkAlertConditions();
        return;
    }
    
    tbodyEl.innerHTML = filteredLogs.map((log, index) => {
        const timeStr = formatDateTime(log.timestamp, 'datetime');
        
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
        
        // 移除模块名称中的"smart_"前缀
        const moduleName = log.module.replace(/^smart_/, '');
        
        return `
            <tr data-log-id="${logId}" data-log-index="${index}" class="${readStatusClass}" onclick="showLogDetail(${index})">
                <td class="font-mono">${index + 1}</td>
                <td>${timeStr}</td>
                <td><span class="log-level-badge ${log.level}">${log.level.toUpperCase()}</span></td>
                <td>${moduleName}</td>
                <td class="log-message-cell" title="${escapedFullMessage}" data-full-message="${escapedFullMessage}">${escapeHtml(log.message || '')}</td>
                <td class="read-status-cell">
                    <span class="read-checkbox ${readStatusClass}" onclick="toggleLogReadStatus('${logId}'); event.stopPropagation();">${readIcon}</span>
                </td>
            </tr>
        `;
    }).join('');
    
    // 保存日志数据，以便点击时使用
    window.logsData = filteredLogs;
    
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

// 生成接收请求唯一 ID
function generateAPIRequestId(timestamp, method, path, statusCode) {
    const str = `${timestamp}:${method}:${path}:${statusCode}`;
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
}

// 生成发送请求唯一 ID
function generateOutboundRequestId(timestamp, method, url, statusCode) {
    const str = `${timestamp}:${method}:${url}:${statusCode}`;
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
}

// 从 localStorage 获取接收请求已读状态
function getAPIRequestReadStatus() {
    try {
        const stored = localStorage.getItem('monitor_api_request_read_status');
        return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch (e) {
        console.error('读取接收请求已读状态失败:', e);
        return new Set();
    }
}

// 保存接收请求已读状态到 localStorage
function saveAPIRequestReadStatus(readStatus) {
    try {
        localStorage.setItem('monitor_api_request_read_status', JSON.stringify(Array.from(readStatus)));
    } catch (e) {
        console.error('保存接收请求已读状态失败:', e);
    }
}

// 从 localStorage 获取发送请求已读状态
function getOutboundRequestReadStatus() {
    try {
        const stored = localStorage.getItem('monitor_outbound_request_read_status');
        return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch (e) {
        console.error('读取发送请求已读状态失败:', e);
        return new Set();
    }
}

// 保存发送请求已读状态到 localStorage
function saveOutboundRequestReadStatus(readStatus) {
    try {
        localStorage.setItem('monitor_outbound_request_read_status', JSON.stringify(Array.from(readStatus)));
    } catch (e) {
        console.error('保存发送请求已读状态失败:', e);
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
    
    // 保存事件处理函数的引用
    const mouseEnterHandler = (e) => {
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
    };
    
    const mouseLeaveHandler = (e) => {
        if (e.target && typeof e.target.closest === 'function') {
            const cell = e.target.closest('.log-message-cell');
            if (cell) {
                tooltip.style.display = 'none';
            }
        }
    };
    
    const mouseMoveHandler = (e) => {
        if (e.target && typeof e.target.closest === 'function') {
            const cell = e.target.closest('.log-message-cell');
            if (!cell) {
                tooltip.style.display = 'none';
            }
        } else {
            // 如果 e.target 不支持 closest 方法，直接隐藏悬停框
            tooltip.style.display = 'none';
        }
    };
    
    // 添加事件监听器
    document.addEventListener('mouseenter', mouseEnterHandler);
    document.addEventListener('mouseleave', mouseLeaveHandler);
    document.addEventListener('mousemove', mouseMoveHandler);
    
    // 页面卸载时移除事件监听器
    window.addEventListener('beforeunload', function() {
        document.removeEventListener('mouseenter', mouseEnterHandler);
        document.removeEventListener('mouseleave', mouseLeaveHandler);
        document.removeEventListener('mousemove', mouseMoveHandler);
        // 移除悬停元素
        if (tooltip && tooltip.parentNode) {
            tooltip.parentNode.removeChild(tooltip);
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
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过定时任务详情数据获取');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/scheduler`);
        const data = await response.json();
        updateSchedulerDetailDisplay(data);
    } catch (error) {
        console.error('获取定时任务详情失败:', error);
    }
}

function updateSchedulerDetailDisplay(data) {
    console.log('定时任务数据:', data);
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
    // 项目级任务：PROJECT_DIR 目录下的任务
    const envData = getCachedData('environment');
    const projectDir = envData ? envData.project_dir : '';
    jobs.sort((a, b) => {
        const aIsProjectTask = projectDir && (a.name || a.id).includes(`project_files.${projectDir}`);
        const bIsProjectTask = projectDir && (b.name || b.id).includes(`project_files.${projectDir}`);
        const aIsSystem = !aIsProjectTask;
        const bIsSystem = !bIsProjectTask;
        if (aIsSystem && !bIsSystem) return -1;
        if (!aIsSystem && bIsSystem) return 1;
        return 0;
    });
    
    gridEl.innerHTML = jobs.map(job => {
        const lastRunTime = job.last_run_time ? formatDateTime(job.last_run_time) : '从未执行';
        const nextRunTime = job.next_run_time ? formatDateTime(job.next_run_time) : '未计划';
        const maxExecutionTime = job.max_execution_time ? `${job.max_execution_time.toFixed(2)} 秒` : '默认';
        const envData = getCachedData('environment');
        const projectDir = envData ? envData.project_dir : '';
        const isProjectTask = projectDir && (job.name || job.id).includes(`project_files.${projectDir}`);
        const isSystemTask = !isProjectTask;
        
        // 解析下次执行时间为日期和时间部分
        let timeStr = '未计划';
        let dateStr = '';
        if (job.next_run_time) {
            let date;
            if (typeof job.next_run_time === 'number') {
                date = new Date(job.next_run_time * 1000);
            } else if (typeof job.next_run_time === 'string') {
                date = new Date(job.next_run_time);
            } else {
                date = new Date(job.next_run_time);
            }
            
            if (!isNaN(date.getTime())) {
                timeStr = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
                
                // 计算日期差值，显示相对时间
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                
                const jobDate = new Date(date);
                jobDate.setHours(0, 0, 0, 0);
                
                const diffTime = jobDate - today;
                const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
                
                if (diffDays === 0) {
                    dateStr = '今天';
                } else if (diffDays === 1) {
                    dateStr = '明天';
                } else if (diffDays === 2) {
                    dateStr = '后天';
                } else {
                    dateStr = `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
                }
            }
        }
        
        return `
        <div class="scheduler-detail-item ${isSystemTask ? 'system-task' : ''}">
            <div class="scheduler-time-dot"></div>
            <div class="scheduler-time-section">
                <span class="scheduler-date">${dateStr}</span>
                <span class="scheduler-time">${timeStr}</span>
                ${job.next_run_time ? `<span class="scheduler-countdown" data-next-run-time="${job.next_run_time}">${formatNextExecutionTime(job.next_run_time)}</span>` : ''}
            </div>
            <div class="scheduler-content-section">
                <div class="scheduler-detail-header">
                    <a href="#" class="scheduler-detail-name">${job.description || job.name || job.id}</a>
                    <span class="scheduler-detail-status">
                        <span class="status-dot healthy"></span>
                        ${isSystemTask ? '系统' : '项目'}级任务
                    </span>
                </div>
                <table class="scheduler-detail-table">
                    <tr class="scheduler-detail-row">
                        <td class="scheduler-detail-label">定时规则</td>
                        <td class="scheduler-detail-value">${job.trigger || '未知'}</td>
                    </tr>
                    <tr class="scheduler-detail-row">
                        <td class="scheduler-detail-label">最近执行</td>
                        <td class="scheduler-detail-value execution-history">
                            ${job.execution_history && job.execution_history.length > 0 ? 
                                job.execution_history.slice().sort((a, b) => new Date(a.time) - new Date(b.time)).map(record => `
                                    <span class="execution-status ${record.error ? 'error' : 'success'}" ${record.error ? `title="${record.error}"` : ''}>
                                        ${formatRecentExecutionTime(record.time)}
                                    </span>
                                `).join('') : 
                                '<span class="execution-status never-executed">从未执行</span>'
                            }
                        </td>
                    </tr>

                    <tr class="scheduler-detail-row">
                        <td class="scheduler-detail-label">最大执行时间</td>
                        <td class="scheduler-detail-value">${maxExecutionTime}</td>
                    </tr>
                    ${job.execution_time ? `
                    <tr class="scheduler-detail-row">
                        <td class="scheduler-detail-label">平均执行时间</td>
                        <td class="scheduler-detail-value">${(job.execution_time * 1000).toFixed(0)} ms</td>
                    </tr>
                    ` : ''}

                </table>
            </div>
        </div>
        `;
    }).join('');
}

function refreshSchedulerPage() {
    fetchSchedulerPage();
}

// 格式化最近执行时间（相对时间）
function formatRecentExecutionTime(timestamp) {
    if (!timestamp) return '从未执行';
    
    let date;
    if (typeof timestamp === 'number') {
        date = new Date(timestamp * 1000);
    } else if (typeof timestamp === 'string') {
        date = new Date(timestamp);
    } else {
        date = new Date(timestamp);
    }
    
    if (isNaN(date.getTime())) {
        return '从未执行';
    }
    
    // 检查是否在最近24小时内
    const now = new Date();
    const twentyFourHoursAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    
    if (date < twentyFourHoursAgo) {
        return '超过24小时';
    }
    
    // 计算日期差值
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const execDate = new Date(date);
    execDate.setHours(0, 0, 0, 0);
    
    const diffTime = today - execDate;
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    let dayStr = '';
    if (diffDays === 0) {
        dayStr = '今天';
    } else if (diffDays === 1) {
        dayStr = '昨天';
    } else {
        dayStr = `${execDate.getMonth() + 1}月${execDate.getDate()}日`;
    }
    
    const timeStr = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    
    return `${dayStr} ${timeStr}`;
}

// 格式化下次执行时间（对于24小时内的任务显示倒计时）
function formatNextExecutionTime(timestamp) {
    if (!timestamp) return '未知';
    
    let date;
    if (typeof timestamp === 'number') {
        date = new Date(timestamp * 1000);
    } else if (typeof timestamp === 'string') {
        date = new Date(timestamp);
    } else {
        date = new Date(timestamp);
    }
    
    if (isNaN(date.getTime())) {
        return '未知';
    }
    
    const now = new Date();
    const diffMs = date - now;
    
    if (diffMs < 0) {
        return '已过期';
    }
    
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    
    if (diffHours < 24) {
        // 24小时内，显示实际倒计时
        const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
        const diffSeconds = Math.floor((diffMs % (1000 * 60)) / 1000);
        
        return `${diffHours.toString().padStart(2, '0')}:${diffMinutes.toString().padStart(2, '0')}:${diffSeconds.toString().padStart(2, '0')}`;
    } else {
        // 超过24小时，显示“X天X小时后”
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        const remainingHours = diffHours % 24;
        
        return `${diffDays}天${remainingHours}小时后`;
    }
}

// 更新倒计时
function updateCountdowns() {
    // 更新时间轴旁边的倒计时
    document.querySelectorAll('.scheduler-countdown').forEach(element => {
        const nextRunTimeStr = element.getAttribute('data-next-run-time');
        if (nextRunTimeStr) {
            const nextRunTime = new Date(nextRunTimeStr);
            const now = new Date();
            const diffMs = nextRunTime - now;
            
            if (diffMs < 0) {
                element.textContent = '执行中';
            } else {
                const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
                
                if (diffHours < 24) {
                    // 24小时内，显示倒计时
                    const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                    const diffSeconds = Math.floor((diffMs % (1000 * 60)) / 1000);
                    
                    element.textContent = `${diffHours.toString().padStart(2, '0')}:${diffMinutes.toString().padStart(2, '0')}:${diffSeconds.toString().padStart(2, '0')}`;
                } else {
                    // 超过24小时，显示“X天X小时后”
                    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
                    const remainingHours = diffHours % 24;
                    
                    element.textContent = `${diffDays}天${remainingHours}小时后`;
                }
            }
        }
    });
}

// 启动倒计时更新
setInterval(updateCountdowns, 1000);

// 开关状态：是否显示内部请求
let showInternalRequests = false;
// 开关状态：是否显示接收请求中的内部请求
let showAPIIntternalRequests = false;
// 开关状态：是否显示已读日志，默认隐藏已读
let showReadLogs = false;
// 存储发送请求数据
let outboundRequestsData = [];

// 获取发送请求数据
async function fetchOutboundRequests() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过发送请求数据获取');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/outbound-http/all`);
        const data = await response.json();
        
        // 调试：打印API返回的数据
        console.log('API返回的发送请求数据:', data);
        
        // 处理API响应数据，兼容不同的数据结构
        const requests = Array.isArray(data) ? data : (data.value || []);
        
        // 计算24小时前的时间戳
        const twentyFourHoursAgo = Date.now() / 1000 - (24 * 60 * 60);
        
        // 根据开关状态决定是否过滤本服务的请求，同时过滤最近24小时的请求
        const filteredRequests = showInternalRequests ? 
            requests.filter(request => request.timestamp >= twentyFourHoursAgo) : 
            requests.filter(request => {
                // 检查URL是否包含localhost或127.0.0.1，同时检查时间
                return !request.url.includes('localhost') && !request.url.includes('127.0.0.1') && request.timestamp >= twentyFourHoursAgo;
            });
        
        // 调试：打印过滤后的数据
        console.log('过滤后的发送请求数据:', filteredRequests);
        
        updateOutboundRequestsTable(filteredRequests);
        
        // 如果需要标记为已读，则将所有400+请求标记为已读
        if (shouldMarkOutboundRequestsAsRead) {
            const readStatus = getOutboundRequestReadStatus();
            filteredRequests.forEach(req => {
                if (req.status_code >= 400) {
                    const requestId = generateOutboundRequestId(req.timestamp, req.method, req.url, req.status_code);
                    readStatus.add(requestId);
                }
            });
            saveOutboundRequestReadStatus(readStatus);
            shouldMarkOutboundRequestsAsRead = false;
        }
        
        // 获取已读状态
        const readStatus = getOutboundRequestReadStatus();
        
        // 检查是否有未读的400+请求
        const hasUnreadErrors = filteredRequests.some(req => {
            if (req.status_code >= 400) {
                const requestId = generateOutboundRequestId(req.timestamp, req.method, req.url, req.status_code);
                return !readStatus.has(requestId);
            }
            return false;
        });
        
        // 更新发送请求页签的红点角标
        const outboundRequestsBadge = document.getElementById('outbound-requests-badge');
        if (outboundRequestsBadge) {
            outboundRequestsBadge.style.display = hasUnreadErrors ? 'inline-block' : 'none';
        }
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

// 切换接收请求中的内部请求显示状态
function toggleAPIIntternalRequests() {
    const checkbox = document.getElementById('show-api-internal-requests');
    showAPIIntternalRequests = checkbox.checked;
    fetchAPIRequests();
}

// 切换已读日志显示状态
function toggleReadLogs() {
    const checkbox = document.getElementById('show-read-logs');
    showReadLogs = checkbox.checked;
    fetchLogsPage();
}



// 更新发送请求表格
function updateOutboundRequestsTable(requests) {
    const tableBody = document.getElementById('outbound-requests-table');
    if (!tableBody) return;
    
    // 限制存储最近100条数据
    outboundRequestsData = requests.slice(0, 100);
    
    // 调试：打印outboundRequestsData
    console.log('outboundRequestsData:', outboundRequestsData);
    
    if (outboundRequestsData.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="empty-state">暂无发送请求记录</td></tr>';
        return;
    }
    
    // 使用文档片段减少DOM操作次数
    const fragment = document.createDocumentFragment();
    
    outboundRequestsData.forEach((request, index) => {
        const row = document.createElement('tr');
        row.innerHTML = formatOutboundRequestRow(request, index);
        row.onclick = () => showOutboundRequestDetail(index);
        row.setAttribute('data-request-index', index);
        fragment.appendChild(row);
    });
    
    tableBody.innerHTML = '';
    tableBody.appendChild(fragment);
}

// 获取状态码描述
function getStatusDescription(statusCode) {
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
}

// 格式化发送请求行
function formatOutboundRequestRow(request, index) {
    const timestamp = formatDateTime(request.timestamp, 'datetime');
    const duration = (request.duration * 1000).toFixed(0);
    const statusClass = request.status_code >= 400 ? 'error' : 'success';
    const durationClass = request.duration > 1 ? 'slow' : '';
    
    // 获取状态码描述
    const statusDescription = getStatusDescription(request.status_code);
    const statusText = statusDescription ? `${request.status_code} ${statusDescription}` : `${request.status_code}`;
    
    return `
    <tr data-request-index="${index}">
        <td class="font-mono">${index + 1}</td>
        <td>${timestamp}</td>
        <td><span class="method ${request.method.toLowerCase()}">${request.method}</span></td>
        <td class="url">${request.url}</td>
        <td class="status ${statusClass}">${statusText}</td>
        <td class="duration ${durationClass}">${duration}ms</td>
        <td>${request.module || 'unknown'}</td>
        <td class="error-message">${request.error_message || '-'}</td>
    </tr>
    `;
}

// 显示发送请求详情
function showOutboundRequestDetail(index) {
    const request = outboundRequestsData[index];
    // 调试：打印请求数据
    console.log('显示请求详情，索引:', index);
    console.log('请求数据:', request);
    console.log('响应体:', request.response_body);
    console.log('响应体类型:', typeof request.response_body);
    console.log('响应体是否为undefined:', request.response_body === undefined);
    console.log('响应体是否为null:', request.response_body === null);
    console.log('响应体条件判断结果:', request.response_body !== undefined && request.response_body !== null);
    const modal = document.createElement('div');
    modal.className = 'modal';
    
    // 解析可能的JSON字符串字段
    let parsedRequestHeaders = request.request_headers;
    if (typeof parsedRequestHeaders === 'string') {
        try {
            parsedRequestHeaders = JSON.parse(parsedRequestHeaders);
        } catch (e) {
            console.log('解析请求头JSON失败', e);
        }
    }
    
    let parsedResponseHeaders = request.response_headers;
    if (typeof parsedResponseHeaders === 'string') {
        try {
            parsedResponseHeaders = JSON.parse(parsedResponseHeaders);
        } catch (e) {
            console.log('解析响应头JSON失败', e);
        }
    }
    
    // 构建HTML内容
    let htmlContent = `
        <div class="modal-overlay"></div>
        <div class="modal-content">
            <div class="modal-header" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 15px;">
                <h3 style="margin: 0; font-size: 18px;">发送请求详情</h3>
                <div class="modal-actions" style="display: flex; align-items: center;">
                    <button class="export-btn" onclick="exportOutboundRequestDetail(${index})" style="padding: 8px 16px; border: none; border-radius: 8px; background-color: #4CAF50; color: white; font-weight: bold; cursor: pointer; font-size: 14px; transition: all 0.3s ease;">导出</button>
                    <button class="close-btn" onclick="this.closest('.modal').remove()" style="padding: 8px 16px; border: none; border-radius: 8px; background-color: #f44336; color: white; cursor: pointer; font-size: 14px; margin-left: 10px;">&times;</button>
                </div>
            </div>
            <div class="modal-body">
                <div class="detail-section">
                    <h4>基本信息</h4>
                    <table class="detail-table">
                        <tbody>
                            <tr>
                                <td class="detail-label">时间戳:</td>
                                <td class="detail-value">${typeof request.timestamp === 'string' ? request.timestamp : new Date(request.timestamp * 1000).toLocaleString('zh-CN')}</td>
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
                            </tr>`;
    
    // 错误信息部分
    if (request.error_message) {
        htmlContent += `
        <tr>
            <td class="detail-label">错误信息:</td>
            <td class="detail-value error">${request.error_message}</td>
        </tr>`;
    }
    
    htmlContent += `
                        </tbody>
                    </table>
                </div>`;
    
    // 请求头部分
    if (parsedRequestHeaders) {
        htmlContent += `
        <div class="detail-section">
            <h4>请求头</h4>
            <pre><code class="language-json">${JSON.stringify(parsedRequestHeaders, null, 2)}</code></pre>
        </div>`;
    }
    
    // 请求体部分
    if (request.request_body) {
        let formattedRequestBody = request.request_body;
        if (typeof request.request_body === 'string') {
            try {
                formattedRequestBody = JSON.stringify(JSON.parse(request.request_body), null, 2);
            } catch (e) {
                formattedRequestBody = request.request_body;
            }
        } else {
            formattedRequestBody = JSON.stringify(request.request_body, null, 2);
        }
        htmlContent += `
        <div class="detail-section">
            <h4>请求体</h4>
            <pre><code class="language-json">${formattedRequestBody}</code></pre>
        </div>`;
    }
    
    // 响应头部分
    if (parsedResponseHeaders) {
        htmlContent += `
        <div class="detail-section">
            <h4>响应头</h4>
            <pre><code class="language-json">${JSON.stringify(parsedResponseHeaders, null, 2)}</code></pre>
        </div>`;
    }
    
    // 响应体部分 - 关键修复：显示所有情况的响应体
    console.log('准备添加响应体部分...');
    console.log('响应体原始值:', request.response_body);
    console.log('响应体类型:', typeof request.response_body);
    console.log('响应体长度:', request.response_body ? request.response_body.length : 0);
    
    // 始终添加响应体部分
    let responseBodyContent = '无响应体数据';
    
    if (request.response_body !== undefined && request.response_body !== null) {
        console.log('响应体不为空，准备渲染...');
        try {
            if (typeof request.response_body === 'string') {
                try {
                    // 尝试解析JSON
                    const parsed = JSON.parse(request.response_body);
                    responseBodyContent = JSON.stringify(parsed, null, 2);
                } catch (e) {
                    console.log('JSON解析失败，使用原始响应体:', e);
                    responseBodyContent = request.response_body;
                }
            } else {
                responseBodyContent = JSON.stringify(request.response_body, null, 2);
            }
            console.log('格式化后的响应体:', responseBodyContent);
            console.log('格式化后响应体长度:', responseBodyContent.length);
        } catch (e) {
            console.log('响应体处理失败:', e);
            responseBodyContent = '响应体处理失败: ' + e.message;
        }
    } else {
        console.log('响应体为空或未定义');
    }
    
    // 强制添加响应体部分
    htmlContent += `
    <div class="detail-section">
        <h4>响应体</h4>
        <pre><code class="language-json">${responseBodyContent}</code></pre>
    </div>`;
    
    htmlContent += `
            </div>
        </div>`;
    
    modal.innerHTML = htmlContent;
    document.body.appendChild(modal);
    Prism.highlightAll();
}

// 导出发送请求详情
function exportOutboundRequestDetail(index) {
    const request = outboundRequestsData[index];
    
    // 解析可能的JSON字符串字段
    let parsedRequestHeaders = request.request_headers;
    if (typeof parsedRequestHeaders === 'string') {
        try {
            parsedRequestHeaders = JSON.parse(parsedRequestHeaders);
        } catch (e) {
            console.log('解析请求头JSON失败', e);
        }
    }
    
    let parsedResponseHeaders = request.response_headers;
    if (typeof parsedResponseHeaders === 'string') {
        try {
            parsedResponseHeaders = JSON.parse(parsedResponseHeaders);
        } catch (e) {
            console.log('解析响应头JSON失败', e);
        }
    }
    
    // 格式化请求体
    let formattedRequestBody = '';
    if (request.request_body) {
        formattedRequestBody = request.request_body;
        if (typeof request.request_body === 'string') {
            try {
                formattedRequestBody = JSON.stringify(JSON.parse(request.request_body), null, 2);
            } catch (e) {
                formattedRequestBody = request.request_body;
            }
        } else {
            formattedRequestBody = JSON.stringify(request.request_body, null, 2);
        }
    }
    
    // 格式化响应体
    let formattedResponseBody = '无响应体数据';
    if (request.response_body !== undefined && request.response_body !== null) {
        try {
            if (typeof request.response_body === 'string') {
                try {
                    // 尝试解析JSON
                    const parsed = JSON.parse(request.response_body);
                    formattedResponseBody = JSON.stringify(parsed, null, 2);
                } catch (e) {
                    formattedResponseBody = request.response_body;
                }
            } else {
                formattedResponseBody = JSON.stringify(request.response_body, null, 2);
            }
        } catch (e) {
            formattedResponseBody = '响应体处理失败: ' + e.message;
        }
    }
    
    // 处理时间戳
    let timestampDisplay = '';
    let filenameTimestamp = '';
    if (typeof request.timestamp === 'string') {
        timestampDisplay = request.timestamp;
        filenameTimestamp = request.timestamp.replace(/[: ]/g, '-');
    } else {
        timestampDisplay = new Date(request.timestamp * 1000).toLocaleString('zh-CN');
        filenameTimestamp = new Date(request.timestamp * 1000).toISOString().replace(/[: ]/g, '-');
    }
    
    // 构建导出HTML
    let html = `
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>发送请求详情</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }
            .modal-content {
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
            }
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                border-bottom: 1px solid #eee;
                padding-bottom: 10px;
            }
            .modal-header h3 {
                margin: 0;
                color: #333;
            }
            .detail-section {
                margin-bottom: 20px;
            }
            .detail-section h4 {
                margin: 0 0 10px 0;
                color: #555;
                border-bottom: 1px solid #eee;
                padding-bottom: 5px;
            }
            .detail-table {
                width: 100%;
                border-collapse: collapse;
            }
            .detail-table td {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            .detail-label {
                font-weight: bold;
                width: 100px;
                color: #555;
            }
            .detail-value {
                color: #333;
            }
            .detail-value.error {
                color: #f44336;
            }
            .detail-value.success {
                color: #4CAF50;
            }
            .detail-value.slow {
                color: #ff9800;
            }
            pre {
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
                overflow-x: auto;
                margin: 0;
            }
            code {
                font-family: 'Courier New', Courier, monospace;
            }
        </style>
    </head>
    <body>
        <div class="modal-content">
            <div class="modal-header">
                <h3>发送请求详情</h3>
            </div>
            <div class="modal-body">
                <div class="detail-section">
                    <h4>基本信息</h4>
                    <table class="detail-table">
                        <tbody>
                            <tr>
                                <td class="detail-label">时间戳:</td>
                                <td class="detail-value">${timestampDisplay}</td>
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
                            </tr>`;
    
    if (request.error_message) {
        html += `
                            <tr>
                                <td class="detail-label">错误信息:</td>
                                <td class="detail-value error">${request.error_message}</td>
                            </tr>`;
    }
    
    html += `
                        </tbody>
                    </table>
                </div>`;
    
    if (parsedRequestHeaders) {
        html += `
                <div class="detail-section">
                    <h4>请求头</h4>
                    <pre><code>${JSON.stringify(parsedRequestHeaders, null, 2)}</code></pre>
                </div>`;
    }
    
    if (formattedRequestBody) {
        html += `
                <div class="detail-section">
                    <h4>请求体</h4>
                    <pre><code>${formattedRequestBody}</code></pre>
                </div>`;
    }
    
    if (parsedResponseHeaders) {
        html += `
                <div class="detail-section">
                    <h4>响应头</h4>
                    <pre><code>${JSON.stringify(parsedResponseHeaders, null, 2)}</code></pre>
                </div>`;
    }
    
    if (formattedResponseBody) {
        html += `
                <div class="detail-section">
                    <h4>响应体</h4>
                    <pre><code>${formattedResponseBody}</code></pre>
                </div>`;
    }
    
    html += `
            </div>
        </div>
    </body>
    </html>
    `;
    
    // 导出为HTML文件
    const blob = new Blob([html], { type: 'text/html' });
    const urlBlob = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = urlBlob;
    
    // 获取时间戳作为文件名
    a.download = `outbound-request-${filenameTimestamp}.html`;
    
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(urlBlob);
}




// 刷新发送请求数据
function refreshOutboundRequests() {
    fetchOutboundRequests();
}

// 重置发送请求统计
async function resetOutboundStats() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过发送请求统计重置');
        return;
    }
    
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

// 添加请求时间戳，用于控制请求频率
const requestTimestamps = new Map();
const REQUEST_INTERVAL = 5000; // 请求间隔，单位毫秒

// 获取并更新overview页面的发送请求数据
async function fetchOverviewOutboundRequests() {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过overview页面发送请求数据获取');
        return;
    }
    
    // 检查请求频率，避免429错误
    const now = Date.now();
    const lastRequestTime = requestTimestamps.get('fetchOverviewOutboundRequests');
    if (lastRequestTime && now - lastRequestTime < REQUEST_INTERVAL) {
        console.log('请求频率过高，跳过overview页面发送请求数据获取');
        return;
    }
    
    try {
        // 记录请求时间
        requestTimestamps.set('fetchOverviewOutboundRequests', now);
        
        console.log('开始获取发送请求数据，API路径:', `${API_BASE}/outbound-http/all`);
        const response = await fetch(`${API_BASE}/outbound-http/all`);
        console.log('获取发送请求数据响应状态:', response.status);
        
        if (!response.ok) {
            // 处理429错误
            if (response.status === 429) {
                console.warn('请求频率过高，服务器返回429错误');
                // 使用默认值
                const defaultSummary = {
                    total_requests: 0,
                    error_rate: 0,
                    avg_response_time: 0,
                    requests_per_minute: 0
                };
                updateOverviewOutboundSummary(defaultSummary);
                updateOverviewOutboundList([]);
                
                // 更新状态徽章
                const badge = document.getElementById('outbound-badge');
                if (badge) {
                    badge.className = 'badge warning';
                    badge.textContent = '限流';
                }
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const requests = await response.json();
        console.log('获取发送请求数据成功，请求数量:', requests.length);
        
        // 计算24小时前的时间戳
        const twentyFourHoursAgo = Date.now() / 1000 - (24 * 60 * 60);
        
        // 过滤内部请求和最近24小时的请求
        const baseUrl = 'http://localhost:8000';
        const filteredRequests = requests.filter(request => {
            return !request.url.startsWith(baseUrl) && request.timestamp >= twentyFourHoursAgo;
        });
        console.log('过滤后请求数量:', filteredRequests.length);
        
        // 计算统计信息
        let summary = {
            total_requests: 0,
            error_rate: 0,
            avg_response_time: 0,
            requests_per_minute: 0
        };
        
        if (filteredRequests.length > 0) {
            const totalRequests = filteredRequests.length;
            const errorRequests = filteredRequests.filter(req => req.status_code >= 400).length;
            const totalResponseTime = filteredRequests.reduce((sum, req) => sum + req.duration, 0);
            
            summary = {
                total_requests: totalRequests,
                error_rate: (errorRequests / totalRequests) * 100,
                avg_response_time: totalResponseTime / totalRequests,
                requests_per_minute: 0
            };
        }
        
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
            // 更新已确认的错误状态，确保下次比较正确
            badgeConfirmedHasError['outbound-requests'] = hasErrors;
            // 保存已确认的错误状态到localStorage
            saveBadgeConfirmedHasError();
        }
    } catch (error) {
        console.error('获取overview页面发送请求数据失败:', error);
        console.error('错误详情:', error.message);
        console.error('错误堆栈:', error.stack);
        
        // 发生错误时使用默认值
        const defaultSummary = {
            total_requests: 0,
            error_rate: 0,
            avg_response_time: 0,
            requests_per_minute: 0
        };
        updateOverviewOutboundSummary(defaultSummary);
        updateOverviewOutboundList([]);
        
        // 更新状态徽章
        const badge = document.getElementById('outbound-badge');
        if (badge) {
            badge.className = 'badge error';
            badge.textContent = '错误';
        }
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

// 页面卸载时清理定时器
window.addEventListener('beforeunload', function() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    if (titleAlertInterval) {
        clearInterval(titleAlertInterval);
    }
});

// 监控内存使用
function monitorMemoryUsage() {
    if (performance && performance.memory) {
        const memory = performance.memory;
        console.log('Memory usage:', {
            used: (memory.usedJSHeapSize / 1024 / 1024).toFixed(2) + ' MB',
            total: (memory.totalJSHeapSize / 1024 / 1024).toFixed(2) + ' MB',
            limit: (memory.jsHeapSizeLimit / 1024 / 1024).toFixed(2) + ' MB'
        });
    }
}

// 定期监控内存使用
const memoryMonitorInterval = setInterval(monitorMemoryUsage, 60000); // 每分钟检查一次

// 页面卸载时清理内存监控定时器
window.addEventListener('beforeunload', function() {
    if (memoryMonitorInterval) {
        clearInterval(memoryMonitorInterval);
    }
});

// 显示日志详细信息
async function showLogDetail(index) {
    // 如果用户不活动，不发送请求
    if (isInactive) {
        console.log('用户不活动，跳过日志详情获取');
        return;
    }
    
    const logs = window.logsData || [];
    if (!logs[index]) return;
    
    // 获取完整的日志数据（包含所有级别，包括DEBUG）
    let allLogs = [];
    try {
        const response = await fetch(`${API_BASE}/logs?limit=200`);
        const data = await response.json();
        // 按时间倒序排列
        allLogs = data.logs.sort((a, b) => b.timestamp - a.timestamp);
    } catch (error) {
        console.error('获取完整日志失败:', error);
        allLogs = logs;
    }
    
    // 找到当前选中日志在完整数据中的索引
    const selectedLog = logs[index];
    const selectedLogIndex = allLogs.findIndex(log => 
        log.timestamp === selectedLog.timestamp && 
        log.module === selectedLog.module && 
        log.message === selectedLog.message
    );
    
    // 计算前后各10条日志的范围
    const startIndex = Math.max(0, selectedLogIndex - 10);
    const endIndex = Math.min(allLogs.length - 1, selectedLogIndex + 10);
    const surroundingLogs = allLogs.slice(startIndex, endIndex + 1);
    
    // 创建模态框
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-overlay"></div>
        <div class="modal-content">
            <div class="modal-header">
                <h3>日志详细信息</h3>
                <div class="modal-header-actions">
                    <select id="modal-log-level" onchange="filterModalLogs(this.value, ${selectedLogIndex})" style="margin-right: 12px; padding: 4px 8px; border: 1px solid #e8e8e8; border-radius: 4px;">
                        <option value="">全部级别 (含DEBUG)</option>
                        <option value="error">错误日志</option>
                        <option value="warning">警告日志</option>
                        <option value="info">信息日志</option>
                        <option value="debug">调试日志</option>
                    </select>
                    <button class="close-btn" onclick="this.closest('.modal').remove()">&times;</button>
                </div>
            </div>
            <div class="modal-body">
                <div class="log-detail-section">
                    <h4>选中日志</h4>
                    <div class="log-detail-item selected">
                        ${formatLogDetail(selectedLog, selectedLogIndex, selectedLogIndex)}
                    </div>
                </div>
                <div class="log-detail-section">
                    <h4>前后关联日志</h4>
                    <div class="surrounding-logs" id="surrounding-logs-container">
                        ${surroundingLogs.map((log, i) => {
                            const actualIndex = startIndex + i;
                            const isSelected = actualIndex === selectedLogIndex;
                            return `
                                <div class="log-detail-item ${isSelected ? 'selected' : ''}" data-log-level="${log.level}">
                                    ${formatLogDetail(log, actualIndex, selectedLogIndex)}
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    Prism.highlightAll();
    
    // 保存完整日志数据到模态框元素上
    modal.dataset.allLogs = JSON.stringify(allLogs);
    modal.dataset.selectedLogIndex = selectedLogIndex;
}

// 筛选模态框中的日志
function filterModalLogs(level, selectedLogIndex) {
    const modal = document.querySelector('.modal');
    if (!modal) return;
    
    const allLogs = JSON.parse(modal.dataset.allLogs);
    
    // 计算前后各10条日志的范围
    const startIndex = Math.max(0, selectedLogIndex - 10);
    const endIndex = Math.min(allLogs.length - 1, selectedLogIndex + 10);
    let surroundingLogs = allLogs.slice(startIndex, endIndex + 1);
    
    // 根据级别筛选
    if (level) {
        surroundingLogs = surroundingLogs.filter(log => log.level === level);
    }
    
    // 更新显示
    const container = document.getElementById('surrounding-logs-container');
    if (container) {
        container.innerHTML = surroundingLogs.map((log, i) => {
            const actualIndex = allLogs.findIndex(l => 
                l.timestamp === log.timestamp && 
                l.module === log.module && 
                l.message === log.message
            );
            const isSelected = actualIndex === selectedLogIndex;
            return `
                <div class="log-detail-item ${isSelected ? 'selected' : ''}" data-log-level="${log.level}">
                    ${formatLogDetail(log, actualIndex, selectedLogIndex)}
                </div>
            `;
        }).join('');
        
        Prism.highlightAll();
    }
}

// HTML转义函数，防止XSS攻击
function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// 格式化日志详细信息
function formatLogDetail(log, index, selectedIndex) {
    const date = new Date(log.timestamp * 1000);
    const timeStr = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2,'0')}-${date.getDate().toString().padStart(2,'0')} ${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}:${date.getSeconds().toString().padStart(2,'0')}.${date.getMilliseconds().toString().padStart(3,'0')}`;
    
    // 计算相对编号：选中的为0，早先为负数，晚为正数
    const relativeIndex = selectedIndex !== undefined ? index - selectedIndex : index;
    
    // 转义日志内容，防止HTML/JS注入
    const escapedMessage = escapeHtml(log.message || '');
    const escapedTraceback = log.traceback ? escapeHtml(log.traceback) : '';
    
    return `
        <div class="log-detail-header">
            <div class="log-detail-info">
                <span class="log-detail-index">#${relativeIndex}</span>
                <span class="log-level-badge ${log.level}">${log.level.toUpperCase()}</span>
                <span class="log-detail-module">${log.module}</span>
                <span class="log-detail-time">${timeStr}</span>
            </div>
        </div>
        <div class="log-detail-message">
            <pre><code class="language-text">${escapedMessage}</code></pre>
        </div>
        ${escapedTraceback ? `
        <div class="log-detail-traceback">
            <h5>堆栈跟踪</h5>
            <pre><code class="language-python">${escapedTraceback}</code></pre>
        </div>
        ` : ''}
    `;
}

// 刷新死信队列统计
async function refreshDeadLetterStats() {
    try {
        const response = await fetch(`${API_BASE}/dead-letter`);
        const data = await response.json();
        updateDeadLetterDisplay(data);
    } catch (error) {
        console.error('获取死信队列数据失败:', error);
    }
}

// 清空死信队列
async function clearDeadLetters() {
    try {
        const response = await fetch(`${API_BASE}/dead-letter/clear`, {
            method: 'POST'
        });
        const data = await response.json();
        if (data.success) {
            refreshDeadLetterStats();
            showNotification('死信队列已清空', 'success');
        } else {
            showNotification('清空死信队列失败', 'error');
        }
    } catch (error) {
        console.error('清空死信队列失败:', error);
        showNotification('清空死信队列失败', 'error');
    }
}

// 更新死信队列显示
function updateDeadLetterDisplay(data) {
    const deadLetters = data.dead_letters || [];
    const total = deadLetters.length;
    const recent = deadLetters.length > 0 ? formatDateTime(deadLetters[0].timestamp) : '--';
    const successRate = data.success_rate || 0;
    
    // 更新汇总数据
    const totalEl = document.getElementById('dead-letter-total');
    if (totalEl) totalEl.textContent = total;
    
    const recentEl = document.getElementById('dead-letter-recent');
    if (recentEl) recentEl.textContent = recent;
    
    const rateEl = document.getElementById('dead-letter-success-rate');
    if (rateEl) rateEl.textContent = successRate.toFixed(2) + '%';
    
    // 更新死信列表
    const tbody = document.getElementById('dead-letter-tbody');
    if (tbody) {
        if (deadLetters.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无DL</td></tr>';
            return;
        }
        
        // 使用文档片段进行批量DOM操作
        const fragment = document.createDocumentFragment();
        deadLetters.forEach(letter => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${letter.id}</td>
                <td>${letter.event_type}</td>
                <td>${formatDateTime(letter.timestamp)}</td>
                <td>${letter.event_data.database || 'unknown'}</td>
                <td>${letter.event_data.table || 'unknown'}</td>
                <td class="error-message">${letter.error_message}</td>
                <td>
                    <button class="btn btn-small" onclick="reprocessDeadLetter('${letter.id}')">重新处理</button>
                </td>
            `;
            fragment.appendChild(tr);
        });
        
        // 清空并添加新内容
        tbody.innerHTML = '';
        tbody.appendChild(fragment);
    }
}

// 重新处理死信
async function reprocessDeadLetter(letterId) {
    try {
        const response = await fetch(`${API_BASE}/dead-letter/reprocess/${letterId}`, {
            method: 'POST'
        });
        const data = await response.json();
        if (data.success) {
            refreshDeadLetterStats();
            showNotification('死信重新处理成功', 'success');
        } else {
            showNotification('死信重新处理失败', 'error');
        }
    } catch (error) {
        console.error('重新处理死信失败:', error);
        showNotification('重新处理死信失败', 'error');
    }
}

// 显示通知
function showNotification(message, type) {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    
    // 添加到页面
    document.body.appendChild(notification);
    
    // 显示通知
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    // 3秒后隐藏通知
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// 获取死信队列数据
async function fetchDeadLetterStats() {
    try {
        const response = await fetch(`${API_BASE}/dead-letter`);
        const data = await response.json();
        updateDeadLetterDisplay(data);
    } catch (error) {
        console.error('获取死信队列数据失败:', error);
    }
}

// 在数据库页面刷新时获取数据库详细信息
async function refreshDatabasePage() {
    await fetchDatabaseDetail();
}

// 更新事件辅助模块显示
function updateEventHelpersDisplay(data) {
    if (!data) return;
    
    // 回调跟踪器
    if (data.callback_tracker) {
        const tracker = data.callback_tracker;
        getElement('callback-pending').textContent = tracker.pending_count || 0;
        getElement('callback-max-retries').textContent = tracker.max_retries || 3;
        getElement('callback-pending-retries').textContent = tracker.total_pending_retries || 0;
    }
    
    // 死信队列
    if (data.dead_letter_queue) {
        const dlq = data.dead_letter_queue;
        getElement('dlq-pending').textContent = dlq.pending_count || 0;
        getElement('dlq-total').textContent = dlq.total_event_count || 0;
        getElement('dlq-file-size').textContent = formatFileSize(dlq.total_file_size || 0);
        getElement('dlq-running').textContent = dlq.running ? '运行中' : '已停止';
        
        // 更新死信队列详细信息区域
        const totalEl = document.getElementById('dead-letter-total');
        if (totalEl) totalEl.textContent = dlq.total_event_count || 0;
        
        const recentEl = document.getElementById('dead-letter-recent');
        if (recentEl) recentEl.textContent = '-';
        
        const rateEl = document.getElementById('dead-letter-success-rate');
        if (rateEl) rateEl.textContent = '100%';
    }
    
    // 事件去重器
    if (data.event_deduplicator) {
        const deduplicator = data.event_deduplicator;
        getElement('deduplicator-total').textContent = deduplicator.total_entries || 0;
        getElement('deduplicator-active').textContent = deduplicator.active_entries || 0;
        getElement('deduplicator-ttl').textContent = deduplicator.ttl || 300;
        getElement('deduplicator-max').textContent = deduplicator.max_entries || 100000;
    }
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}
