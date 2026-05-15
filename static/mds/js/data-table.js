/**
 * @file data-table.js
 * @description 数据表格组件 - 支持虚拟滚动、批量选择、自定义列渲染
 * @author Frontend Team
 * @version 1.2.0
 * @date 2026-05-14
 * @requires ./common.js
 */

class DataTable {
    constructor(config) {
        // 基础配置
        this.tableName = config.tableName;
        this.columns = config.columns || [];
        this.container = config.container || document.getElementById('tableContainer');
        this.pageSize = config.pageSize || 100;
        this.currentPage = 1;
        this.total = 0;
        this.data = [];
        this.filters = {};
        this.advancedFilters = null;
        this.sortField = config.defaultSortField || '_createtime';
        this.sortOrder = config.defaultSortOrder || 'desc';
        
        // 回调函数
        this.onRowClick = config.onRowClick;
        this.onSelectionChange = config.onSelectionChange;
        this.onRowDoubleClick = config.onRowDoubleClick;
        
        // 选择状态
        this.selectedIds = new Set();
        this.selectedAllPages = false;
        
        // 枚举配置
        this.enumFields = config.enumFields || [];
        this.enumOptions = config.enumOptions || {};
        
        // 渲染配置
        this.renderMode = config.renderMode || 'standard'; // standard | virtual
        this.virtualRowHeight = config.virtualRowHeight || 32;
        
        // 性能优化
        this.isLoading = false;
        this.lastSearchTime = 0;
        this.searchDebounce = config.searchDebounce || 300;
        
        // 初始化
        this.init();
    }
    
    init() {
        this.render();
        this.bindEvents();
    }
    
    /**
     * 渲染表格容器
     */
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
                                ${this.columns.map(col => this.renderHeaderCell(col)).join('')}
                            </tr>
                        </thead>
                        <tbody id="tableBody">
                            <tr>
                                <td colspan="${this.columns.length + 1}" class="text-center text-muted py-4">
                                    <div class="spinner-border text-primary" role="status" style="width: 2rem; height: 2rem;">
                                        <span class="visually-hidden">加载中...</span>
                                    </div>
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
                    <button class="btn btn-sm btn-outline-success" id="selectAllPagesBtn" style="width: 100px;">
                        全选(<span id="totalCount">0</span>)
                    </button>
                    <button class="btn btn-sm btn-outline-primary ms-2" id="batchEditBtn" disabled style="width: 100px;">
                        编辑(<span id="selectedCount">0</span>)
                    </button>
                    <button class="btn btn-sm btn-outline-danger" id="batchDeleteBtn" disabled style="width: 100px;">
                        删除(<span id="selectedCountDup">0</span>)
                    </button>
                    <button class="btn btn-sm btn-outline-cyan" id="templateBtn" style="width: 100px;">
                        模板
                    </button>
                </div>
                <nav>
                    <ul class="pagination pagination-sm mb-0" id="pagination"></ul>
                </nav>
            </div>
        `;
    }
    
    /**
     * 渲染表头单元格
     * @param {Object} col - 列配置
     * @returns {string} HTML字符串
     */
    renderHeaderCell(col) {
        const sortIcon = col.sortable ? '<i class="bi bi-arrow-down-up ms-1"></i>' : '';
        return `
            <th 
                style="${col.width ? 'width: ' + col.width + '; min-width: ' + col.width : 'white-space: nowrap;'}" 
                data-field="${col.field}" 
                class="${col.sortable ? 'sortable cursor-pointer' : ''}"
                title="${col.sortable ? `点击按 ${col.title} 排序` : ''}"
            >
                ${col.title}${sortIcon}
            </th>
        `;
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 全选复选框
        const selectAll = document.getElementById('selectAll');
        if (selectAll) {
            selectAll.addEventListener('change', (e) => this.handleSelectAll(e.target.checked));
        }
        
        // 全选所有页
        const selectAllPagesBtn = document.getElementById('selectAllPagesBtn');
        if (selectAllPagesBtn) {
            selectAllPagesBtn.addEventListener('click', () => this.selectAllPages());
        }
        
        // 批量删除
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');
        if (batchDeleteBtn) {
            batchDeleteBtn.addEventListener('click', () => this.batchDelete());
        }
        
        // 模板下载
        const templateBtn = document.getElementById('templateBtn');
        if (templateBtn) {
            templateBtn.addEventListener('click', () => downloadTemplate(this.tableName));
        }
        
        // 页面大小切换
        const pageSizeSelect = document.getElementById('pageSizeSelect');
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', (e) => {
                this.pageSize = parseInt(e.target.value);
                this.currentPage = 1;
                this.loadData();
            });
        }
        
        // 排序点击
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
    
    /**
     * 处理全选
     * @param {boolean} checked - 是否选中
     */
    handleSelectAll(checked) {
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
    }
    
    /**
     * 加载数据
     * @param {Object} params - 查询参数
     * @returns {Promise<void>}
     */
    async loadData(params = {}) {
        if (this.isLoading) return;
        
        this.isLoading = true;
        showLoading();
        
        try {
            this.filters = { ...this.filters, ...params };
            
            // 重置选择状态（非首次加载时）
            if (Object.keys(params).length > 0) {
                this.selectedIds.clear();
                this.selectedAllPages = false;
                const selectAll = document.getElementById('selectAll');
                if (selectAll) selectAll.checked = false;
                this.updateSelectedCount();
            }
            
            const queryParams = this.buildQueryParams();
            const response = await callApi(`/list/${this.tableName}?${queryParams}`);
            
            handleResponse(response, (data) => {
                this.data = data.data.records || [];
                this.total = data.data.total || 0;
                this.renderTable();
                this.renderPagination();
            });
        } catch (error) {
            console.error('加载数据失败:', error);
            showMessage('加载数据失败', 'danger');
        } finally {
            this.isLoading = false;
            hideLoading();
        }
    }
    
    /**
     * 构建查询参数
     * @returns {URLSearchParams} 查询参数
     */
    buildQueryParams() {
        const params = new URLSearchParams({
            page: this.currentPage,
            page_size: this.pageSize,
            sort_field: this.sortField,
            sort_order: this.sortOrder,
            ...this.filters
        });
        
        if (this.advancedFilters && this.advancedFilters.length > 0) {
            params.set('advanced_filters', JSON.stringify(this.advancedFilters));
        }
        
        return params;
    }
    
    /**
     * 渲染表格内容
     */
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
        
        // 根据渲染模式选择渲染方式
        if (this.renderMode === 'virtual' && this.data.length > 200) {
            this.renderVirtualTable(tbody);
        } else {
            this.renderStandardTable(tbody);
        }
    }
    
    /**
     * 标准渲染模式
     * @param {HTMLElement} tbody - 表格体元素
     */
    renderStandardTable(tbody) {
        tbody.innerHTML = this.data.map(row => this.renderRow(row)).join('');
        this.bindRowEvents();
    }
    
    /**
     * 虚拟滚动渲染模式
     * @param {HTMLElement} tbody - 表格体元素
     */
    renderVirtualTable(tbody) {
        // 虚拟滚动实现（简化版）
        const visibleCount = Math.min(this.data.length, 100);
        const startIndex = 0;
        const endIndex = startIndex + visibleCount;
        
        tbody.innerHTML = this.data.slice(startIndex, endIndex).map((row, idx) => 
            this.renderRow(row, startIndex + idx)
        ).join('');
        
        // 设置容器高度以显示滚动条
        tbody.style.height = `${this.data.length * this.virtualRowHeight}px`;
        tbody.style.position = 'relative';
        
        this.bindRowEvents();
    }
    
    /**
     * 渲染行
     * @param {Object} row - 行数据
     * @param {number} [index] - 行索引
     * @returns {string} HTML字符串
     */
    renderRow(row, index = 0) {
        const errorMap = this.parseErrorFields(row);
        const isSelected = this.selectedIds.has(row._staging_id);
        const rowClass = this.getRowClass(row);
        
        return `
            <tr 
                data-id="${row._staging_id}" 
                class="table-row ${rowClass}"
                ${this.renderMode === 'virtual' ? `style="position: absolute; top: ${index * this.virtualRowHeight}px;"` : ''}
            >
                <td>
                    <input 
                        type="checkbox" 
                        class="form-check-input row-checkbox" 
                        data-id="${row._staging_id}"
                        ${isSelected ? 'checked' : ''}
                    >
                </td>
                ${this.columns.map(col => `<td>${this.renderCell(col, row, errorMap)}</td>`).join('')}
            </tr>
        `;
    }
    
    /**
     * 获取行样式类
     * @param {Object} row - 行数据
     * @returns {string} 样式类名
     */
    getRowClass(row) {
        const classes = [];
        
        // 状态相关样式
        if (row._status === 'compliance_error' || row._status === 'rejected') {
            classes.push('table-row-rejected');
        }
        
        return classes.join(' ');
    }
    
    /**
     * 解析错误字段
     * @param {Object} row - 行数据
     * @returns {Object} 错误映射
     */
    parseErrorFields(row) {
        const errorMap = {};
        if (!row._error_msg) return errorMap;
        
        try {
            let errorData = typeof row._error_msg === 'string' ? JSON.parse(row._error_msg) : row._error_msg;
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
        }
        
        return errorMap;
    }
    
    /**
     * 渲染单元格
     * @param {Object} col - 列配置
     * @param {Object} row - 行数据
     * @param {Object} errorMap - 错误映射
     * @returns {string} HTML字符串
     */
    renderCell(col, row, errorMap = {}) {
        let value = row[col.field];
        
        // 自定义渲染函数
        if (col.render) {
            return col.render(value, row);
        }
        
        // 状态字段
        if (col.field === '_status') {
            return this.renderStatusCell(value, row);
        }
        
        // 时间字段
        if (['_createtime', '_updatetime', '_synced_time'].includes(col.field)) {
            return `<span class="font-mono">${formatDateTime(value)}</span>`;
        }
        
        // 空值处理
        if (value === null || value === undefined) {
            return this.renderNullCell(col, errorMap);
        }
        
        // 错误处理
        const errorInfo = errorMap[col.field];
        if (errorInfo) {
            return this.renderErrorCell(value, errorInfo, col);
        }
        
        // 枚举字段
        if (this.enumFields.includes(col.field)) {
            return this.renderEnumCell(value, col.field);
        }
        
        // 普通文本
        return this.renderTextCell(value, col);
    }
    
    /**
     * 渲染状态单元格
     */
    renderStatusCell(status, row) {
        if (status === 'compliance_error' || status === 'rejected') {
            return `
                <span class="status-error-cell" data-error-json="${escapeHtml(row._error_msg || '[]')}">
                    ${formatStatus(status)}
                </span>
            `;
        }
        return formatStatus(status);
    }
    
    /**
     * 渲染空值单元格
     */
    renderNullCell(col, errorMap) {
        const isFreeField = col.field.startsWith('free');
        const errorInfo = errorMap[col.field];
        
        if (errorInfo) {
            return `
                <span 
                    class="error-cell null-cell" 
                    data-error-type="${errorInfo.type}" 
                    data-error-msg="${escapeHtml(errorInfo.message)}"
                >-</span>
            `;
        }
        
        return isFreeField ? '<span class="text-muted">-</span>' : '<span class="null-cell">-</span>';
    }
    
    /**
     * 渲染错误单元格
     */
    renderErrorCell(value, errorInfo, col) {
        const displayValue = typeof value === 'string' && value.length > 30 
            ? truncateText(value, 30) 
            : value;
        
        const isEnumField = this.enumFields.includes(col.field);
        
        if (isEnumField) {
            // 统一使用 data-error-msg 方式（替代 title）
            return `
                <span class="enum-tag enum-tag-error" data-error-type="${errorInfo.type}" data-error-msg="${escapeHtml(errorInfo.message)}">
                    ${escapeHtml(displayValue)}
                </span>
            `;
        }
        
        return `
            <span 
                class="error-cell font-mono" 
                data-error-type="${errorInfo.type}" 
                data-error-msg="${escapeHtml(errorInfo.message)}"
            >
                ${escapeHtml(displayValue)}
            </span>
        `;
    }
    
    /**
     * 渲染枚举单元格
     */
    renderEnumCell(value, fieldName) {
        const options = this.enumOptions[fieldName] || [];
        const option = options.find(o => String(o.value) === String(value));
        
        if (option) {
            return `<span class="enum-tag">${escapeHtml(option.label)}</span>`;
        }
        
        return `<span class="enum-tag">${escapeHtml(value)}</span>`;
    }
    
    /**
     * 渲染文本单元格
     */
    renderTextCell(value, col) {
        if (typeof value === 'string' && value.length > 30) {
            return `
                <span class="font-mono" title="${escapeHtml(value)}">
                    ${escapeHtml(truncateText(value, 30))}
                </span>
            `;
        }
        
        return `<span class="font-mono">${escapeHtml(value)}</span>`;
    }
    
    /**
     * 绑定行事件
     */
    bindRowEvents() {
        // 错误提示框
        this.bindTooltip();
        
        // 行选择
        document.querySelectorAll('.row-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => this.handleRowSelect(e.target));
        });
        
        // 双击编辑
        document.querySelectorAll('.table-row').forEach(tr => {
            tr.addEventListener('dblclick', (e) => this.handleRowDoubleClick(e, tr));
            tr.style.cursor = 'pointer';
        });
    }
    
    /**
     * 处理行选择
     * @param {HTMLElement} checkbox - 复选框元素
     */
    handleRowSelect(checkbox) {
        const id = parseInt(checkbox.dataset.id);
        if (checkbox.checked) {
            this.selectedIds.add(id);
        } else {
            this.selectedIds.delete(id);
            this.selectedAllPages = false;
        }
        this.updateSelectedCount();
    }
    
    /**
     * 处理行双击
     * @param {Event} e - 事件对象
     * @param {HTMLElement} tr - 行元素
     */
    handleRowDoubleClick(e, tr) {
        if (e.target.type === 'checkbox') return;
        
        const id = parseInt(tr.dataset.id);
        const rowData = this.data.find(r => r._staging_id === id);
        
        if (this.onRowDoubleClick) {
            this.onRowDoubleClick(rowData);
        } else if (this.onRowClick) {
            this.onRowClick(rowData);
        }
    }
    
    /**
     * 绑定提示框
     */
    bindTooltip() {
        // 清理旧提示框
        document.querySelectorAll('.error-tooltip').forEach(t => t.remove());
        
        // 错误单元格提示（包括普通错误和枚举错误）
        document.querySelectorAll('.error-cell, .enum-tag-error').forEach(cell => {
            cell.addEventListener('mouseenter', (e) => this.showErrorTooltip(e));
            cell.addEventListener('mouseleave', (e) => this.hideErrorTooltip(e));
        });
        
        // 状态错误提示
        document.querySelectorAll('.status-error-cell').forEach(cell => {
            cell.addEventListener('mouseenter', (e) => this.showStatusErrorTooltip(e));
            cell.addEventListener('mouseleave', (e) => this.hideStatusErrorTooltip(e));
        });
    }
    
    /**
     * 显示错误提示框
     */
    showErrorTooltip(e) {
        const errorType = e.target.dataset.errorType;
        const errorMsg = e.target.dataset.errorMsg;
        
        if (!errorType || !errorMsg) return;
        
        const tooltip = document.createElement('div');
        tooltip.className = 'error-tooltip';
        tooltip.innerHTML = `
            <div class="error-tooltip-type">${errorType}</div>
            <div class="error-tooltip-msg">${errorMsg}</div>
        `;
        document.body.appendChild(tooltip);
        e.target._tooltip = tooltip;
        
        const rect = e.target.getBoundingClientRect();
        tooltip.style.left = rect.left + 'px';
        tooltip.style.top = rect.bottom + 5 + 'px';
        tooltip.style.display = 'block';
    }
    
    /**
     * 隐藏错误提示框
     */
    hideErrorTooltip(e) {
        if (e.target._tooltip) {
            e.target._tooltip.remove();
            e.target._tooltip = null;
        }
    }
    
    /**
     * 显示状态错误提示框
     */
    showStatusErrorTooltip(e) {
        const errorJson = e.target.dataset.errorJson;
        if (!errorJson) return;
        
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
        
        const rect = e.target.getBoundingClientRect();
        tooltip.style.left = Math.min(rect.left, window.innerWidth - 410) + 'px';
        tooltip.style.top = rect.bottom + 5 + 'px';
        tooltip.style.display = 'block';
    }
    
    /**
     * 隐藏状态错误提示框
     */
    hideStatusErrorTooltip(e) {
        if (e.target._tooltip) {
            e.target._tooltip.remove();
            e.target._tooltip = null;
        }
    }
    
    /**
     * 渲染分页
     */
    renderPagination() {
        const pagination = document.getElementById('pagination');
        const totalPages = Math.ceil(this.total / this.pageSize);
        
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }
        
        pagination.innerHTML = this.buildPaginationHtml(totalPages);
        this.bindPaginationEvents();
    }
    
    /**
     * 构建分页HTML
     * @param {number} totalPages - 总页数
     * @returns {string} HTML字符串
     */
    buildPaginationHtml(totalPages) {
        let html = `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage - 1}">
                    <i class="bi bi-chevron-left"></i> 上一页
                </a>
            </li>
        `;
        
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, this.currentPage + 2);
        
        // 添加前面的省略号
        if (startPage > 1) {
            html += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="1">1</a>
                </li>
            `;
            if (startPage > 2) {
                html += `
                    <li class="page-item disabled">
                        <span class="page-link">...</span>
                    </li>
                `;
            }
        }
        
        for (let i = startPage; i <= endPage; i++) {
            html += `
                <li class="page-item ${i === this.currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }
        
        // 添加后面的省略号
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                html += `
                    <li class="page-item disabled">
                        <span class="page-link">...</span>
                    </li>
                `;
            }
            html += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${totalPages}">${totalPages}</a>
                </li>
            `;
        }
        
        html += `
            <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage + 1}">
                    下一页 <i class="bi bi-chevron-right"></i>
                </a>
            </li>
        `;
        
        return html;
    }
    
    /**
     * 绑定分页事件
     */
    bindPaginationEvents() {
        document.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(link.dataset.page);
                if (page >= 1 && page <= Math.ceil(this.total / this.pageSize) && page !== this.currentPage) {
                    this.currentPage = page;
                    this.selectedIds.clear();
                    this.selectedAllPages = false;
                    const selectAll = document.getElementById('selectAll');
                    if (selectAll) selectAll.checked = false;
                    this.updateSelectedCount();
                    this.loadData();
                }
            });
        });
    }
    
    /**
     * 更新选择计数
     */
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
    
    /**
     * 更新总数显示
     */
    updateTotalCount() {
        const totalCount = document.getElementById('totalCount');
        if (totalCount) {
            totalCount.textContent = this.total;
        }
    }
    
    /**
     * 全选所有页
     * @returns {Promise<void>}
     */
    async selectAllPages() {
        if (this.total === 0) {
            showMessage('没有可选择的记录', 'warning');
            return;
        }
        
        if (!confirm(`确定选中全部 ${this.total} 条记录吗？\n\n注意：这将获取所有分页的记录ID，可能需要较长时间。`)) {
            return;
        }
        
        showLoading();
        
        try {
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
            
            handleResponse(response, (data) => {
                const allRecords = data.data.records || [];
                this.selectedIds.clear();
                allRecords.forEach(row => this.selectedIds.add(row._staging_id));
                this.selectedAllPages = true;
                
                const selectAll = document.getElementById('selectAll');
                if (selectAll) selectAll.checked = true;
                
                document.querySelectorAll('.row-checkbox').forEach(cb => {
                    cb.checked = true;
                });
                
                this.updateSelectedCount();
                showMessage(`已选中 ${this.selectedIds.size} 条记录`, 'success');
            });
        } catch (error) {
            console.error('全选失败:', error);
            showMessage('全选失败', 'danger');
        } finally {
            hideLoading();
        }
    }
    
    /**
     * 批量删除
     * @returns {Promise<void>}
     */
    async batchDelete() {
        if (this.selectedIds.size === 0) return;
        
        if (!confirm(`确定删除选中的 ${this.selectedIds.size} 条记录吗？`)) return;
        
        showLoading();
        
        try {
            const response = await callApi(`/batch_delete/${this.tableName}`, 'POST', Array.from(this.selectedIds));
            
            handleResponse(response, () => {
                showMessage('删除成功', 'success');
                this.selectedIds.clear();
                this.loadData();
            });
        } catch (error) {
            console.error('批量删除失败:', error);
            showMessage('批量删除失败', 'danger');
        } finally {
            hideLoading();
        }
    }
    
    /**
     * 设置筛选条件
     * @param {string} key - 筛选键
     * @param {*} value - 筛选值
     */
    setFilter(key, value) {
        if (value) {
            this.filters[key] = value;
        } else {
            delete this.filters[key];
        }
        this.currentPage = 1;
        this.selectedIds.clear();
        this.selectedAllPages = false;
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        this.updateSelectedCount();
        this.loadData();
    }
    
    /**
     * 刷新
     */
    refresh() {
        this.loadData();
    }
    
    /**
     * 获取选中的ID列表
     * @returns {number[]} 选中的ID数组
     */
    getSelectedIds() {
        return Array.from(this.selectedIds);
    }
    
    /**
     * 清除选择
     */
    clearSelection() {
        this.selectedIds.clear();
        this.selectedAllPages = false;
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = false);
        this.updateSelectedCount();
    }
    
    /**
     * 销毁组件
     */
    destroy() {
        this.selectedIds.clear();
        this.container.innerHTML = '';
    }
}
