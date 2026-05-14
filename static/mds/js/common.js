/**
 * @file common.js
 * @description 公共函数库 - 工具函数、状态定义、通用UI操作
 * @author Frontend Team
 * @version 1.1.0
 * @date 2026-05-14
 */

const API_BASE = '/api/mds';

/**
 * 缓冲表状态枚举定义
 * @enum {Object}
 */
const STAGING_STATUS = {
    PENDING: {
        value: 'pending',
        label: '待处理',
        colorClass: 'text-warning',
        bgClass: 'bg-warning',
        badgeClass: 'status-badge status-badge-pending',
        icon: 'clock'
    },
    COMPLIANCE_PASS: {
        value: 'compliance_pass',
        label: '合规通过',
        colorClass: 'text-info',
        bgClass: 'bg-info',
        badgeClass: 'status-badge status-badge-compliance_pass',
        icon: 'check-circle'
    },
    COMPLIANCE_ERROR: {
        value: 'compliance_error',
        label: '合规错误',
        colorClass: 'text-danger',
        bgClass: 'bg-danger',
        badgeClass: 'status-badge status-badge-compliance_error',
        icon: 'x-circle'
    },
    RELATION_PASS: {
        value: 'relation_pass',
        label: '关联通过',
        colorClass: 'text-success',
        bgClass: 'bg-success',
        badgeClass: 'status-badge status-badge-relation_pass',
        icon: 'link'
    },
    RELATION_ERROR: {
        value: 'relation_error',
        label: '关联错误',
        colorClass: 'text-warning',
        bgClass: 'bg-warning',
        badgeClass: 'status-badge status-badge-relation_error',
        icon: 'alert-circle'
    },
    SYNCED: {
        value: 'synced',
        label: '已推送',
        colorClass: 'text-info',
        bgClass: 'bg-info',
        badgeClass: 'status-badge status-badge-synced',
        icon: 'send'
    }
};

// 旧状态映射（兼容历史数据）
const LEGACY_STATUS_MAP = {
    'validated': 'relation_pass',
    'rejected': 'compliance_error'
};

const STATUS_COLORS = {
    'pending': 'pending',
    'compliance_pass': 'compliance_pass',
    'compliance_error': 'compliance_error',
    'relation_pass': 'relation_pass',
    'relation_error': 'relation_error',
    'synced': 'synced',
    // 兼容旧状态
    'validated': 'validated',
    'rejected': 'rejected'
};

const STATUS_TEXTS = {
    'pending': '待处理',
    'compliance_pass': '合规通过',
    'compliance_error': '合规错误',
    'relation_pass': '关联通过',
    'relation_error': '关联错误',
    'synced': '已推送',
    // 兼容旧状态
    'validated': '校验通过',
    'rejected': '校验失败'
};

async function callApi(endpoint, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };
    
    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        const result = await response.json();
        return result;
    } catch (error) {
        console.error('API调用失败:', error);
        return { success: 0, message: error.message };
    }
}

function handleResponse(response, onSuccess, onError) {
    if (response.success === 1) {
        if (onSuccess) onSuccess(response);
    } else {
        if (onError) {
            onError(response);
        } else {
            showMessage(response.message || '操作失败', 'danger');
        }
    }
}

function showMessage(message, type = 'info') {
    const container = document.querySelector('.toast-container') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast show align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    const second = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

/**
 * 获取状态配置信息
 * @param {string} status - 状态值
 * @returns {Object} 状态配置对象
 */
function getStatusConfig(status) {
    // 兼容旧状态
    const normalizedStatus = LEGACY_STATUS_MAP[status] || status;
    const colorKey = STATUS_COLORS[normalizedStatus] || STATUS_COLORS[status] || 'secondary';
    return STAGING_STATUS[normalizedStatus.toUpperCase()] || {
        value: status,
        label: STATUS_TEXTS[normalizedStatus] || STATUS_TEXTS[status] || status,
        colorClass: `text-${colorKey}`,
        bgClass: `bg-${colorKey}`,
        badgeClass: `status-badge status-badge-${colorKey}`
    };
}

/**
 * 格式化状态显示
 * @param {string} status - 状态值
 * @returns {string} HTML字符串
 */
function formatStatus(status) {
    const config = getStatusConfig(status);
    return `<span class="badge ${config.badgeClass}">${config.label}</span>`;
}

function showLoading() {
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.id = 'loadingOverlay';
    overlay.innerHTML = `
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">加载中...</span>
        </div>
    `;
    document.body.appendChild(overlay);
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.remove();
}

function showProgress(title, total) {
    let progressOverlay = document.getElementById('progressOverlay');
    if (!progressOverlay) {
        progressOverlay = document.createElement('div');
        progressOverlay.id = 'progressOverlay';
        progressOverlay.className = 'progress-overlay';
        progressOverlay.innerHTML = `
            <div class="progress-container">
                <div class="progress-title">${title}</div>
                <div class="progress-bar-wrapper">
                    <div class="progress-bar" style="width: 0%"></div>
                </div>
                <div class="progress-text">0/${total}</div>
            </div>
        `;
        document.body.appendChild(progressOverlay);
    } else {
        progressOverlay.querySelector('.progress-title').textContent = title;
        progressOverlay.querySelector('.progress-text').textContent = `0/${total}`;
        progressOverlay.querySelector('.progress-bar').style.width = '0%';
    }
}

function updateProgress(current, total, text) {
    const progressOverlay = document.getElementById('progressOverlay');
    if (progressOverlay) {
        const percent = Math.min(100, Math.round((current / total) * 100));
        progressOverlay.querySelector('.progress-bar').style.width = percent + '%';
        progressOverlay.querySelector('.progress-text').textContent = text || `${current}/${total}`;
    }
}

function setProgressIndeterminate(isIndeterminate) {
    const progressOverlay = document.getElementById('progressOverlay');
    if (progressOverlay) {
        const progressBar = progressOverlay.querySelector('.progress-bar');
        if (isIndeterminate) {
            progressBar.classList.add('progress-bar-indeterminate');
            progressBar.style.width = '100%';
        } else {
            progressBar.classList.remove('progress-bar-indeterminate');
        }
    }
}

function hideProgress() {
    const progressOverlay = document.getElementById('progressOverlay');
    if (progressOverlay) progressOverlay.remove();
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function truncateText(text, maxLength = 50) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

async function uploadFile(tableName, file, dedupStrategy = 'skip') {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(
            `${API_BASE}/upload/${tableName}?dedup_strategy=${dedupStrategy}`,
            {
                method: 'POST',
                body: formData
            }
        );
        const result = await response.json();
        return result;
    } catch (error) {
        console.error('文件上传失败:', error);
        return { success: 0, message: error.message };
    }
}

function downloadTemplate(tableName) {
    const templates = {
        't_material': [
            ['物料号', '物料描述', '工厂', '物料类型', '虚拟件', '可否延迟', '批量策略', '提前期', '最小批量', '最大批量', '单位'],
            ['MAT001', '示例物料', '1000', 'P', 'N', 'Y', 'EX', '10', '1', '100', 'EA']
        ],
        't_workcenter': [
            ['工作中心', '描述', '瓶颈', '有限产能', '产能'],
            ['WC001', '示例工作中心', 'N', 'Y', '100']
        ],
        't_mat_ver': [
            ['物料号', '版本号', '描述', '激活', '批量下限', '批量上限'],
            ['MAT001', 'V1', '示例版本', 'Y', '1', '1000']
        ],
        't_mat_wc': [
            ['物料号', '版本号', '工序号', '工作中心', '串并行', '基础工时'],
            ['MAT001', 'V1', 'P01', 'WC001', 'S', '60']
        ],
        't_mat_wc_bom': [
            ['父件料号', '子件料号', '版本号', '工序号', '用量', '损耗率', 'MTO', '替代料'],
            ['MAT001', 'COMP001', 'V1', 'P01', '2', '5', 'N', 'N']
        ],
        't_mold': [
            ['模具编号', '描述', '类型', '状态', '穴数', '台数'],
            ['MOLD001', '示例模具', '注塑', '空闲', '4', '1']
        ],
        't_mat_wc_mold': [
            ['物料号', '工作中心', '工序号', '模具编号', 'UPH'],
            ['MAT001', 'WC001', 'P01', 'MOLD001', '100']
        ]
    };
    
    const data = templates[tableName] || [['暂无模板']];
    let csv = data.map(row => row.join(',')).join('\n');
    
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = `${tableName}_template.csv`;
    link.click();
    
    setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
}
