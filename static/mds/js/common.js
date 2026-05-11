/**
 * 公共函数库
 */

const API_BASE = '/api/mds';

const STATUS_COLORS = {
    'pending': 'warning',
    'validated': 'success',
    'rejected': 'danger',
    'synced': 'info'
};

const STATUS_TEXTS = {
    'pending': '待处理',
    'validated': '校验通过',
    'rejected': '校验失败',
    'synced': '已同步'
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
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatStatus(status) {
    const color = STATUS_COLORS[status] || 'secondary';
    const text = STATUS_TEXTS[status] || status;
    return `<span class="badge badge-${status}">${text}</span>`;
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
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${tableName}_template.csv`;
    link.click();
}
