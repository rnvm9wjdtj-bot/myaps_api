/**
 * 物料数据特定逻辑
 */

const TABLE_NAME = 't_material';

// 必填字段 - 与后端 schemas.py 中的定义保持一致
// 仅包含使用 ... 作为默认值的字段
const REQUIRED_FIELDS = ['materialno', 'description', 'leadday', 'grday', 'abc', 'unit'];

const TABLE_COLUMNS = [
    { field: '_status', title: '状态', width: '80px' },
    { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
    { field: 'materialno', title: '物料号', width: '100px', sortable: true },
    { field: 'description', title: '物料描述', width: '150px' },
    { field: 'size', title: '规格' },
    { field: 'plant', title: '工厂', width: '70px' },
    { field: 'planner', title: '计划员' },
    { field: 'fifo', title: 'FIFO', width: '50px' },
    { field: 'leadday', title: '提前期', width: '60px' },
    { field: 'expday', title: '保质期', width: '60px' },
    { field: 'grday', title: '质检期', width: '60px' },
    { field: 'abc', title: 'ABC', width: '50px' },
    { field: 'unit', title: '单位', width: '50px' },
    { field: 'price', title: '价格', width: '80px' },
    { field: 'groupno', title: '型号' },
    { field: 'type', title: '类型', width: '50px' },
    { field: 'phantom', title: '虚拟件', width: '60px' },
    { field: 'phantommin', title: '虚拟时间', width: '70px' },
    { field: 'firmday', title: '固定天数', width: '60px' },
    { field: 'daygap', title: '拆分天数', width: '60px' },
    { field: 'candelay', title: '可延迟', width: '60px' },
    { field: 'lotsize', title: '批量策略', width: '70px' },
    { field: 'lotfix', title: '固定批', width: '60px' },
    { field: 'lotmin', title: '最小批', width: '60px' },
    { field: 'lotmax', title: '最大批', width: '60px' },
    { field: 'lotround', title: '取整值', width: '60px' },
    { field: 'lotss', title: '安全库存', width: '60px' },
    { field: 'lotpoint', title: '订货点', width: '60px' },
    { field: 'lottop', title: '最大库存', width: '60px' },
    { field: 'planitem', title: '产品组' },
    { field: 'preday', title: '向前冲销', width: '60px' },
    { field: 'subday', title: '向后冲销', width: '60px' },
    { field: 'free1', title: '自定义1' },
    { field: 'free2', title: '自定义2' },
    { field: 'free3', title: '自定义3' },
    { field: '_source_system', title: '来源', width: '80px' }
];

const FIELD_LABELS = {};
TABLE_COLUMNS.forEach(col => {
    FIELD_LABELS[col.field] = col.title;
});

const INTERNAL_FIELDS = ['_staging_id', '_source_system', '_source_id', '_status', 
                         '_error_msg', '_transform_rules', '_retry_count', 
                         '_createtime', '_updatetime', '_synced_id', '_synced_time'];

const ENUM_OPTIONS = {
    fifo: [
        { value: '0', label: '最近原则' },
        { value: '1', label: 'FIFO' }
    ],
    abc: [
        { value: 'A', label: 'A类' },
        { value: 'B', label: 'B类' },
        { value: 'C', label: 'C类' }
    ],
    type: [
        { value: 'E', label: '自制件(E)' },
        { value: 'F', label: '采购件(F)' }
    ],
    phantom: [
        { value: 'N', label: '否' },
        { value: 'Y', label: '是' }
    ],
    candelay: [
        { value: 'N', label: '否' },
        { value: 'Y', label: '是' }
    ],
    lotsize: [
        { value: 'EX', label: 'EX-一对一' },
        { value: 'FX', label: 'FX-固定批' },
        { value: 'VB', label: 'VB-重订货点' },
        { value: 'D1', label: 'D1-按1天合并' },
        { value: 'D2', label: 'D2-按2天合并' },
        { value: 'D3', label: 'D3-按3天合并' },
        { value: 'D4', label: 'D4-按4天合并' },
        { value: 'D5', label: 'D5-按5天合并' },
        { value: 'D6', label: 'D6-按6天合并' },
        { value: 'W1', label: 'W1-按1周合并' },
        { value: 'W2', label: 'W2-按2周合并' },
        { value: 'W3', label: 'W3-按3周合并' },
        { value: 'W4', label: 'W4-按4周合并' },
        { value: 'M1', label: 'M1-按1月合并' },
        { value: 'M2', label: 'M2-按2月合并' },
        { value: 'M3', label: 'M3-按3月合并' }
    ]
};

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
        pageSize: 100,
        onRowClick: (row) => showEditModal(row),
        enumFields: Object.keys(ENUM_OPTIONS)
    });
    
    dataTable.loadData();
    
    bindFilterEvents();
    bindActionEvents();
    bindUploadEvents();
    bindAdvancedFilterEvents();
    bindBatchEditEvents();
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
    const rulesBtn = document.getElementById('rulesBtn');
    
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
    
    if (rulesBtn) {
        rulesBtn.addEventListener('click', () => showValidationRulesModal(TABLE_NAME, '物料'));
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
    const pendingCount = await getPendingCount();
    if (pendingCount === 0) {
        showMessage('没有待处理的记录', 'warning');
        return;
    }
    
    showProgress('校验中', pendingCount);
    
    let totalValidated = 0;
    let totalRejected = 0;
    let totalFilled = 0;
    let processed = 0;
    let lastProcessed = 0;
    
    while (true) {
        setProgressIndeterminate(true);
        
        const response = await callApi(`/validate/${TABLE_NAME}?batch_size=200`, 'POST');
        
        setProgressIndeterminate(false);
        
        if (response.success !== 1) {
            hideProgress();
            showMessage(response.message || '校验失败', 'danger');
            break;
        }
        
        const stats = response.data;
        // 后端返回字段映射：relation_pass -> validated，relation_error+compliance_error -> rejected
        const batchValidated = stats.relation_pass || 0;
        const batchRejected = (stats.relation_error || 0) + (stats.compliance_error || 0);
        const batchProcessed = batchValidated + batchRejected;
        
        totalValidated += batchValidated;
        totalRejected += batchRejected;
        totalFilled += stats.filled || 0;
        
        if (batchProcessed > 0) {
            await animateProgress(processed, processed + batchProcessed, pendingCount, `已处理 ${processed + batchProcessed}/${pendingCount}`);
            processed += batchProcessed;
        }
        
        if (batchProcessed === 0) {
            break;
        }
        
        await sleep(50);
    }
    
    hideProgress();
    
    const filledMsg = totalFilled ? `，填充默认值${totalFilled}条` : '';
    showMessage(`校验完成: 通过${totalValidated}条，失败${totalRejected}条${filledMsg}`, 'success');
    dataTable.refresh();
    statusCard.refresh();
}

async function animateProgress(from, to, total, text) {
    const steps = 10;
    const stepSize = (to - from) / steps;
    
    for (let i = 1; i <= steps; i++) {
        const current = Math.round(from + stepSize * i);
        updateProgress(current, total, text);
        await sleep(30);
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function getPendingCount() {
    const response = await callApi(`/status/${TABLE_NAME}`);
    if (response.success === 1) {
        return response.data.pending || 0;
    }
    return 0;
}

async function validateAllData() {
    if (!confirm('确定要校验所有待处理数据吗？')) return;
    
    showProgress('校验所有表', 100);
    
    const response = await callApi('/validate_all', 'POST');
    
    hideProgress();
    
    handleResponse(response, (data) => {
        showMessage('所有表校验完成', 'success');
        dataTable.refresh();
        statusCard.refresh();
    });
}

async function syncData() {
    const response = await callApi(`/status/${TABLE_NAME}`);
    if (response.success !== 1) {
        showMessage('获取状态失败', 'danger');
        return;
    }
    
    const stats = response.data;
    const validatedCount = stats.validated || 0;
    const retryExceeded = stats.retry_exceeded || 0;
    
    if (validatedCount === 0) {
        showMessage('没有校验通过的记录可同步', 'warning');
        return;
    }
    
    // 如果有超过重试次数的记录，询问是否重置
    let resetRetry = false;
    if (retryExceeded > 0) {
        resetRetry = confirm(`有${retryExceeded}条记录的重试次数已达上限，是否重置重试次数后同步？\n\n点击"确定"重置并同步，点击"取消"跳过这些记录`);
    }
    
    const { mode, targetDbs } = await showSyncModeDialog(validatedCount);
    if (!mode || !targetDbs || targetDbs.length === 0) return;
    
    const targetDbParam = targetDbs.join(',');
    const totalCount = validatedCount * targetDbs.length;
    
    showProgress(mode === 'incremental' ? '增量同步中' : '刷新同步中', totalCount);
    
    let totalSynced = 0;
    let totalFailed = 0;
    let processed = 0;
    
    // 构建API URL
    const baseUrl = `/sync/${TABLE_NAME}?batch_size=200&mode=${mode}&target_dbs=${encodeURIComponent(targetDbParam)}&reset_retry=${resetRetry}`;
    
    // 刷新模式只调用一次，增量模式循环调用
    if (mode === 'refresh') {
        // 刷新模式：一次性同步
        setProgressIndeterminate(true);
        const syncResponse = await callApi(baseUrl, 'POST');
        setProgressIndeterminate(false);
        
        if (syncResponse.success !== 1) {
            hideProgress();
            showMessage(syncResponse.message || '同步失败', 'danger');
        } else {
            const syncStats = syncResponse.data;
            totalSynced = syncStats.total_synced || 0;
            totalFailed = syncStats.total_failed || 0;
            updateProgress(totalSynced + totalFailed, totalCount, `已处理 ${totalSynced + totalFailed}/${totalCount}`);
            
            // 根据成功/失败显示不同消息
            if (totalFailed > 0) {
                showMessage(`同步完成: ${targetDbs.length}个账套, 成功${totalSynced}条, 失败${totalFailed}条（部分记录缺少必填字段）`, 'warning');
            } else {
                showMessage(`同步完成: ${targetDbs.length}个账套, 成功${totalSynced}条`, 'success');
            }
        }
    } else {
        // 增量模式：循环调用直到没有数据
        let firstCall = true;
        while (true) {
            setProgressIndeterminate(true);
            const url = firstCall ? baseUrl : `/sync/${TABLE_NAME}?batch_size=200&mode=${mode}&target_dbs=${encodeURIComponent(targetDbParam)}`;
            const syncResponse = await callApi(url, 'POST');
            setProgressIndeterminate(false);
            firstCall = false;
            
            if (syncResponse.success !== 1) {
                hideProgress();
                showMessage(syncResponse.message || '同步失败', 'danger');
                break;
            }
            
            const syncStats = syncResponse.data;
            const batchSynced = syncStats.total_synced || 0;
            const batchFailed = syncStats.total_failed || 0;
            
            totalSynced += batchSynced;
            totalFailed += batchFailed;
            processed += batchSynced + batchFailed;
            
            if (processed > 0) {
                updateProgress(processed, totalCount, `已处理 ${processed}/${totalCount}`);
            }
            
            if (batchSynced === 0 && batchFailed === 0) {
                break;
            }
            
            await sleep(50);
        }
        
        // 根据成功/失败显示不同消息
        if (totalFailed > 0) {
            showMessage(`同步完成: ${targetDbs.length}个账套, 成功${totalSynced}条, 失败${totalFailed}条（部分记录缺少必填字段）`, 'warning');
        } else {
            showMessage(`同步完成: ${targetDbs.length}个账套, 成功${totalSynced}条`, 'success');
        }
    }
    
    hideProgress();
    
    dataTable.refresh();
    statusCard.refresh();
}

async function showSyncModeDialog(validatedCount) {
    // 获取账套列表
    const dbListResponse = await callApi('/dblist');
    const dbList = dbListResponse.success === 1 ? dbListResponse.data : [];
    
    return new Promise((resolve) => {
        const modalHtml = `
            <div class="modal fade" id="syncModeModal" tabindex="-1">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">选择同步模式</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label fw-bold">目标账套</label>
                                <div class="border rounded p-2" style="max-height: 150px; overflow-y: auto;">
                                    ${dbList.map((db, idx) => `
                                        <div class="form-check">
                                            <input class="form-check-input target-db-checkbox" type="checkbox" id="targetDb_${idx}" value="${db}" checked>
                                            <label class="form-check-label" for="targetDb_${idx}">${db}</label>
                                        </div>
                                    `).join('')}
                                </div>
                                <div class="form-text">默认全选，可取消勾选排除不需要同步的账套</div>
                            </div>
                            <hr>
                            <div class="mb-3">
                                <label class="form-label fw-bold">同步模式</label>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="syncMode" id="modeIncremental" value="incremental" checked>
                                    <label class="form-check-label" for="modeIncremental">
                                        <strong>增量同步</strong> <span class="badge bg-primary">${validatedCount}条</span>
                                    </label>
                                    <div class="text-muted small mt-1">仅同步校验通过的新数据，保留正式表现有数据</div>
                                </div>
                            </div>
                            <div class="mb-3">
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="syncMode" id="modeRefresh" value="refresh">
                                    <label class="form-check-label" for="modeRefresh">
                                        <strong>刷新同步</strong> <span class="badge bg-warning text-dark">${validatedCount}条</span>
                                    </label>
                                    <div class="text-muted small mt-1">清空正式表后，重新同步校验通过的数据</div>
                                </div>
                            </div>
                            <div class="alert alert-warning small mb-0">
                                <i class="bi bi-exclamation-triangle"></i> 刷新同步将<strong>删除正式表所有数据</strong>，请谨慎操作！
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" id="confirmSyncBtn">开始同步</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modal = new bootstrap.Modal(document.getElementById('syncModeModal'));
        const confirmBtn = document.getElementById('confirmSyncBtn');
        
        confirmBtn.addEventListener('click', () => {
            const mode = document.querySelector('input[name="syncMode"]:checked').value;
            const targetDbs = Array.from(document.querySelectorAll('.target-db-checkbox:checked')).map(cb => cb.value);
            
            if (targetDbs.length === 0) {
                showMessage('请至少选择一个目标账套', 'warning');
                return;
            }
            
            modal.hide();
            resolve({ mode, targetDbs });
        });
        
        document.getElementById('syncModeModal').addEventListener('hidden.bs.modal', function() {
            this.remove();
            resolve({ mode: null, targetDbs: [] });
        }, { once: true });
        
        modal.show();
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
    const businessFields = Object.entries(row).filter(([key]) => !key.startsWith('_'));
    
    detailContent.innerHTML = `
        <table class="table table-sm table-bordered">
            <tbody>
                ${businessFields.map(([key, value]) => `
                    <tr>
                        <th style="width: 120px; background-color: #f8f9fa;">${FIELD_LABELS[key] || key}</th>
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

/**
 * 从行数据中获取错误字段列表
 * @param {Object} row - 行数据
 * @returns {Array} 错误字段名数组
 */
function getErrorFields(row) {
    const errorFields = [];
    if (!row._error_msg) return errorFields;
    
    try {
        let errorData = typeof row._error_msg === 'string' ? JSON.parse(row._error_msg) : row._error_msg;
        if (!Array.isArray(errorData)) {
            errorData = [errorData];
        }
        
        errorData.forEach(err => {
            if (err.error_field) {
                errorFields.push(err.error_field);
            }
        });
    } catch (e) {
        console.error('解析错误信息失败:', e);
    }
    
    return errorFields;
}

function generateEditField(col, row) {
    const fieldName = col.field;
    const fieldValue = row[fieldName] !== null && row[fieldName] !== undefined ? row[fieldName] : '';
    const isRequired = REQUIRED_FIELDS.includes(fieldName);
    
    // 获取错误字段列表（从 _error_msg 中解析）
    const errorFields = getErrorFields(row);
    const isErrorField = errorFields.includes(fieldName);
    const errorClass = isErrorField ? ' is-invalid' : '';
    
    // 水平布局：label 在左侧，加粗加黑，右对齐，靠近输入框
    const labelHtml = `
        <label class="col-form-label flex-shrink-0" style="font-weight: 700; color: #1a1a1a; text-align: right; padding-right: 8px; margin-bottom: 0; white-space: nowrap;">
            ${col.title}${isRequired ? '<span class="text-danger">*</span>' : ''}
        </label>
    `;
    
    if (ENUM_OPTIONS[fieldName]) {
        const options = ENUM_OPTIONS[fieldName];
        return `
            <div class="mb-2 row align-items-center justify-content-start" style="gap: 4px;">
                <div class="flex-shrink-0" style="min-width: 90px; max-width: 120px;">${labelHtml}</div>
                <div class="flex-grow-1" style="min-width: 0;">
                    <select class="form-select font-mono${errorClass}" name="${fieldName}" style="height: 31px; padding: 0.25rem 0.5rem; font-size: 0.8rem;" ${isRequired ? 'required' : ''}>
                        <option value="">-- 请选择 --</option>
                        ${options.map(opt => `
                            <option value="${opt.value}" ${String(fieldValue) === String(opt.value) ? 'selected' : ''}>
                                ${opt.label}
                            </option>
                        `).join('')}
                    </select>
                </div>
            </div>
        `;
    }
    
    return `
        <div class="mb-2 row align-items-center justify-content-start" style="gap: 4px;">
            <div class="flex-shrink-0" style="min-width: 90px; max-width: 120px;">${labelHtml}</div>
            <div class="flex-grow-1" style="min-width: 0;">
                <input type="text" class="form-control font-mono${errorClass}" name="${fieldName}" 
                       value="${escapeHtml(String(fieldValue))}"
                       style="height: 31px; padding: 0.25rem 0.5rem; font-size: 0.8rem;"
                       ${isRequired ? 'required' : ''}>
            </div>
        </div>
    `;
}

function showEditModal(row) {
    const modal = new bootstrap.Modal(document.getElementById('editModal'));
    
    const businessFields = TABLE_COLUMNS.filter(col => !col.field.startsWith('_'));
    const totalFields = businessFields.length;
    const halfCount = Math.ceil(totalFields / 2);
    
    const leftFields = businessFields.slice(0, halfCount);
    const rightFields = businessFields.slice(halfCount);
    
    const editForm = document.getElementById('editForm');
    editForm.innerHTML = `
        <div class="row">
            <div class="col-6">
                ${leftFields.map(col => generateEditField(col, row)).join('')}
            </div>
            <div class="col-6">
                ${rightFields.map(col => generateEditField(col, row)).join('')}
            </div>
        </div>
    `;
    
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) {
        saveBtn.onclick = () => saveRecord(row._staging_id);
    }
    
    modal.show();
}

async function saveRecord(stagingId) {
    const form = document.getElementById('editForm');
    
    const requiredFields = TABLE_COLUMNS.filter(col => REQUIRED_FIELDS.includes(col.field));
    for (const col of requiredFields) {
        const input = form.querySelector(`[name="${col.field}"]`);
        if (input && !input.value.trim()) {
            showMessage(`${col.title} 是必填字段`, 'warning');
            input.focus();
            return;
        }
    }
    
    const formData = new FormData(form);
    const data = {};
    
    formData.forEach((value, key) => {
        if (value === '') {
            data[key] = null;
        } else {
            data[key] = value;
        }
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

function bindAdvancedFilterEvents() {
    const filterConditions = document.getElementById('filterConditions');
    const addBtn = document.getElementById('addFilterCondition');
    const clearBtn = document.getElementById('clearAllFilters');
    const applyBtn = document.getElementById('applyAdvancedFilter');
    
    const stringFields = [
        { value: 'MaterialNo', label: '物料号' },
        { value: 'Description', label: '物料描述' },
        { value: 'Plant', label: '工厂' },
        { value: 'Planner', label: '计划员' },
        { value: 'Unit', label: '单位' }
    ];
    
    const numberFields = [
        { value: 'LeadDay', label: '提前期' },
        { value: 'ExpDay', label: '保质期' },
        { value: 'GRDay', label: '质检期' },
        { value: 'Price', label: '价格' },
        { value: 'PhantomMin', label: '虚拟时间' },
        { value: 'FirmDay', label: '固定天' },
        { value: 'DayGap', label: '拆分天' },
        { value: 'LotFix', label: '固定批' },
        { value: 'LotMin', label: '最小批' },
        { value: 'LotMax', label: '最大批' }
    ];
    
    const enumFields = [
        { value: 'ABC', label: 'ABC分类', options: ENUM_OPTIONS.abc },
        { value: 'Type', label: '类型', options: ENUM_OPTIONS.type },
        { value: 'Phantom', label: '虚拟件', options: ENUM_OPTIONS.phantom },
        { value: 'CanDelay', label: '可延迟', options: ENUM_OPTIONS.candelay },
        { value: 'LotSize', label: '批量策略', options: ENUM_OPTIONS.lotsize },
        { value: 'FIFO', label: 'FIFO', options: ENUM_OPTIONS.fifo }
    ];
    
    const allFields = [...stringFields, ...numberFields, ...enumFields];
    
    function getOperatorOptions(field) {
        const isNumber = numberFields.some(f => f.value === field);
        const isEnum = enumFields.some(f => f.value === field);
        
        if (isNumber) {
            return `
                <option value="eq">=</option>
                <option value="gt">></option>
                <option value="gte">>=</option>
                <option value="lt"><</option>
                <option value="lte"><=</option>
                <option value="null">为空</option>
                <option value="not_null">不为空</option>
            `;
        } else if (isEnum) {
            return `
                <option value="eq">等于</option>
                <option value="like">包含</option>
                <option value="not_like">不包含</option>
                <option value="null">为空</option>
                <option value="not_null">不为空</option>
            `;
        } else {
            return `
                <option value="eq">等于</option>
                <option value="ne">不等于</option>
                <option value="like">包含</option>
                <option value="not_like">不包含</option>
                <option value="starts">开头是</option>
                <option value="ends">结尾是</option>
                <option value="null">为空</option>
                <option value="not_null">不为空</option>
            `;
        }
    }
    
    function getValueInput(field, operator) {
        const isNumber = numberFields.some(f => f.value === field);
        const enumField = enumFields.find(f => f.value === field);
        
        if (operator === 'null' || operator === 'not_null') {
            return '<input type="text" class="form-control form-control-sm filter-value" disabled placeholder="无需输入">';
        }
        
        if (enumField) {
            const options = enumField.options || [];
            return `
                <select class="form-select form-select-sm filter-value">
                    <option value="">请选择</option>
                    ${options.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
                </select>
            `;
        }
        
        if (isNumber) {
            return '<input type="number" class="form-control form-control-sm filter-value" placeholder="请输入数值">';
        }
        
        return '<input type="text" class="form-control form-control-sm filter-value" placeholder="请输入">';
    }
    
    function createConditionRow(isFirst = false) {
        const row = document.createElement('div');
        row.className = 'filter-condition-row mb-2';
        row.innerHTML = `
            <div class="row g-2 align-items-center">
                <div class="col-auto">
                    <span class="text-muted small">${isFirst ? '当' : '且'}</span>
                </div>
                <div class="col-3">
                    <select class="form-select form-select-sm filter-field">
                        <option value="">选择字段</option>
                        <optgroup label="文本字段">
                            ${stringFields.map(f => `<option value="${f.value}">${f.label}</option>`).join('')}
                        </optgroup>
                        <optgroup label="数值字段">
                            ${numberFields.map(f => `<option value="${f.value}">${f.label}</option>`).join('')}
                        </optgroup>
                        <optgroup label="枚举字段">
                            ${enumFields.map(f => `<option value="${f.value}">${f.label}</option>`).join('')}
                        </optgroup>
                    </select>
                </div>
                <div class="col-2">
                    <select class="form-select form-select-sm filter-operator">
                        <option value="">请选择</option>
                    </select>
                </div>
                <div class="col-4 filter-value-container">
                    <input type="text" class="form-control form-control-sm filter-value" disabled placeholder="请先选择字段">
                </div>
                <div class="col-auto">
                    <button type="button" class="btn btn-outline-danger btn-sm remove-condition-btn">×</button>
                </div>
            </div>
        `;
        
        const fieldSelect = row.querySelector('.filter-field');
        const operatorSelect = row.querySelector('.filter-operator');
        const valueContainer = row.querySelector('.filter-value-container');
        
        fieldSelect.addEventListener('change', () => {
            const field = fieldSelect.value;
            operatorSelect.innerHTML = getOperatorOptions(field);
            valueContainer.innerHTML = getValueInput(field, operatorSelect.value);
        });
        
        operatorSelect.addEventListener('change', () => {
            const field = fieldSelect.value;
            const operator = operatorSelect.value;
            valueContainer.innerHTML = getValueInput(field, operator);
        });
        
        return row;
    }
    
    const firstRow = filterConditions.querySelector('.filter-condition-row');
    if (firstRow) {
        firstRow.replaceWith(createConditionRow(true));
    }
    
    if (addBtn) {
        addBtn.addEventListener('click', () => {
            const newRow = createConditionRow(false);
            filterConditions.appendChild(newRow);
        });
    }
    
    filterConditions.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-condition-btn')) {
            const row = e.target.closest('.filter-condition-row');
            if (row && filterConditions.children.length > 1) {
                row.remove();
            }
        }
    });
    
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            filterConditions.innerHTML = '';
            filterConditions.appendChild(createConditionRow(true));
        });
    }
    
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            const conditions = [];
            filterConditions.querySelectorAll('.filter-condition-row').forEach(row => {
                const field = row.querySelector('.filter-field').value;
                const operator = row.querySelector('.filter-operator').value;
                const valueEl = row.querySelector('.filter-value');
                const value = valueEl ? valueEl.value.trim() : '';
                
                if (field && operator) {
                    if (operator === 'null' || operator === 'not_null') {
                        conditions.push({ field, operator, value: '' });
                    } else if (value) {
                        conditions.push({ field, operator, value });
                    }
                }
            });
            
            if (conditions.length > 0) {
                dataTable.advancedFilters = conditions;
                dataTable.selectedIds.clear();
                const selectAll = document.getElementById('selectAll');
                if (selectAll) selectAll.checked = false;
                dataTable.updateSelectedCount();
                dataTable.loadData();
                bootstrap.Modal.getInstance(document.getElementById('advancedFilterModal')).hide();
            } else {
                showMessage('请至少设置一个有效的筛选条件', 'warning');
            }
        });
    }
}

function bindBatchEditEvents() {
    const batchEditBtn = document.getElementById('batchEditBtn');
    const showFieldSelectBtn = document.getElementById('showFieldSelectBtn');
    const fieldSelectPanel = document.getElementById('fieldSelectPanel');
    const fieldSearchInput = document.getElementById('fieldSearchInput');
    const fieldCheckboxList = document.getElementById('fieldCheckboxList');
    const batchEditFields = document.getElementById('batchEditFields');
    const applyBatchEditBtn = document.getElementById('applyBatchEdit');
    
    const editableFields = TABLE_COLUMNS.filter(col => !col.field.startsWith('_') && col.field !== 'materialno');
    
    let fieldValues = {};
    let nullFields = new Set();
    
    function renderFieldCheckboxes(searchText = '') {
        const filtered = editableFields.filter(f => 
            f.title.toLowerCase().includes(searchText.toLowerCase())
        );
        
        fieldCheckboxList.innerHTML = filtered.map(f => `
            <div class="form-check">
                <input class="form-check-input field-checkbox" type="checkbox" value="${f.field}" id="cb_${f.field}">
                <label class="form-check-label" for="cb_${f.field}">${f.title}</label>
            </div>
        `).join('');
        
        fieldCheckboxList.querySelectorAll('.field-checkbox').forEach(cb => {
            if (fieldValues[cb.value] !== undefined || nullFields.has(cb.value)) {
                cb.checked = true;
            }
            
            cb.addEventListener('change', () => {
                renderBatchEditFields();
            });
        });
    }
    
    function renderBatchEditFields() {
        const selectedFields = Array.from(fieldCheckboxList.querySelectorAll('.field-checkbox:checked'))
            .map(cb => cb.value);
        
        batchEditFields.innerHTML = selectedFields.map(field => {
            const col = editableFields.find(c => c.field === field);
            const enumOptions = ENUM_OPTIONS[field];
            const isNull = nullFields.has(field);
            const savedValue = fieldValues[field] || '';
            
            let inputHtml;
            if (enumOptions) {
                inputHtml = `
                    <select class="form-select form-select-sm batch-edit-value" data-field="${field}" ${isNull ? 'disabled' : ''}>
                        <option value="">请选择</option>
                        ${enumOptions.map(o => `<option value="${o.value}" ${savedValue === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                    </select>
                `;
            } else {
                inputHtml = `<input type="text" class="form-control form-control-sm batch-edit-value" data-field="${field}" value="${savedValue}" placeholder="输入新值" ${isNull ? 'disabled' : ''}>`;
            }
            
            const clearBtnClass = isNull ? 'btn-danger' : 'btn-outline-danger';
            const clearBtnText = isNull ? '已清空(点击恢复)' : '清空';
            
            return `
                <div class="row g-2 mb-2 align-items-center">
                    <div class="col-3">
                        <label class="form-label mb-0">${col.title}</label>
                    </div>
                    <div class="col-6">
                        ${inputHtml}
                    </div>
                    <div class="col-auto">
                        <button type="button" class="btn ${clearBtnClass} btn-sm clear-field-btn" data-field="${field}">${clearBtnText}</button>
                    </div>
                </div>
            `;
        }).join('');
        
        batchEditFields.querySelectorAll('.batch-edit-value').forEach(input => {
            input.addEventListener('input', (e) => {
                const field = e.target.dataset.field;
                fieldValues[field] = e.target.value;
            });
            
            input.addEventListener('change', (e) => {
                const field = e.target.dataset.field;
                fieldValues[field] = e.target.value;
            });
        });
        
        batchEditFields.querySelectorAll('.clear-field-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const field = btn.dataset.field;
                
                if (nullFields.has(field)) {
                    nullFields.delete(field);
                    delete fieldValues[field];
                } else {
                    if (REQUIRED_FIELDS.includes(field)) {
                        showMessage(`${FIELD_LABELS[field] || field} 是必填字段，不能清空`, 'warning');
                        return;
                    }
                    nullFields.add(field);
                    delete fieldValues[field];
                }
                
                renderBatchEditFields();
            });
        });
    }
    
    if (showFieldSelectBtn) {
        showFieldSelectBtn.addEventListener('click', () => {
            const isVisible = fieldSelectPanel.style.display !== 'none';
            fieldSelectPanel.style.display = isVisible ? 'none' : 'block';
            if (!isVisible) {
                renderFieldCheckboxes();
                renderBatchEditFields();
            }
        });
    }
    
    if (fieldSearchInput) {
        fieldSearchInput.addEventListener('input', (e) => {
            renderFieldCheckboxes(e.target.value);
        });
    }
    
    if (batchEditBtn) {
        batchEditBtn.addEventListener('click', () => {
            if (dataTable.selectedIds.size === 0) {
                showMessage('请先选择要编辑的记录', 'warning');
                return;
            }
            
            fieldValues = {};
            nullFields = new Set();
            fieldSelectPanel.style.display = 'none';
            fieldCheckboxList.innerHTML = '';
            batchEditFields.innerHTML = '';
            
            const modal = new bootstrap.Modal(document.getElementById('batchEditModal'));
            modal.show();
        });
    }
    
    if (applyBatchEditBtn) {
        applyBatchEditBtn.addEventListener('click', async () => {
            const updates = {};
            
            batchEditFields.querySelectorAll('.batch-edit-value').forEach(input => {
                const field = input.dataset.field;
                const value = input.value.trim();
                if (value) {
                    updates[field] = value;
                }
            });
            
            nullFields.forEach(field => {
                updates[field] = null;
            });
            
            if (Object.keys(updates).length === 0) {
                showMessage('请至少修改一个字段', 'warning');
                return;
            }
            
            const ids = Array.from(dataTable.selectedIds);
            
            showLoading();
            
            const response = await callApi(`/batch_update/${TABLE_NAME}`, 'POST', {
                ids: ids,
                updates: updates
            });
            
            hideLoading();
            
            handleResponse(response, () => {
                showMessage(`成功更新 ${ids.length} 条记录`, 'success');
                bootstrap.Modal.getInstance(document.getElementById('batchEditModal')).hide();
                dataTable.selectedIds.clear();
                dataTable.loadData();
                statusCard.refresh();
            });
        });
    }
}

document.addEventListener('DOMContentLoaded', initPage);
