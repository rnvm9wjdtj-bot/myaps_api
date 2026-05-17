/**
 * MDS 页面控制器 - 公共模块
 * 提供通用的页面管理逻辑，所有表共用
 */
class MDSPageController {
    constructor(config) {
        this.config = config;
        this.tableKey = config.tableKey;
        this.tableDisplayName = config.tableDisplayName;
        
        this.tableMeta = null;
        this.dataTable = null;
        this.statusCard = null;
        
        this.fieldValues = {};
        this.nullFields = new Set();
        this.pendingFile = null;
        
        this.init();
    }
    
    async init() {
        try {
            await this.loadTableMeta();
            this.initStatusCard();
            this.initDataTable();
            this.bindEvents();
        } catch (error) {
            console.error('页面初始化失败:', error);
            showMessage('页面初始化失败', 'danger');
        }
    }
    
    async loadTableMeta() {
        const response = await callApi(`/rules/${this.tableKey}`);
        if (response.success === 1) {
            this.tableMeta = response.data;
        }
    }
    
    getFieldLabel(fieldName) {
        if (this.tableMeta?.fields) {
            const field = this.tableMeta.fields.find(f => f.field === fieldName);
            if (field) return field.title;
        }
        
        if (this.config?.display?.columns) {
            const col = this.config.display.columns.find(c => c.field === fieldName);
            if (col) return col.title;
        }
        
        return fieldName;
    }
    
    getFieldType(fieldName) {
        if (this.tableMeta?.fields) {
            const field = this.tableMeta.fields.find(f => f.field === fieldName);
            if (field) return field.data_type;
        }
        return 'string';
    }
    
    getEnumOptions(fieldName) {
        if (this.tableMeta?.fields) {
            const field = this.tableMeta.fields.find(f => f.field === fieldName);
            if (field && field.enum_options) {
                return field.enum_options;
            }
        }
        return [];
    }
    
    isRequiredField(fieldName) {
        if (this.tableMeta?.fields) {
            const field = this.tableMeta.fields.find(f => f.field === fieldName);
            if (field) return field.is_required;
        }
        return false;
    }
    
    getRequiredFields() {
        if (this.tableMeta?.fields) {
            return this.tableMeta.fields.filter(f => f.is_required).map(f => f.field);
        }
        return [];
    }
    
    isReadOnlyField(fieldName) {
        if (this.config?.display?.columns) {
            const col = this.config.display.columns.find(c => c.field === fieldName);
            if (col && col.readOnly !== undefined) {
                return col.readOnly;
            }
        }
        return false;
    }

    getEditableFields() {
        let fields = [];
        
        if (this.config?.display?.columns) {
            fields = this.config.display.columns.filter(
                col => !col.field.startsWith('_') && !this.isReadOnlyField(col.field)
            );
        } else if (this.tableMeta?.fields) {
            fields = this.tableMeta.fields.filter(f => !f.is_internal);
        }
        
        return fields;
    }
    
    getColumns() {
        if (this.config?.display?.columns) {
            return this.config.display.columns;
        }
        
        if (this.tableMeta?.fields) {
            return this.tableMeta.fields.map(f => ({
                field: f.field,
                title: f.title
            }));
        }
        
        return [];
    }
    
    getEnumFieldKeys() {
        if (this.tableMeta?.fields) {
            return this.tableMeta.fields
                .filter(f => f.data_type === 'enum' && f.enum_options)
                .map(f => f.field);
        }
        return [];
    }
    
    initStatusCard() {
        this.statusCard = new StatusCard({
            tableName: this.tableKey,
            container: document.getElementById('statusCardContainer'),
            onStatusClick: (status) => {
                this.dataTable.setFilter('_status', status);
            }
        });
    }
    
    initDataTable() {
        // 准备枚举选项
        const enumOptions = {};
        const enumFieldKeys = this.getEnumFieldKeys();
        enumFieldKeys.forEach(fieldName => {
            enumOptions[fieldName] = this.getEnumOptions(fieldName);
        });
        
        this.dataTable = new DataTable({
            tableName: this.tableKey,
            columns: this.getColumns(),
            container: document.getElementById('tableContainer'),
            pageSize: 100,
            onRowClick: (row) => this.showEditModal(row),
            enumFields: enumFieldKeys,
            enumOptions: enumOptions,
            foreignKeys: this.config.foreignKeys || []
        });
        
        this.dataTable.loadData();
    }
    
    bindEvents() {
        this.bindFilterEvents();
        this.bindActionEvents();
        this.bindUploadEvents();
        this.bindAdvancedFilterEvents();
        this.bindBatchEditEvents();
    }
    
    bindFilterEvents() {
        const statusFilter = document.getElementById('statusFilter');
        const sourceFilter = document.getElementById('sourceFilter');
        const keywordInput = document.getElementById('keywordInput');
        const searchBtn = document.getElementById('searchBtn');
        const resetBtn = document.getElementById('resetBtn');
        
        if (statusFilter) {
            statusFilter.addEventListener('change', (e) => {
                this.dataTable.setFilter('_status', e.target.value);
            });
        }
        
        if (sourceFilter) {
            sourceFilter.addEventListener('change', (e) => {
                this.dataTable.setFilter('source_system', e.target.value);
            });
        }
        
        if (searchBtn && keywordInput) {
            searchBtn.addEventListener('click', () => {
                this.dataTable.setFilter('keyword', keywordInput.value.trim());
            });
            
            keywordInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.dataTable.setFilter('keyword', keywordInput.value.trim());
                }
            });
        }
        
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                if (statusFilter) statusFilter.value = '';
                if (sourceFilter) sourceFilter.value = '';
                if (keywordInput) keywordInput.value = '';
                this.statusCard.setActiveStatus(null);
                this.dataTable.filters = {};
                this.dataTable.advancedFilters = null;
                this.dataTable.loadData();
            });
        }
    }
    
    bindActionEvents() {
        const validateBtn = document.getElementById('validateBtn');
        const validateAllBtn = document.getElementById('validateAllBtn');
        const syncBtn = document.getElementById('syncBtn');
        const syncAllBtn = document.getElementById('syncAllBtn');
        const rulesBtn = document.getElementById('rulesBtn');
        const downloadTemplateBtn = document.getElementById('downloadTemplateBtn');
        
        if (validateBtn) {
            validateBtn.addEventListener('click', () => this.validateData());
        }
        
        if (validateAllBtn) {
            validateAllBtn.addEventListener('click', () => this.validateAllData());
        }
        
        if (syncBtn) {
            syncBtn.addEventListener('click', () => this.syncData());
        }
        
        if (syncAllBtn) {
            syncAllBtn.addEventListener('click', () => this.syncAllData());
        }
        
        if (rulesBtn) {
            rulesBtn.addEventListener('click', () => {
                showValidationRulesModal(this.tableKey, this.tableDisplayName);
            });
        }
    }
    
    bindUploadEvents() {
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        
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
                    this.setPendingFile(files[0]);
                }
            });
            
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.setPendingFile(e.target.files[0]);
                }
            });
        }
        
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                this.uploadPendingFile();
            });
        }
    }
    
    setPendingFile(file) {
        if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
            showMessage('请上传Excel或CSV文件', 'warning');
            return;
        }
        
        this.pendingFile = file;
        
        const uploadArea = document.getElementById('uploadArea');
        if (uploadArea) {
            const sizeKB = (file.size / 1024).toFixed(1);
            const sizeMB = (file.size / 1024 / 1024).toFixed(2);
            const sizeDisplay = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;
            uploadArea.innerHTML = `
                <i class="bi bi-file-earmark-spreadsheet fs-1 text-primary mb-2"></i>
                <p class="mb-0 text-primary fw-bold">${file.name}</p>
                <p class="mb-0 text-muted small">${sizeDisplay}</p>
            `;
        }
    }
    
    async uploadPendingFile() {
        if (!this.pendingFile) {
            showMessage('请先选择文件', 'warning');
            return;
        }
        
        await this.handleFileUpload(this.pendingFile);
    }
    
    getDedupStrategy() {
        const radio = document.querySelector('input[name="dedupStrategy"]:checked');
        return radio ? radio.value : 'overwrite';
    }
    
    async handleFileUpload(file) {
        if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
            showMessage('请上传Excel或CSV文件', 'warning');
            return;
        }
        
        const strategy = this.getDedupStrategy();
        
        // 禁用上传按钮，防止重复提交
        const uploadBtn = document.getElementById('uploadBtn');
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 上传中...';
        }
        
        showLoading();
        
        try {
            const response = await uploadFile(this.tableKey, file, strategy);
            
            hideLoading();
            
            handleResponse(response, (data) => {
                const result = data.data;
                showMessage(`导入完成: 成功${result.inserted}条, 跳过${result.skipped}条`, 'success');
                
                this.resetUploadArea();
                this.pendingFile = null;
                
                const uploadModal = bootstrap.Modal.getInstance(document.getElementById('uploadModal'));
                if (uploadModal) uploadModal.hide();
                
                this.dataTable.refresh();
                this.statusCard.refresh();
            });
        } catch (error) {
            hideLoading();
            showMessage('上传失败', 'danger');
        } finally {
            // 恢复上传按钮
            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = '上传';
            }
        }
    }
    
    resetUploadArea() {
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        
        if (fileInput) fileInput.value = '';
        
        if (uploadArea) {
            uploadArea.innerHTML = `
                <p class="mb-0">点击或拖拽文件上传（支持 .xlsx, .xls, .csv）</p>
                <input type="file" id="fileInput" accept=".xlsx,.xls,.csv" style="display: none;">
            `;
            
            const newFileInput = document.getElementById('fileInput');
            if (newFileInput) {
                newFileInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) {
                        this.setPendingFile(e.target.files[0]);
                    }
                });
            }
        }
    }
    
    async validateData() {
        const pendingCount = await this.getPendingCount();
        if (pendingCount === 0) {
            showMessage('没有待处理的记录', 'warning');
            return;
        }
        
        showProgress('校验中', pendingCount);
        
        let totalValidated = 0;
        let totalRejected = 0;
        let totalFilled = 0;
        let processed = 0;
        
        while (true) {
            setProgressIndeterminate(true);
            
            const response = await callApi(`/validate/${this.tableKey}?batch_size=200`, 'POST');
            
            setProgressIndeterminate(false);
            
            if (response.success !== 1) {
                hideProgress();
                showMessage(response.message || '校验失败', 'danger');
                break;
            }
            
            const stats = response.data;
            const batchValidated = stats.relation_pass || 0;
            const batchRejected = (stats.relation_error || 0) + (stats.compliance_error || 0);
            const batchProcessed = batchValidated + batchRejected;
            
            totalValidated += batchValidated;
            totalRejected += batchRejected;
            totalFilled += stats.filled || 0;
            
            if (batchProcessed > 0) {
                await this.animateProgress(processed, processed + batchProcessed, pendingCount, `已处理 ${processed + batchProcessed}/${pendingCount}`);
                processed += batchProcessed;
            }
            
            if (batchProcessed === 0) {
                break;
            }
            
            await this.sleep(50);
        }
        
        hideProgress();
        
        const filledMsg = totalFilled ? `，填充默认值${totalFilled}条` : '';
        showMessage(`校验完成: 通过${totalValidated}条，失败${totalRejected}条${filledMsg}`, 'success');
        this.dataTable.refresh();
        this.statusCard.refresh();
    }
    
    async animateProgress(from, to, total, text) {
        const steps = 10;
        const stepSize = (to - from) / steps;
        
        for (let i = 1; i <= steps; i++) {
            const current = Math.round(from + stepSize * i);
            updateProgress(current, total, text);
            await this.sleep(30);
        }
    }
    
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    async getPendingCount() {
        const response = await callApi(`/status/${this.tableKey}`);
        if (response.success === 1) {
            return response.data.pending || 0;
        }
        return 0;
    }
    
    async validateAllData() {
        if (!confirm('确定要校验所有待处理数据吗？')) return;
        
        showProgress('校验所有表', 100);
        
        const response = await callApi('/validate_all', 'POST');
        
        hideProgress();
        
        handleResponse(response, (data) => {
            showMessage('所有表校验完成', 'success');
            this.dataTable.refresh();
            this.statusCard.refresh();
        });
    }
    
    async syncData() {
        const response = await callApi(`/status/${this.tableKey}`);
        if (response.success !== 1) {
            showMessage('获取状态失败', 'danger');
            return;
        }
        
        const stats = response.data;
        const relationPassCount = stats.relation_pass || 0;
        const syncErrorCount = stats.sync_error || 0;
        const retryExceeded = stats.retry_exceeded || 0;
        
        if (relationPassCount === 0 && syncErrorCount === 0) {
            showMessage('没有【联合校验通过】或【同步失败】的记录可推送', 'warning');
            return;
        }
        
        let resetRetry = false;
        if (retryExceeded > 0) {
            resetRetry = confirm(`有${retryExceeded}条记录的重试次数已达上限，是否重置重试次数后推送？\n\n点击"确定"重置并推送，点击"取消"跳过这些记录`);
        }
        
        const { mode, targetDbs } = await this.showSyncModeDialog(relationPassCount, syncErrorCount);
        if (!mode || !targetDbs || targetDbs.length === 0) return;
        
        const targetDbParam = targetDbs.join(',');
        const totalCount = (relationPassCount + syncErrorCount) * targetDbs.length;
        
        showProgress(mode === 'incremental' ? '增量推送中' : '刷新推送中', totalCount);
        
        let totalSynced = 0;
        let totalFailed = 0;
        let totalDedup = 0;
        let processed = 0;
        
        const baseUrl = `/sync/${this.tableKey}?batch_size=200&mode=${mode}&target_dbs=${encodeURIComponent(targetDbParam)}&reset_retry=${resetRetry}`;
        
        // 统一使用循环处理，支持大批量数据
        let firstCall = true;
        while (true) {
            setProgressIndeterminate(true);
            let url = baseUrl;
            if (!firstCall && mode === 'refresh') {
                // 刷新模式后续调用：跳过 truncate
                url = `/sync/${this.tableKey}?batch_size=200&mode=${mode}&target_dbs=${encodeURIComponent(targetDbParam)}&skip_truncate=true`;
            }
            const syncResponse = await callApi(url, 'POST');
            setProgressIndeterminate(false);
            firstCall = false;
            
            if (syncResponse.success !== 1) {
                hideProgress();
                showMessage(syncResponse.message || '推送失败', 'danger');
                break;
            }
            
            const syncStats = syncResponse.data;
            const batchSynced = syncStats.total_synced || 0;
            const batchFailed = syncStats.total_failed || 0;
            const batchDedup = syncStats.total_dedup || 0;
            
            totalSynced += batchSynced;
            totalFailed += batchFailed;
            totalDedup += batchDedup;
            processed += batchSynced + batchFailed + batchDedup;
            
            if (processed > 0) {
                updateProgress(processed, totalCount, `已处理 ${processed}/${totalCount}`);
            }
            
            // 如果本批次没有处理任何记录，说明已完成
            if (batchSynced === 0 && batchFailed === 0 && batchDedup === 0) {
                break;
            }
            
            await this.sleep(50);
        }
        
        hideProgress();
        
        if (totalFailed > 0 || totalDedup > 0) {
            showMessage(`推送完成: ${targetDbs.length}个账套, 成功${totalSynced}条, 去重失败${totalDedup}条, 其他失败${totalFailed}条`, 'warning');
        } else {
            showMessage(`推送完成: ${targetDbs.length}个账套, 成功${totalSynced}条`, 'success');
        }
        
        this.dataTable.refresh();
        this.statusCard.refresh();
    }
    
    async showSyncModeDialog(relationPassCount, syncErrorCount) {
        const dbListResponse = await callApi('/dblist');
        const dbList = dbListResponse.success === 1 ? dbListResponse.data : [];
        
        const totalCount = relationPassCount + syncErrorCount;
        const hasSyncError = syncErrorCount > 0;
        
        return new Promise((resolve) => {
            const modalHtml = `
                <div class="modal fade" id="syncModeModal" tabindex="-1">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">选择推送模式</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                ${hasSyncError ? `
                                <div class="alert alert-info small mb-3">
                                    <i class="bi bi-info-circle"></i> 
                                    将推送 <strong>${relationPassCount}</strong> 条【联合校验通过】+ <strong>${syncErrorCount}</strong> 条【同步失败】的记录
                                </div>
                                ` : ''}
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
                                    <div class="form-text">默认全选，可取消勾选排除不需要推送的账套</div>
                                </div>
                                <hr>
                                <div class="mb-3">
                                    <label class="form-label fw-bold">推送模式</label>
                                    <div class="form-check">
                                        <input class="form-check-input" type="radio" name="syncMode" id="modeIncremental" value="incremental" checked>
                                        <label class="form-check-label" for="modeIncremental">
                                            <strong>增量推送</strong> <span class="badge bg-primary">${totalCount}条</span>
                                        </label>
                                        <div class="text-muted small mt-1">仅推送校验通过的新数据，保留正式表现有数据</div>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <div class="form-check">
                                        <input class="form-check-input" type="radio" name="syncMode" id="modeRefresh" value="refresh">
                                        <label class="form-check-label" for="modeRefresh">
                                            <strong>刷新推送</strong> <span class="badge bg-warning text-dark">${totalCount}条</span>
                                        </label>
                                        <div class="text-muted small mt-1">清空正式表后，重新推送校验通过的数据</div>
                                    </div>
                                </div>
                                <div class="alert alert-warning small mb-0">
                                    <i class="bi bi-exclamation-triangle"></i> 刷新推送将<strong>删除正式表所有数据</strong>，请谨慎操作！
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                                <button type="button" class="btn btn-primary" id="confirmSyncBtn">开始推送</button>
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
    
    async syncAllData() {
        if (!confirm('确定要推送所有校验通过的数据吗？')) return;
        
        showLoading();
        
        const response = await callApi('/sync_all', 'POST');
        
        hideLoading();
        
        handleResponse(response, (data) => {
            showMessage('所有表推送完成', 'success');
            this.dataTable.refresh();
            this.statusCard.refresh();
        });
    }
    
    getErrorFields(row) {
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
    
    formatDetailValue(key, value) {
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
    
    showErrorDetail(errorMsg) {
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
    
    generateEditField(col, row) {
        const fieldName = col.field;
        const fieldValue = row[fieldName] !== null && row[fieldName] !== undefined ? row[fieldName] : '';
        const isRequired = this.isRequiredField(fieldName);
        const isReadOnly = this.isReadOnlyField(fieldName);
        
        const errorFields = this.getErrorFields(row);
        const isErrorField = errorFields.includes(fieldName);
        const errorClass = isErrorField ? ' is-invalid' : '';
        
        const labelHtml = `
            <label class="col-form-label flex-shrink-0" style="font-weight: 700; color: #1a1a1a; text-align: right; padding-right: 8px; margin-bottom: 0; white-space: nowrap;">
                ${col.title}${isRequired ? '<span class="text-danger">*</span>' : ''}
                ${isReadOnly ? '<span class="text-muted ms-1"><i class="bi bi-lock"></i></span>' : ''}
            </label>
        `;
        
        if (isReadOnly) {
            return `
                <div class="mb-2 row align-items-center justify-content-start" style="gap: 4px;">
                    <div class="flex-shrink-0" style="min-width: 90px; max-width: 120px;">${labelHtml}</div>
                    <div class="flex-grow-1" style="min-width: 0;">
                        <div class="form-control-plaintext font-mono" style="height: 31px; padding: 0.25rem 0.5rem; font-size: 0.8rem;">
                            ${fieldValue === null || fieldValue === undefined ? '<span class="text-muted">-</span>' : escapeHtml(String(fieldValue))}
                        </div>
                    </div>
                </div>
            `;
        }
        
        const enumOptions = this.getEnumOptions(fieldName);
        if (enumOptions.length > 0) {
            return `
                <div class="mb-2 row align-items-center justify-content-start" style="gap: 4px;">
                    <div class="flex-shrink-0" style="min-width: 90px; max-width: 120px;">${labelHtml}</div>
                    <div class="flex-grow-1" style="min-width: 0;">
                        <select class="form-select font-mono${errorClass}" name="${fieldName}" style="height: 31px; padding: 0.25rem 0.5rem; font-size: 0.8rem;" ${isRequired ? 'required' : ''}>
                            <option value="">-- 请选择 --</option>
                            ${enumOptions.map(opt => `
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
    
    showEditModal(row) {
        const modal = new bootstrap.Modal(document.getElementById('editModal'));
        
        const columns = this.getColumns();
        const businessFields = columns.filter(col => !col.field.startsWith('_'));
        const totalFields = businessFields.length;
        const halfCount = Math.ceil(totalFields / 2);
        
        const leftFields = businessFields.slice(0, halfCount);
        const rightFields = businessFields.slice(halfCount);
        
        const editForm = document.getElementById('editForm');
        editForm.innerHTML = `
            <div class="row">
                <div class="col-6">
                    ${leftFields.map(col => this.generateEditField(col, row)).join('')}
                </div>
                <div class="col-6">
                    ${rightFields.map(col => this.generateEditField(col, row)).join('')}
                </div>
            </div>
        `;
        
        const saveBtn = document.getElementById('saveBtn');
        if (saveBtn) {
            saveBtn.onclick = () => this.saveRecord(row._staging_id);
        }
        
        const detailModal = document.getElementById('detailModal');
        if (detailModal && bootstrap.Modal.getInstance(detailModal)) {
            bootstrap.Modal.getInstance(detailModal).hide();
        }
        
        modal.show();
    }
    
    async saveRecord(stagingId) {
        const form = document.getElementById('editForm');
        const columns = this.getColumns();
        
        const requiredFields = this.getRequiredFields();
        for (const fieldName of requiredFields) {
            if (this.isReadOnlyField(fieldName)) continue;
            const col = columns.find(c => c.field === fieldName);
            const input = form.querySelector(`[name="${fieldName}"]`);
            if (input && !input.value.trim()) {
                showMessage(`${col?.title || fieldName} 是必填字段`, 'warning');
                input.focus();
                return;
            }
        }
        
        const formData = new FormData(form);
        const data = {};
        
        formData.forEach((value, key) => {
            if (this.isReadOnlyField(key)) return;
            if (value === '') {
                data[key] = null;
            } else {
                data[key] = value;
            }
        });
        
        showLoading();
        
        const response = await callApi(`/update/${this.tableKey}/${stagingId}`, 'PATCH', data);
        
        hideLoading();
        
        handleResponse(response, () => {
            showMessage('保存成功', 'success');
            bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
            this.dataTable.refresh();
        });
    }
    
    async deleteRecord(stagingId) {
        if (!confirm('确定删除此记录吗？')) return;
        
        showLoading();
        
        const response = await callApi(`/delete/${this.tableKey}/${stagingId}`, 'DELETE');
        
        hideLoading();
        
        handleResponse(response, () => {
            showMessage('删除成功', 'success');
            
            const detailModal = document.getElementById('detailModal');
            if (detailModal && bootstrap.Modal.getInstance(detailModal)) {
                bootstrap.Modal.getInstance(detailModal).hide();
            }
            
            const editModal = document.getElementById('editModal');
            if (editModal && bootstrap.Modal.getInstance(editModal)) {
                bootstrap.Modal.getInstance(editModal).hide();
            }
            
            this.dataTable.refresh();
            this.statusCard.refresh();
        });
    }
    
    bindAdvancedFilterEvents() {
        const filterConditions = document.getElementById('filterConditions');
        const addBtn = document.getElementById('addFilterCondition');
        const clearBtn = document.getElementById('clearAllFilters');
        const applyBtn = document.getElementById('applyAdvancedFilter');
        
        if (!filterConditions) return;
        
        const { stringFields, numberFields, enumFields } = this.getAdvancedFilterFieldGroups();
        const allFields = [...stringFields, ...numberFields, ...enumFields];
        
        const getOperatorOptions = (field) => {
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
        };
        
        const getValueInput = (field, operator) => {
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
        };
        
        const createConditionRow = (isFirst = false) => {
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
        };
        
        const firstRow = filterConditions.querySelector('.filter-condition-row');
        if (firstRow) {
            firstRow.replaceWith(createConditionRow(true));
        } else {
            filterConditions.appendChild(createConditionRow(true));
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
                this.dataTable.advancedFilters = null;
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
                    this.dataTable.advancedFilters = conditions;
                    this.dataTable.selectedIds.clear();
                    const selectAll = document.getElementById('selectAll');
                    if (selectAll) selectAll.checked = false;
                    this.dataTable.updateSelectedCount();
                    this.dataTable.loadData();
                    bootstrap.Modal.getInstance(document.getElementById('advancedFilterModal')).hide();
                } else {
                    showMessage('请至少设置一个有效的筛选条件', 'warning');
                }
            });
        }
    }
    
    getAdvancedFilterFieldGroups() {
        const configGroups = this.config?.display?.advancedFilterCategories;
        
        if (configGroups) {
            return configGroups;
        }
        
        const stringFields = [];
        const numberFields = [];
        const enumFields = [];
        
        if (this.tableMeta?.fields) {
            this.tableMeta.fields.forEach(field => {
                if (field.is_internal) return;
                
                const fieldItem = {
                    value: field.field,
                    label: field.title
                };
                
                if (field.data_type === 'enum' && field.enum_options) {
                    fieldItem.options = field.enum_options;
                    enumFields.push(fieldItem);
                } else if (field.data_type === 'number') {
                    numberFields.push(fieldItem);
                } else {
                    stringFields.push(fieldItem);
                }
            });
        }
        
        return { stringFields, numberFields, enumFields };
    }
    
    bindBatchEditEvents() {
        const batchEditBtn = document.getElementById('batchEditBtn');
        const showFieldSelectBtn = document.getElementById('showFieldSelectBtn');
        const fieldSelectPanel = document.getElementById('fieldSelectPanel');
        const fieldSearchInput = document.getElementById('fieldSearchInput');
        const fieldCheckboxList = document.getElementById('fieldCheckboxList');
        const batchEditFields = document.getElementById('batchEditFields');
        const applyBatchEditBtn = document.getElementById('applyBatchEdit');
        
        const editableFields = this.getEditableFields();
        
        const renderFieldCheckboxes = (searchText = '') => {
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
                if (this.fieldValues[cb.field] !== undefined || this.nullFields.has(cb.field)) {
                    cb.checked = true;
                }
                
                cb.addEventListener('change', () => {
                    this.renderBatchEditFields(editableFields);
                });
            });
        };
        
        const renderBatchEditFields = (fields) => {
            const selectedFields = Array.from(fieldCheckboxList.querySelectorAll('.field-checkbox:checked'))
                .map(cb => c.value);
            
            batchEditFields.innerHTML = selectedFields.map(field => {
                const col = fields.find(f => f.field === field);
                const enumOptions = this.getEnumOptions(field);
                const isNull = this.nullFields.has(field);
                const savedValue = this.fieldValues[field] || '';
                
                let inputHtml;
                if (enumOptions.length > 0) {
                    inputHtml = `
                        <select class="form-select form-select-sm batch-edit-value" data-field="${field}" ${isNull ? 'disabled' : ''}>
                            <option value="">请选择</option>
                            ${enumOptions.map(opt => `<option value="${opt.value}" ${savedValue === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
                        </select>
                    `;
                } else {
                    inputHtml = `<input type="text" class="form-control form-control-sm batch-edit-value" data-field="${field}" value="${escapeHtml(savedValue)}" placeholder="输入新值" ${isNull ? 'disabled' : ''}>`;
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
                    this.fieldValues[field] = e.target.value;
                });
                
                input.addEventListener('change', (e) => {
                    const field = e.target.dataset.field;
                    this.fieldValues[field] = e.target.value;
                });
            });
            
            batchEditFields.querySelectorAll('.clear-field-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const field = btn.dataset.field;
                    
                    if (this.nullFields.has(field)) {
                        this.nullFields.delete(field);
                        delete this.fieldValues[field];
                    } else {
                        if (this.isRequiredField(field)) {
                            showMessage(`${this.getFieldLabel(field)} 是必填字段，不能清空`, 'warning');
                            return;
                        }
                        this.nullFields.add(field);
                        delete this.fieldValues[field];
                    }
                    
                    this.renderBatchEditFields(editableFields);
                });
            });
        };
        
        if (showFieldSelectBtn) {
            showFieldSelectBtn.addEventListener('click', () => {
                const isVisible = fieldSelectPanel.style.display !== 'none';
                fieldSelectPanel.style.display = isVisible ? 'none' : 'block';
                if (!isVisible) {
                    renderFieldCheckboxes();
                    this.renderBatchEditFields(editableFields);
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
                if (this.dataTable.selectedIds.size === 0) {
                    showMessage('请先选择要编辑的记录', 'warning');
                    return;
                }
                
                this.fieldValues = {};
                this.nullFields = new Set();
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
                
                this.nullFields.forEach(field => {
                    updates[field] = null;
                });
                
                if (Object.keys(updates).length === 0) {
                    showMessage('请至少修改一个字段', 'warning');
                    return;
                }
                
                const ids = Array.from(this.dataTable.selectedIds);
                
                showLoading();
                
                const response = await callApi(`/batch_update/${this.tableKey}`, 'POST', {
                    ids: ids,
                    updates: updates
                });
                
                hideLoading();
                
                handleResponse(response, () => {
                    showMessage(`成功更新 ${ids.length} 条记录`, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('batchEditModal')).hide();
                    this.dataTable.selectedIds.clear();
                    this.dataTable.loadData();
                    this.statusCard.refresh();
                });
            });
        }
    }
}
