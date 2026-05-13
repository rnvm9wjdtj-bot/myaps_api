/**
 * 数据列表组件
 */

class DataTable {
    constructor(config) {
        this.tableName = config.tableName;
        this.columns = config.columns || [];
        this.container = config.container || document.getElementById('tableContainer');
        this.pageSize = config.pageSize || 100;
        this.currentPage = 1;
        this.total = 0;
        this.data = [];
        this.filters = {};
        this.sortField = '_createtime';
        this.sortOrder = 'desc';
        this.onRowClick = config.onRowClick;
        this.onSelectionChange = config.onSelectionChange;
        this.selectedIds = new Set();
        this.enumFields = config.enumFields || [];
        
        this.init();
    }
    
    init() {
        this.render();
        this.bindEvents();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="table-wrapper" style="display: flex; flex-direction: column; height: calc(100vh - 280px);">
                <div class="table-responsive flex-grow-1" style="overflow-y: auto; overflow-x: auto;">
                    <table class="table table-hover table-nowrap mb-0" style="min-width: max-content;">
                        <thead class="table-header-fixed">
                            <tr>
                                <th style="width: 40px; min-width: 40px;">
                                    <input type="checkbox" class="form-check-input" id="selectAll">
                                </th>
                                ${this.columns.map(col => `
                                    <th style="${col.width ? 'width: ' + col.width + '; min-width: ' + col.width : 'white-space: nowrap;'}" 
                                        data-field="${col.field}" 
                                        class="${col.sortable ? 'sortable' : ''}">
                                        ${col.title}
                                        ${col.sortable ? '<i class="bi bi-arrow-down-up"></i>' : ''}
                                    </th>
                                `).join('')}
                            </tr>
                        </thead>
                        <tbody id="tableBody">
                            <tr>
                                <td colspan="${this.columns.length + 1}" class="text-center text-muted py-4">
                                    加载中...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="table-footer-fixed d-flex justify-content-between align-items-center px-2 py-2 bg-white border-top" style="font-size:0.75rem">
                <div class="d-flex align-items-center gap-2">
                    <span id="totalInfo">共 0 条</span>
                    <select class="form-select form-select-sm" id="pageSizeSelect" style="width: 80px;">
                        <option value="50" ${this.pageSize === 50 ? 'selected' : ''}>50</option>
                        <option value="100" ${this.pageSize === 100 ? 'selected' : ''}>100</option>
                        <option value="200" ${this.pageSize === 200 ? 'selected' : ''}>200</option>
                        <option value="500" ${this.pageSize === 500 ? 'selected' : ''}>500</option>
                        <option value="1000" ${this.pageSize === 1000 ? 'selected' : ''}>1000</option>
                    </select>
                    <span>条/页</span>
                    <button class="btn btn-sm btn-outline-success" id="selectAllPagesBtn">
                        全选(<span id="totalCount">0</span>)
                    </button>
                    <button class="btn btn-sm btn-outline-primary ms-2" id="batchEditBtn" disabled>
                        编辑(<span id="selectedCount">0</span>)
                    </button>
                    <button class="btn btn-sm btn-outline-danger" id="batchDeleteBtn" disabled>
                        删除(<span id="selectedCountDup">0</span>)
                    </button>
                </div>
                <nav>
                    <ul class="pagination pagination-sm mb-0" id="pagination"></ul>
                </nav>
            </div>
        `;
    }
    
    bindEvents() {
        const selectAll = document.getElementById('selectAll');
        if (selectAll) {
            selectAll.addEventListener('change', (e) => {
                const checked = e.target.checked;
                document.querySelectorAll('.row-checkbox').forEach(cb => {
                    cb.checked = checked;
                    const id = parseInt(cb.dataset.id);
                    if (checked) {
                        this.selectedIds.add(id);
                    } else {
                        this.selectedIds.delete(id);
                    }
                });
                this.updateSelectedCount();
            });
        }
        
        const selectAllPagesBtn = document.getElementById('selectAllPagesBtn');
        if (selectAllPagesBtn) {
            selectAllPagesBtn.addEventListener('click', () => this.selectAllPages());
        }
        
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');
        if (batchDeleteBtn) {
            batchDeleteBtn.addEventListener('click', () => this.batchDelete());
        }
        
        const pageSizeSelect = document.getElementById('pageSizeSelect');
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', (e) => {
                this.pageSize = parseInt(e.target.value);
                this.currentPage = 1;
                this.loadData();
            });
        }
        
        this.container.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const field = th.dataset.field;
                if (this.sortField === field) {
                    this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
                } else {
                    this.sortField = field;
                    this.sortOrder = 'desc';
                }
                this.loadData();
            });
        });
    }
    
    async loadData(params = {}) {
        showLoading();
        
        this.filters = { ...this.filters, ...params };
        
        if (Object.keys(params).length > 0 || this.advancedFilters) {
            this.selectedIds.clear();
            const selectAll = document.getElementById('selectAll');
            if (selectAll) selectAll.checked = false;
            this.updateSelectedCount();
        }
        
        const queryParams = new URLSearchParams({
            page: this.currentPage,
            page_size: this.pageSize,
            sort_field: this.sortField,
            sort_order: this.sortOrder,
            ...this.filters
        });
        
        if (this.advancedFilters && this.advancedFilters.length > 0) {
            queryParams.set('advanced_filters', JSON.stringify(this.advancedFilters));
        }
        
        const response = await callApi(`/list/${this.tableName}?${queryParams}`);
        
        hideLoading();
        
        handleResponse(response, (data) => {
            this.data = data.data.records || [];
            this.total = data.data.total || 0;
            this.renderTable();
            this.renderPagination();
        });
    }
    
    renderTable() {
        const tbody = document.getElementById('tableBody');
        const totalInfo = document.getElementById('totalInfo');
        
        if (totalInfo) {
            totalInfo.textContent = `共 ${this.total} 条`;
        }
        
        this.updateTotalCount();
        
        if (this.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="${this.columns.length + 1}" class="text-center text-muted py-4">
                        暂无数据
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = this.data.map(row => {
            const errorMap = this.parseErrorFields(row);
            return `
            <tr data-id="${row._staging_id}" class="table-row ${row._status === 'rejected' ? 'table-row-rejected' : ''}">
                <td>
                    <input type="checkbox" class="form-check-input row-checkbox" 
                           data-id="${row._staging_id}"
                           ${this.selectedIds.has(row._staging_id) ? 'checked' : ''}>
                </td>
                ${this.columns.map(col => `
                    <td>${this.renderCell(col, row, errorMap)}</td>
                `).join('')}
            </tr>
        `}).join('');
        
        this.bindTooltip();
        
        tbody.querySelectorAll('.row-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const id = parseInt(e.target.dataset.id);
                if (e.target.checked) {
                    this.selectedIds.add(id);
                } else {
                    this.selectedIds.delete(id);
                }
                this.updateSelectedCount();
            });
        });
        
        tbody.querySelectorAll('.table-row').forEach(tr => {
            tr.addEventListener('dblclick', (e) => {
                if (e.target.type === 'checkbox') return;
                const id = parseInt(tr.dataset.id);
                const rowData = this.data.find(r => r._staging_id === id);
                if (this.onRowClick) {
                    this.onRowClick(rowData);
                }
            });
            tr.style.cursor = 'pointer';
            tr.title = '双击编辑';
        });
    }
    
    parseErrorFields(row) {
        const errorMap = {};
        if (row._status === 'rejected' && row._error_msg) {
            try {
                let errorData = row._error_msg;
                if (typeof errorData === 'string') {
                    errorData = JSON.parse(errorData);
                }
                if (!Array.isArray(errorData)) {
                    errorData = [errorData];
                }
                errorData.forEach(err => {
                    if (err.error_field) {
                        errorMap[err.error_field] = {
                            type: err.error_type,
                            message: err.error_message
                        };
                    }
                });
            } catch (e) {
                console.error('解析错误信息失败:', e, '原始数据:', row._error_msg);
                errorMap['_error'] = {
                    type: 'parse_error',
                    message: typeof row._error_msg === 'string' ? row._error_msg : '错误信息格式异常'
                };
            }
        }
        return errorMap;
    }
    
    renderCell(col, row, errorMap = {}) {
        let value = row[col.field];
        
        if (col.render) {
            return col.render(value, row);
        }
        
        if (col.field === '_status') {
            if (value === 'rejected' && row._error_msg) {
                return `<span class="status-error-cell" data-error-json="${escapeHtml(row._error_msg)}">${formatStatus(value)}</span>`;
            }
            return formatStatus(value);
        }
        
        if (col.field === '_createtime' || col.field === '_updatetime' || col.field === '_synced_time') {
            return `<span class="font-mono">${formatDateTime(value)}</span>`;
        }
        
        if (value === null || value === undefined) {
            const isFreeField = col.field.startsWith('free');
            const errorInfo = errorMap[col.field];
            if (errorInfo) {
                return `<span class="error-cell null-cell" data-error-type="${errorInfo.type}" data-error-msg="${escapeHtml(errorInfo.message)}">-</span>`;
            }
            return isFreeField ? '<span class="text-muted">-</span>' : '<span class="null-cell">-</span>';
        }
        
        const isEnumField = this.enumFields && this.enumFields.includes(col.field);
        
        const errorInfo = errorMap[col.field];
        if (errorInfo) {
            const displayValue = typeof value === 'string' && value.length > 30 
                ? truncateText(value, 30) 
                : value;
            const content = isEnumField 
                ? `<span class="enum-tag enum-tag-error">${escapeHtml(displayValue)}</span>`
                : `<span class="error-cell font-mono" data-error-type="${errorInfo.type}" data-error-msg="${escapeHtml(errorInfo.message)}" title="${escapeHtml(errorInfo.message)}">${escapeHtml(displayValue)}</span>`;
            return content;
        }
        
        if (isEnumField) {
            return `<span class="enum-tag">${escapeHtml(value)}</span>`;
        }
        
        if (typeof value === 'string' && value.length > 30) {
            return `<span class="font-mono" title="${escapeHtml(value)}">${escapeHtml(truncateText(value, 30))}</span>`;
        }
        
        return `<span class="font-mono">${escapeHtml(value)}</span>`;
    }
    
    bindTooltip() {
        const existingTooltips = document.querySelectorAll('.error-tooltip');
        existingTooltips.forEach(t => t.remove());
        
        document.querySelectorAll('.error-cell').forEach(cell => {
            cell.addEventListener('mouseenter', (e) => {
                const errorType = e.target.dataset.errorType;
                const errorMsg = e.target.dataset.errorMsg;
                if (!e.target._tooltip) {
                    const tooltip = document.createElement('div');
                    tooltip.className = 'error-tooltip';
                    tooltip.innerHTML = `<div class="error-tooltip-type">${errorType}</div><div class="error-tooltip-msg">${errorMsg}</div>`;
                    document.body.appendChild(tooltip);
                    e.target._tooltip = tooltip;
                }
                const rect = e.target.getBoundingClientRect();
                e.target._tooltip.style.left = rect.left + 'px';
                e.target._tooltip.style.top = (rect.bottom + 5) + 'px';
                e.target._tooltip.style.display = 'block';
            });
            
            cell.addEventListener('mouseleave', (e) => {
                if (e.target._tooltip) {
                    e.target._tooltip.remove();
                    e.target._tooltip = null;
                }
            });
        });
        
        document.querySelectorAll('.status-error-cell').forEach(cell => {
            cell.addEventListener('mouseenter', (e) => {
                const errorJson = e.target.dataset.errorJson;
                if (!e.target._tooltip) {
                    const tooltip = document.createElement('div');
                    tooltip.className = 'error-tooltip error-tooltip-wide';
                    try {
                        const errors = JSON.parse(errorJson);
                        tooltip.innerHTML = errors.map(err => `
                            <div class="error-tooltip-item">
                                <div class="error-tooltip-type">${err.error_type || 'unknown'}</div>
                                ${err.error_field ? `<div class="error-tooltip-field">字段: ${err.error_field}</div>` : ''}
                                <div class="error-tooltip-msg">${escapeHtml(err.error_message || '')}</div>
                            </div>
                        `).join('<hr class="error-tooltip-divider">');
                    } catch (ex) {
                        tooltip.innerHTML = `<pre class="error-tooltip-json">${escapeHtml(errorJson)}</pre>`;
                    }
                    document.body.appendChild(tooltip);
                    e.target._tooltip = tooltip;
                }
                const rect = e.target.getBoundingClientRect();
                const tooltipWidth = 400;
                e.target._tooltip.style.left = Math.min(rect.left, window.innerWidth - tooltipWidth - 10) + 'px';
                e.target._tooltip.style.top = (rect.bottom + 5) + 'px';
                e.target._tooltip.style.display = 'block';
            });
            
            cell.addEventListener('mouseleave', (e) => {
                if (e.target._tooltip) {
                    e.target._tooltip.remove();
                    e.target._tooltip = null;
                }
            });
        });
    }
    
    renderPagination() {
        const pagination = document.getElementById('pagination');
        const totalPages = Math.ceil(this.total / this.pageSize);
        
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }
        
        let html = '';
        
        html += `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage - 1}">上一页</a>
            </li>
        `;
        
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, this.currentPage + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            html += `
                <li class="page-item ${i === this.currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }
        
        html += `
            <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage + 1}">下一页</a>
            </li>
        `;
        
        pagination.innerHTML = html;
        
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(link.dataset.page);
                if (page >= 1 && page <= totalPages && page !== this.currentPage) {
                    this.currentPage = page;
                    this.selectedIds.clear();
                    const selectAll = document.getElementById('selectAll');
                    if (selectAll) selectAll.checked = false;
                    this.updateSelectedCount();
                    this.loadData();
                }
            });
        });
    }
    
    updateSelectedCount() {
        const count = this.selectedIds.size;
        const selectedCount = document.getElementById('selectedCount');
        const selectedCountDup = document.getElementById('selectedCountDup');
        const batchEditBtn = document.getElementById('batchEditBtn');
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');
        
        if (selectedCount) selectedCount.textContent = count;
        if (selectedCountDup) selectedCountDup.textContent = count;
        if (batchEditBtn) batchEditBtn.disabled = count === 0;
        if (batchDeleteBtn) batchDeleteBtn.disabled = count === 0;
        
        if (this.onSelectionChange) {
            this.onSelectionChange(Array.from(this.selectedIds));
        }
    }
    
    updateTotalCount() {
        const totalCount = document.getElementById('totalCount');
        if (totalCount) {
            totalCount.textContent = this.total;
        }
    }
    
    async selectAllPages() {
        if (this.total === 0) {
            showMessage('没有可选择的记录', 'warning');
            return;
        }
        
        if (!confirm(`确定选中全部 ${this.total} 条记录吗？\n\n注意：这将获取所有分页的记录ID，可能需要较长时间。`)) {
            return;
        }
        
        showLoading();
        
        const queryParams = new URLSearchParams({
            page: 1,
            page_size: 10000,
            sort_field: this.sortField,
            sort_order: this.sortOrder,
            ...this.filters
        });
        
        if (this.advancedFilters && this.advancedFilters.length > 0) {
            queryParams.set('advanced_filters', JSON.stringify(this.advancedFilters));
        }
        
        const response = await callApi(`/list/${this.tableName}?${queryParams}`);
        
        hideLoading();
        
        handleResponse(response, (data) => {
            const allRecords = data.data.records || [];
            this.selectedIds.clear();
            allRecords.forEach(row => {
                this.selectedIds.add(row._staging_id);
            });
            
            const selectAll = document.getElementById('selectAll');
            if (selectAll) selectAll.checked = true;
            
            document.querySelectorAll('.row-checkbox').forEach(cb => {
                cb.checked = true;
            });
            
            this.updateSelectedCount();
            showMessage(`已选中 ${this.selectedIds.size} 条记录`, 'success');
        });
    }
    
    async batchDelete() {
        if (this.selectedIds.size === 0) return;
        
        if (!confirm(`确定删除选中的 ${this.selectedIds.size} 条记录吗？`)) return;
        
        showLoading();
        
        const response = await callApi(`/batch_delete/${this.tableName}`, 'POST', Array.from(this.selectedIds));
        
        hideLoading();
        
        handleResponse(response, () => {
            showMessage('删除成功', 'success');
            this.selectedIds.clear();
            this.loadData();
        });
    }
    
    refresh() {
        this.loadData();
    }
    
    setFilter(key, value) {
        if (value) {
            this.filters[key] = value;
        } else {
            delete this.filters[key];
        }
        this.currentPage = 1;
        this.selectedIds.clear();
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        this.updateSelectedCount();
        this.loadData();
    }
}
