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
        label: '基本校验通过',
        colorClass: 'text-info',
        bgClass: 'bg-info',
        badgeClass: 'status-badge status-badge-compliance_pass',
        icon: 'check-circle'
    },
    COMPLIANCE_ERROR: {
        value: 'compliance_error',
        label: '基本校验错误',
        colorClass: 'text-danger',
        bgClass: 'bg-danger',
        badgeClass: 'status-badge status-badge-compliance_error',
        icon: 'x-circle'
    },
    RELATION_PASS: {
        value: 'relation_pass',
        label: '联合校验通过',
        colorClass: 'text-success',
        bgClass: 'bg-success',
        badgeClass: 'status-badge status-badge-relation_pass',
        icon: 'link'
    },
    RELATION_ERROR: {
        value: 'relation_error',
        label: '联合校验错误',
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
    'compliance_pass': '基本校验通过',
    'compliance_error': '基本校验错误',
    'relation_pass': '联合校验通过',
    'relation_error': '联合校验错误',
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


// ==================== 状态元数据加载（阶段一新增）====================
let STAGING_STATUS_META = null;
let STAGING_META_LOADED = false;

/**
 * 从后端加载状态元数据
 * @param {boolean} forceReload - 强制重新加载
 * @returns {Promise<Object|null>}
 */
async function loadStatusMeta(forceReload = false) {
    if (STAGING_STATUS_META && !forceReload) {
        return STAGING_STATUS_META;
    }
    
    try {
        const response = await callApi('/status-meta');
        if (response && response.success === 1) {
            STAGING_STATUS_META = {};
            response.data.forEach(item => {
                STAGING_STATUS_META[item.value] = item;
            });
            STAGING_META_LOADED = true;
            console.log('状态元数据加载成功:', Object.keys(STAGING_STATUS_META));
        }
    } catch (e) {
        console.warn('加载状态元数据失败，使用硬编码 fallback', e);
        STAGING_META_LOADED = true;
    }
    
    return STAGING_STATUS_META;
}

/**
 * 等待状态元数据加载完成
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<void>}
 */
async function waitForStatusMeta(timeout = 3000) {
    const startTime = Date.now();
    while (!STAGING_META_LOADED && (Date.now() - startTime) < timeout) {
        await new Promise(resolve => setTimeout(resolve, 50));
    }
}

// 页面加载时自动加载状态元数据（非阻塞）
document.addEventListener('DOMContentLoaded', () => {
    loadStatusMeta().catch(e => console.warn('自动加载状态元数据失败', e));
});

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
    }, 5000);
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
    
    // 优先使用后端元数据
    const meta = STAGING_STATUS_META?.[normalizedStatus];
    if (meta) {
        return {
            value: meta.value,
            label: meta.label,
            colorClass: `text-${meta.color}`,
            bgClass: `bg-${meta.color}`,
            badgeClass: `badge bg-${meta.color}`,
            icon: 'circle'
        };
    }
    
    // Fallback到旧的硬编码
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

async function uploadFile(tableName, file, dedupStrategy = 'overwrite') {
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



/**
 * 获取校验规则文档
 * @param {string} tableKey - 表名
 * @returns {Promise<Object>} 校验规则
 */
async function getValidationRules(tableKey) {
    try {
        const response = await callApi(`/rules/${tableKey}`);
        if (response.success === 1) {
            return response.data;
        }
        return null;
    } catch (error) {
        console.error('获取校验规则失败:', error);
        return null;
    }
}

/**
 * 渲染校验规则HTML
 * @param {Object} rules - 校验规则数据
 * @returns {string} HTML字符串
 */
function renderValidationRulesHtml(rules) {
    if (!rules) {
        return `
            <div class="text-center py-5">
                <i class="bi bi-inbox fs-1 text-muted"></i>
                <p class="mt-3 text-muted">暂无校验规则</p>
            </div>
        `;
    }

    let html = `
        <div class="validation-rules">
    `;

    // 必填字段卡片
    if (rules.required_fields && rules.required_fields.length > 0) {
        html += `
            <div class="card rule-card mb-4 border-0 shadow-sm">
                <div class="card-header bg-white border-bottom-0 py-3">
                    <h6 class="mb-0 d-flex align-items-center text-primary">
                        <span class="rule-icon bg-primary bg-opacity-10 text-primary rounded-circle d-inline-flex align-items-center justify-content-center me-3">
                            <i class="bi bi-asterisk fs-5"></i>
                        </span>
                        <span class="fw-bold">必填字段</span>
                        <span class="ms-auto badge bg-primary bg-opacity-10 text-primary rounded-pill">${rules.required_fields.length}</span>
                    </h6>
                </div>
                <div class="card-body pt-0">
                    <div class="row g-2">
        `;
        rules.required_fields.forEach(field => {
            html += `
                <div class="col-md-6">
                    <div class="d-flex align-items-start p-2 rounded bg-light bg-opacity-50">
                        <span class="field-badge bg-primary text-white rounded-circle d-inline-flex align-items-center justify-content-center me-2 flex-shrink-0" style="width: 28px; height: 28px; font-size: 0.7rem;">R</span>
                        <div class="flex-grow-1">
                            <div class="fw-semibold text-primary">${escapeHtml(field.field)}</div>
                            <div class="text-muted small">${escapeHtml(field.description)}</div>
                        </div>
                    </div>
                </div>
            `;
        });
        html += `</div></div></div>`;
    }

    // 枚举字段卡片
    if (rules.enum_fields && rules.enum_fields.length > 0) {
        html += `
            <div class="card rule-card mb-4 border-0 shadow-sm">
                <div class="card-header bg-white border-bottom-0 py-3">
                    <h6 class="mb-0 d-flex align-items-center text-info">
                        <span class="rule-icon bg-info bg-opacity-10 text-info rounded-circle d-inline-flex align-items-center justify-content-center me-3">
                            <i class="bi bi-list-check fs-5"></i>
                        </span>
                        <span class="fw-bold">枚举字段</span>
                        <span class="ms-auto badge bg-info bg-opacity-10 text-info rounded-pill">${rules.enum_fields.length}</span>
                    </h6>
                </div>
                <div class="card-body pt-0">
        `;
        rules.enum_fields.forEach(field => {
            const allowedValues = Array.isArray(field.allowed_values) 
                ? field.allowed_values.map(v => `<span class="badge bg-info bg-opacity-10 text-info me-1 px-3 py-1">${escapeHtml(v)}</span>`).join(' ') 
                : '';
            html += `
                <div class="mb-3 pb-2 border-bottom border-light last-child-border-0">
                    <div class="d-flex align-items-center mb-2">
                        <span class="field-badge bg-info text-white rounded-circle d-inline-flex align-items-center justify-content-center me-2 flex-shrink-0" style="width: 28px; height: 28px; font-size: 0.7rem;">E</span>
                        <strong class="text-info">${escapeHtml(field.field)}</strong>
                        <span class="text-muted small ms-2">${escapeHtml(field.description)}</span>
                    </div>
                    <div class="ms-5">
                        <div class="d-flex flex-wrap gap-2">${allowedValues}</div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    }

    // 数值范围卡片
    if (rules.range_fields && rules.range_fields.length > 0) {
        html += `
            <div class="card rule-card mb-4 border-0 shadow-sm">
                <div class="card-header bg-white border-bottom-0 py-3">
                    <h6 class="mb-0 d-flex align-items-center text-warning">
                        <span class="rule-icon bg-warning bg-opacity-10 text-warning rounded-circle d-inline-flex align-items-center justify-content-center me-3">
                            <i class="bi bi-rulers fs-5"></i>
                        </span>
                        <span class="fw-bold">数值范围</span>
                        <span class="ms-auto badge bg-warning bg-opacity-10 text-warning rounded-pill">${rules.range_fields.length}</span>
                    </h6>
                </div>
                <div class="card-body pt-0">
        `;
        rules.range_fields.forEach(field => {
            let constraints = [];
            if (field.ge !== null && field.ge !== undefined) constraints.push(`≥ <strong>${field.ge}</strong>`);
            if (field.gt !== null && field.gt !== undefined) constraints.push(`> <strong>${field.gt}</strong>`);
            if (field.le !== null && field.le !== undefined) constraints.push(`≤ <strong>${field.le}</strong>`);
            if (field.lt !== null && field.lt !== undefined) constraints.push(`< <strong>${field.lt}</strong>`);
            
            html += `
                <div class="mb-3 pb-2 border-bottom border-light">
                    <div class="d-flex align-items-center mb-2">
                        <span class="field-badge bg-warning text-white rounded-circle d-inline-flex align-items-center justify-content-center me-2 flex-shrink-0" style="width: 28px; height: 28px; font-size: 0.7rem;">N</span>
                        <strong class="text-warning">${escapeHtml(field.field)}</strong>
                        <span class="text-muted small ms-2">${escapeHtml(field.description)}</span>
                    </div>
                    <div class="ms-5">
                        <div class="d-flex gap-3">${constraints.join('<span class="text-muted">•</span>')}</div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    }

    // 长度限制卡片
    if (rules.max_length_fields && rules.max_length_fields.length > 0) {
        html += `
            <div class="card rule-card mb-4 border-0 shadow-sm">
                <div class="card-header bg-white border-bottom-0 py-3">
                    <h6 class="mb-0 d-flex align-items-center text-success">
                        <span class="rule-icon bg-success bg-opacity-10 text-success rounded-circle d-inline-flex align-items-center justify-content-center me-3">
                            <i class="bi bi-text-paragraph fs-5"></i>
                        </span>
                        <span class="fw-bold">长度限制</span>
                        <span class="ms-auto badge bg-success bg-opacity-10 text-success rounded-pill">${rules.max_length_fields.length}</span>
                    </h6>
                </div>
                <div class="card-body pt-0">
                    <div class="row g-2">
        `;
        rules.max_length_fields.forEach(field => {
            html += `
                <div class="col-md-6">
                    <div class="d-flex align-items-center p-2 rounded bg-light bg-opacity-50">
                        <span class="field-badge bg-success text-white rounded-circle d-inline-flex align-items-center justify-content-center me-2 flex-shrink-0" style="width: 28px; height: 28px; font-size: 0.7rem;">L</span>
                        <div class="flex-grow-1">
                            <div class="fw-semibold text-success">${escapeHtml(field.field)}</div>
                            <div class="text-muted small">${escapeHtml(field.description)} · 最大 ${field.max_length} 字符</div>
                        </div>
                    </div>
                </div>
            `;
        });
        html += `</div></div></div>`;
    }

    // 外键约束卡片
    if (rules.foreign_keys && rules.foreign_keys.length > 0) {
        html += `
            <div class="card rule-card mb-4 border-0 shadow-sm">
                <div class="card-header bg-white border-bottom-0 py-3">
                    <h6 class="mb-0 d-flex align-items-center text-secondary">
                        <span class="rule-icon bg-secondary bg-opacity-10 text-secondary rounded-circle d-inline-flex align-items-center justify-content-center me-3">
                            <i class="bi bi-link-45deg fs-5"></i>
                        </span>
                        <span class="fw-bold">外键约束</span>
                        <span class="ms-auto badge bg-secondary bg-opacity-10 text-secondary rounded-pill">${rules.foreign_keys.length}</span>
                    </h6>
                </div>
                <div class="card-body pt-0">
                    <div class="row g-2">
        `;
        rules.foreign_keys.forEach(field => {
            html += `
                <div class="col-md-6">
                    <div class="d-flex align-items-center p-2 rounded bg-light bg-opacity-50">
                        <span class="field-badge bg-secondary text-white rounded-circle d-inline-flex align-items-center justify-content-center me-2 flex-shrink-0" style="width: 28px; height: 28px; font-size: 0.7rem;">F</span>
                        <div class="flex-grow-1">
                            <div class="fw-semibold text-secondary">${escapeHtml(field.field)}</div>
                            <div class="text-muted small">${escapeHtml(field.description)}</div>
                        </div>
                    </div>
                </div>
            `;
        });
        html += `</div></div></div>`;
    }

    // 业务规则卡片
    if (rules.business_rules && rules.business_rules.length > 0) {
        html += `
            <div class="card rule-card border-0 shadow-sm">
                <div class="card-header bg-white border-bottom-0 py-3">
                    <h6 class="mb-0 d-flex align-items-center text-purple">
                        <span class="rule-icon bg-purple bg-opacity-10 text-purple rounded-circle d-inline-flex align-items-center justify-content-center me-3">
                            <i class="bi bi-lightning-charge-fill fs-5"></i>
                        </span>
                        <span class="fw-bold">业务规则</span>
                        <span class="ms-auto badge bg-purple bg-opacity-10 text-purple rounded-pill">${rules.business_rules.length}</span>
                    </h6>
                </div>
                <div class="card-body pt-0">
        `;
        rules.business_rules.forEach((rule, idx) => {
            html += `
                <div class="mb-3 pb-3 border-bottom border-light last-child-border-0">
                    <div class="d-flex align-items-start">
                        <span class="rule-number bg-purple text-white rounded-circle d-inline-flex align-items-center justify-content-center me-3 flex-shrink-0" style="width: 32px; height: 32px; font-size: 0.8rem;">${idx+1}</span>
                        <div class="flex-grow-1">
                            <div class="fw-bold text-purple mb-1">${rule.name ? escapeHtml(rule.name) : `规则 ${idx+1}`}</div>
                            ${rule.description ? `<div class="text-muted small">${escapeHtml(rule.description)}</div>` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    }

    html += `</div>`;
    return html;
}

/**
 * 显示校验规则弹窗
 * @param {string} tableKey - 表名
 * @param {string} tableName - 显示名称
 */
async function showValidationRulesModal(tableKey, tableName) {
    try {
        const rules = await getValidationRules(tableKey);
        
        modalManager.register('validationRules', {
            id: 'validationRulesModal',
            title: `${tableName || tableKey} 校验规则`,
            size: 'lg',
            body: (data) => {
                if (!data.rules) {
                    return '<div class="text-center py-4"><div class="spinner-border text-primary"></div><p class="mt-2 text-muted">加载中...</p></div>';
                }
                return renderValidationRulesHtml(data.rules);
            },
            footer: '<button type="button" class="btn btn-primary" data-bs-dismiss="modal">关闭</button>',
            onOpen: (data, modalElement) => {
                if (data.rules) {
                    const bodyEl = modalElement.querySelector('#validationRulesModal_body');
                    bodyEl.innerHTML = renderValidationRulesHtml(data.rules);
                }
            }
        });
        
        modalManager.open('validationRules', { rules });
    } catch (error) {
        console.error('显示校验规则失败:', error);
        showMessage('加载校验规则失败', 'danger');
    }
}
