/**
 * 物料数据特定逻辑
 */

const TABLE_NAME = 't_material';

const TABLE_COLUMNS = [
    { field: '_staging_id', title: 'ID', width: '60px' },
    { field: 'materialno', title: '物料号', width: '120px', sortable: true },
    { field: 'description', title: '物料描述', width: '200px' },
    { field: 'plant', title: '工厂', width: '80px' },
    { field: 'type', title: '类型', width: '60px' },
    { field: 'unit', title: '单位', width: '60px' },
    { field: '_source_system', title: '来源', width: '80px' },
    { field: '_status', title: '状态', width: '100px' },
    { field: '_createtime', title: '创建时间', width: '150px', sortable: true }
];

let dataTable;
let statusCard;

function initPage() {
    statusCard = new StatusCard({
        tableName: TABLE_NAME,
        container: document.getElementById('statusCardContainer'),
        onStatusClick: (status) => {
            dataTable.setFilter('_status', status);
        }
    });
    
    dataTable = new DataTable({
        tableName: TABLE_NAME,
        columns: TABLE_COLUMNS,
        container: document.getElementById('tableContainer'),
        pageSize: 20,
        onRowClick: (row) => showDetailModal(row)
    });
    
    bindFilterEvents();
    bindActionEvents();
    bindUploadEvents();
}

function bindFilterEvents() {
    const statusFilter = document.getElementById('statusFilter');
    const sourceFilter = document.getElementById('sourceFilter');
    const keywordInput = document.getElementById('keywordInput');
    const searchBtn = document.getElementById('searchBtn');
    const resetBtn = document.getElementById('resetBtn');
    
    if (statusFilter) {
        statusFilter.addEventListener('change', (e) => {
            dataTable.setFilter('_status', e.target.value);
        });
    }
    
    if (sourceFilter) {
        sourceFilter.addEventListener('change', (e) => {
            dataTable.setFilter('source_system', e.target.value);
        });
    }
    
    if (searchBtn && keywordInput) {
        searchBtn.addEventListener('click', () => {
            dataTable.setFilter('keyword', keywordInput.value.trim());
        });
        
        keywordInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                dataTable.setFilter('keyword', keywordInput.value.trim());
            }
        });
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (statusFilter) statusFilter.value = '';
            if (sourceFilter) sourceFilter.value = '';
            if (keywordInput) keywordInput.value = '';
            statusCard.setActiveStatus(null);
            dataTable.filters = {};
            dataTable.loadData();
        });
    }
}

function bindActionEvents() {
    const validateBtn = document.getElementById('validateBtn');
    const validateAllBtn = document.getElementById('validateAllBtn');
    const syncBtn = document.getElementById('syncBtn');
    const syncAllBtn = document.getElementById('syncAllBtn');
    
    if (validateBtn) {
        validateBtn.addEventListener('click', () => validateData());
    }
    
    if (validateAllBtn) {
        validateAllBtn.addEventListener('click', () => validateAllData());
    }
    
    if (syncBtn) {
        syncBtn.addEventListener('click', () => syncData());
    }
    
    if (syncAllBtn) {
        syncAllBtn.addEventListener('click', () => syncAllData());
    }
}

function bindUploadEvents() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const dedupStrategy = document.getElementById('dedupStrategy');
    
    if (uploadArea && fileInput) {
        uploadArea.addEventListener('click', () => fileInput.click());
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileUpload(files[0]);
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFileUpload(e.target.files[0]);
            }
        });
    }
    
    if (uploadBtn) {
        uploadBtn.addEventListener('click', () => {
            if (fileInput && fileInput.files.length > 0) {
                handleFileUpload(fileInput.files[0]);
            } else {
                showMessage('请先选择文件', 'warning');
            }
        });
    }
}

async function handleFileUpload(file) {
    if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
        showMessage('请上传Excel或CSV文件', 'warning');
        return;
    }
    
    const strategy = document.getElementById('dedupStrategy')?.value || 'skip';
    
    showLoading();
    
    const response = await uploadFile(TABLE_NAME, file, strategy);
    
    hideLoading();
    
    handleResponse(response, (data) => {
        const result = data.data;
        showMessage(`导入完成: 成功${result.inserted}条, 跳过${result.skipped}条`, 'success');
        
        if (fileInput) fileInput.value = '';
        
        dataTable.refresh();
        statusCard.refresh();
    });
}

async function validateData() {
    showLoading();
    
    const response = await callApi(`/validate/${TABLE_NAME}`, 'POST');
    
    hideLoading();
    
    handleResponse(response, (data) => {
        const stats = data.data;
        showMessage(`校验完成: 通过${stats.validated}条, 失败${stats.rejected}条`, 'success');
        dataTable.refresh();
        statusCard.refresh();
    });
}

async function validateAllData() {
    if (!confirm('确定要校验所有待处理数据吗？')) return;
    
    showLoading();
    
    const response = await callApi('/validate_all', 'POST');
    
    hideLoading();
    
    handleResponse(response, (data) => {
        showMessage('所有表校验完成', 'success');
        dataTable.refresh();
        statusCard.refresh();
    });
}

async function syncData() {
    showLoading();
    
    const response = await callApi(`/sync/${TABLE_NAME}`, 'POST');
    
    hideLoading();
    
    handleResponse(response, (data) => {
        const stats = data.data;
        showMessage(`同步完成: 成功${stats.synced}条, 失败${stats.failed}条`, 'success');
        dataTable.refresh();
        statusCard.refresh();
    });
}

async function syncAllData() {
    if (!confirm('确定要同步所有校验通过的数据吗？')) return;
    
    showLoading();
    
    const response = await callApi('/sync_all', 'POST');
    
    hideLoading();
    
    handleResponse(response, (data) => {
        showMessage('所有表同步完成', 'success');
        dataTable.refresh();
        statusCard.refresh();
    });
}

function showDetailModal(row) {
    const modal = new bootstrap.Modal(document.getElementById('detailModal'));
    
    document.getElementById('detailTitle').textContent = `记录详情 - ${row.materialno}`;
    
    const detailContent = document.getElementById('detailContent');
    detailContent.innerHTML = `
        <table class="table table-sm">
            <tbody>
                ${Object.entries(row).map(([key, value]) => `
                    <tr>
                        <th style="width: 150px;">${escapeHtml(key)}</th>
                        <td>${formatDetailValue(key, value)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    const editBtn = document.getElementById('editBtn');
    const deleteBtn = document.getElementById('deleteBtn');
    
    if (editBtn) {
        editBtn.onclick = () => showEditModal(row);
    }
    
    if (deleteBtn) {
        deleteBtn.onclick = () => deleteRecord(row._staging_id);
    }
    
    if (row._status === 'rejected' && row._error_msg) {
        showErrorDetail(row._error_msg);
    }
    
    modal.show();
}

function formatDetailValue(key, value) {
    if (key === '_status') {
        return formatStatus(value);
    }
    if (key === '_createtime' || key === '_updatetime' || key === '_synced_time') {
        return formatDate(value);
    }
    if (value === null || value === undefined) {
        return '<span class="text-muted">-</span>';
    }
    return escapeHtml(String(value));
}

function showErrorDetail(errorMsg) {
    try {
        const errors = JSON.parse(errorMsg);
        const errorContainer = document.getElementById('errorContainer');
        
        if (errorContainer && errors.length > 0) {
            errorContainer.innerHTML = `
                <div class="alert alert-danger">
                    <strong>校验错误：</strong>
                    ${errors.map(e => `
                        <div class="error-detail mt-2">
                            <div><span class="error-type">${e.error_type}</span> - <span class="error-field">${e.error_field}</span></div>
                            <div class="error-message">${escapeHtml(e.error_message)}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
    } catch (e) {
        console.error('解析错误信息失败:', e);
    }
}

function showEditModal(row) {
    const modal = new bootstrap.Modal(document.getElementById('editModal'));
    
    const editForm = document.getElementById('editForm');
    editForm.innerHTML = TABLE_COLUMNS
        .filter(col => !col.field.startsWith('_'))
        .map(col => `
            <div class="mb-3">
                <label class="form-label">${col.title}</label>
                <input type="text" class="form-control" name="${col.field}" 
                       value="${escapeHtml(row[col.field] || '')}">
            </div>
        `).join('');
    
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) {
        saveBtn.onclick = () => saveRecord(row._staging_id);
    }
    
    modal.show();
}

async function saveRecord(stagingId) {
    const form = document.getElementById('editForm');
    const formData = new FormData(form);
    const data = {};
    
    formData.forEach((value, key) => {
        data[key] = value;
    });
    
    showLoading();
    
    const response = await callApi(`/update/${TABLE_NAME}/${stagingId}`, 'PATCH', data);
    
    hideLoading();
    
    handleResponse(response, () => {
        showMessage('保存成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
        dataTable.refresh();
    });
}

async function deleteRecord(stagingId) {
    if (!confirm('确定删除此记录吗？')) return;
    
    showLoading();
    
    const response = await callApi(`/delete/${TABLE_NAME}/${stagingId}`, 'DELETE');
    
    hideLoading();
    
    handleResponse(response, () => {
        showMessage('删除成功', 'success');
        bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();
        dataTable.refresh();
        statusCard.refresh();
    });
}

document.addEventListener('DOMContentLoaded', initPage);
