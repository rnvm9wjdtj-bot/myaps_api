/**
 * 数据列表组件
 */

class DataTable {
    constructor(config) {
        this.tableName = config.tableName;
        this.columns = config.columns || [];
        this.container = config.container || document.getElementById('tableContainer');
        this.pageSize = config.pageSize || 20;
        this.currentPage = 1;
        this.total = 0;
        this.data = [];
        this.filters = {};
        this.sortField = '_createtime';
        this.sortOrder = 'desc';
        this.onRowClick = config.onRowClick;
        this.onSelectionChange = config.onSelectionChange;
        this.selectedIds = new Set();
        
        this.init();
    }
    
    init() {
        this.render();
        this.bindEvents();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th style="width: 40px;">
                                <input type="checkbox" class="form-check-input" id="selectAll">
                            </th>
                            ${this.columns.map(col => `
                                <th style="${col.width ? 'width:' + col.width : ''}" 
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
            <div class="d-flex justify-content-between align-items-center p-3">
                <div>
                    <span id="totalInfo">共 0 条</span>
                    <button class="btn btn-sm btn-outline-danger ms-2" id="batchDeleteBtn" disabled>
                        批量删除 (<span id="selectedCount">0</span>)
                    </button>
                </div>
                <nav>
                    <ul class="pagination" id="pagination"></ul>
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
        
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');
        if (batchDeleteBtn) {
            batchDeleteBtn.addEventListener('click', () => this.batchDelete());
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
        
        const queryParams = new URLSearchParams({
            page: this.currentPage,
            page_size: this.pageSize,
            sort_field: this.sortField,
            sort_order: this.sortOrder,
            ...this.filters
        });
        
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
        
        tbody.innerHTML = this.data.map(row => `
            <tr data-id="${row._staging_id}" class="table-row">
                <td>
                    <input type="checkbox" class="form-check-input row-checkbox" 
                           data-id="${row._staging_id}"
                           ${this.selectedIds.has(row._staging_id) ? 'checked' : ''}>
                </td>
                ${this.columns.map(col => `
                    <td>${this.renderCell(col, row)}</td>
                `).join('')}
            </tr>
        `).join('');
        
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
            tr.addEventListener('click', (e) => {
                if (e.target.type === 'checkbox') return;
                const id = parseInt(tr.dataset.id);
                const rowData = this.data.find(r => r._staging_id === id);
                if (this.onRowClick) {
                    this.onRowClick(rowData);
                }
            });
        });
    }
    
    renderCell(col, row) {
        let value = row[col.field];
        
        if (col.render) {
            return col.render(value, row);
        }
        
        if (col.field === '_status') {
            return formatStatus(value);
        }
        
        if (col.field === '_createtime' || col.field === '_updatetime' || col.field === '_synced_time') {
            return formatDate(value);
        }
        
        if (value === null || value === undefined) {
            return '<span class="text-muted">-</span>';
        }
        
        if (typeof value === 'string' && value.length > 30) {
            return `<span title="${escapeHtml(value)}">${escapeHtml(truncateText(value, 30))}</span>`;
        }
        
        return escapeHtml(value);
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
                    this.loadData();
                }
            });
        });
    }
    
    updateSelectedCount() {
        const count = this.selectedIds.size;
        const selectedCount = document.getElementById('selectedCount');
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');
        
        if (selectedCount) selectedCount.textContent = count;
        if (batchDeleteBtn) batchDeleteBtn.disabled = count === 0;
        
        if (this.onSelectionChange) {
            this.onSelectionChange(Array.from(this.selectedIds));
        }
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
        this.loadData();
    }
}
