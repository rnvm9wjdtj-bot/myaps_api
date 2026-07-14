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
        this.selectAllPageSize = config.selectAllPageSize || 10000;
        
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
        
        // 外键配置
        this.foreignKeyFields = config.foreignKeyFields || [];
        this.foreignKeys = config.foreignKeys || [];
        this.foreignKeyOptions = {}; // 外键选项缓存 {fieldName: [{value, label}, ...]}
        
        // 必填字段配置
        this.requiredFields = config.requiredFields || [];
        
        // 主键字段配置
        this.primaryKeyFields = config.primaryKeyFields || [];
        
        // 字段映射（Python字段名 -> 数据库字段名）
        this.fieldMap = config.fieldMap || {};
        
        // 字段默认值
        this.fieldDefaults = config.fieldDefaults || {};
        
        // 渲染模式
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
        this.bindLanguageChangeListener();
    }
    
    /**
     * 监听语言切换事件
     */
    bindLanguageChangeListener() {
        window.addEventListener('languageChanged', () => {
            this.render();
            this.loadData();
        });
    }
    
    /**
     * 渲染表格容器
     */
    render() {
        this.container.innerHTML = `
            <div class="table-wrapper" style="display: flex; flex-direction: column; height: calc(100vh - 280px);">
                <div class="table-responsive flex-grow-1" style="overflow-y: auto; overflow-x: auto;">
                    <table class="table table-hover table-nowrap mb-0" style="width: 100%; table-layout: auto;">
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
                                        <span class="visually-hidden">${typeof i18n !== 'undefined' ? i18n.t('mds.table.loading') : '加载中...'}</span>
                                    </div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="table-footer-fixed d-flex justify-content-between align-items-center px-2 py-2 bg-white border-top" style="font-size:0.75rem">
                <div class="d-flex align-items-center gap-2">
                    <button class="btn btn-sm btn-outline-success font-monospace" id="selectAllPagesBtn" style="width: 150px;">
                        <i class="bi bi-check-all"></i> <span id="selectAllBtnText">${typeof i18n !== 'undefined' ? i18n.t('mds.action.selectAll') : '全选'}(<span id="totalCount">0</span>)</span>
                    </button>
                    <button class="btn btn-sm btn-outline-primary font-monospace" id="batchEditBtn" disabled style="width: 150px;">
                        <i class="bi bi-pencil"></i> <span id="editBtnText">${typeof i18n !== 'undefined' ? i18n.t('mds.action.edit') : '编辑'}(<span id="selectedCount">0</span>)</span>
                    </button>
                    <button class="btn btn-sm btn-outline-danger font-monospace" id="batchDeleteBtn" disabled style="width: 150px;">
                        <i class="bi bi-trash"></i> <span id="deleteBtnText">${typeof i18n !== 'undefined' ? i18n.t('mds.action.delete') : '删除'}(<span id="selectedCountDup">0</span>)</span>
                    </button>
                    <button class="btn btn-sm btn-outline-info font-monospace" id="templateBtn" style="width: 150px;">
                        <i class="bi bi-download"></i> <span id="exportBtnText">${typeof i18n !== 'undefined' ? i18n.t('mds.action.exportTemplate') : '导出模板'}</span>
                    </button>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <select class="form-select form-select-sm font-monospace" id="pageSizeSelect" style="width: 80px;">
                        <option value="50" ${this.pageSize === 50 ? 'selected' : ''}>50</option>
                        <option value="100" ${this.pageSize === 100 ? 'selected' : ''}>100</option>
                        <option value="200" ${this.pageSize === 200 ? 'selected' : ''}>200</option>
                        <option value="500" ${this.pageSize === 500 ? 'selected' : ''}>500</option>
                        <option value="1000" ${this.pageSize === 1000 ? 'selected' : ''}>1000</option>
                    </select>
                    <span class="font-monospace">${typeof i18n !== 'undefined' ? i18n.t('mds.table.perPage') : '条/页'}</span>
                    <span id="totalInfo" class="font-monospace">${typeof i18n !== 'undefined' ? i18n.t('mds.table.total', {count: 0}) : '共 0 条'}</span>
                    <nav>
                        <ul class="pagination pagination-sm mb-0" id="pagination"></ul>
                    </nav>
                </div>
            </div>
        `;
    }
    
    /**
     * 渲染表头单元格
     * @param {Object} col - 列配置
     * @returns {string} HTML字符串
     */
    renderHeaderCell(col) {
        const isEnum = this.enumFields.includes(col.field);
        const isForeignKey = this.foreignKeys.some(fk => fk.field === col.field);
        const isRequired = this.requiredFields.includes(col.field);
        const isPrimaryKey = this.primaryKeyFields.includes(col.field);
        const isCompositeKey = this.primaryKeyFields.length > 1 && isPrimaryKey;
        const dbFieldName = this.fieldMap[col.field] || col.field;
        const defaultValue = this.fieldDefaults[col.field];
        const primaryKeyIcon = isPrimaryKey 
            ? `<i class="bi ${isCompositeKey ? 'bi-key' : 'bi-key'} ms-1" style="font-size: 0.85rem; color: #ff9300;" title="${isCompositeKey ? '联合主键字段' : '主键字段'}"></i>` 
            : '';
        const readOnlyIcon = col.readOnly ? '<i class="bi bi-lock ms-1 text-muted" style="font-size: 0.8rem;"></i>' : '';
        const enumIcon = isEnum ? '<i class="bi bi-list-ul ms-1" style="font-size: 0.8rem; color: #08c9c9;" title="枚举字段"></i>' : '';
        const foreignKeyIcon = isForeignKey ? '<i class="bi bi-link-45deg ms-1" style="font-size: 0.8rem; color: #08c9c9;" title="外键字段"></i>' : '';
        const requiredIcon = isRequired ? '<span style="color: #f52222; font-weight: bold; margin-left: 2px;">*</span>' : '';
        
        let sortIcon = '';
        if (col.sortable) {
            if (this.sortField === col.field) {
                sortIcon = this.sortOrder === 'asc' 
                    ? '<i class="bi bi-arrow-up ms-1" style="color: #08c9c9;"></i>' 
                    : '<i class="bi bi-arrow-down ms-1" style="color: #08c9c9;"></i>';
            } else {
                sortIcon = '<i class="bi bi-arrow-down-up ms-1" style="color: #08c9c9;"></i>';
            }
        }
        
        const titleParts = [`字段: ${dbFieldName}`];
        if (defaultValue !== undefined && defaultValue !== null) {
            titleParts.push(`默认: ${defaultValue}`);
        }
        if (isRequired) titleParts.push('必填');
        if (isPrimaryKey) titleParts.push(isCompositeKey ? '联合主键' : '主键');
        if (isForeignKey) titleParts.push('外键');
        if (isEnum) titleParts.push('枚举');
        if (col.readOnly) titleParts.push('只读');
        if (col.sortable) titleParts.push('点击排序');
        
        return `
            <th 
                style="${col.width ? 'width: ' + col.width + '; min-width: ' + col.width + ';' : 'white-space: nowrap;'}" 
                data-field="${col.field}" 
                class="${col.sortable ? 'sortable' : ''}"
                title="${titleParts.join(' | ')}"
            >
                ${col.title}${requiredIcon}${primaryKeyIcon}${foreignKeyIcon}${enumIcon}${readOnlyIcon}${sortIcon}
            </th>
        `;
    }
    
    /**
     * 渲染表头
     */
    renderHeader() {
        const thead = this.container.querySelector('thead tr');
        if (thead) {
            thead.innerHTML = `
                <th style="width: 40px; min-width: 40px;">
                    <input type="checkbox" class="form-check-input" id="selectAll">
                </th>
                ${this.columns.map(col => this.renderHeaderCell(col)).join('')}
            `;
            this.bindEvents();
        }
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
        
        // 导出选中数据
        const templateBtn = document.getElementById('templateBtn');
        if (templateBtn) {
            templateBtn.addEventListener('click', () => this.exportSelected());
        }
        
        // 页面大小切换
        const pageSizeSelect = document.getElementById('pageSizeSelect');
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', (e) => {
                this.pageSize = parseInt(e.target.value);
                this.currentPage = 1;
                this.clearSelection();
                this.loadData();
            });
        }
        
        // 检查删除权限
        this.checkRemovePermission();
        
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
                this.renderHeader();
                this.clearSelection();
                this.loadData();
            });
        });
    }
    
    /**
     * 处理全选
     * @param {boolean} checked - 是否选中
     */
    handleSelectAll(checked) {
        if (!checked) {
            this.selectedAllPages = false;
        }
        
        document.querySelectorAll('.row-checkbox').forEach(cb => {
            cb.checked = checked;
            const id = parseInt(cb.dataset.id);
            if (checked) {
                this.selectedIds.add(id);
            } else {
                this.selectedIds.delete(id);
            }
        });
        
        // 如果选中了当前页所有记录，且当前页记录数等于总数，则标记为全选
        if (checked && this.data.length === this.total) {
            this.selectedAllPages = true;
        }
        
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
            totalInfo.textContent = typeof i18n !== 'undefined' ? 
                i18n.t('mds.table.total', {count: this.total}) : 
                `共 ${this.total} 条`;
        }
        
        this.updateTotalCount();
        
        if (this.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="${this.columns.length + 1}" class="text-center text-muted py-4">
                        ${typeof i18n !== 'undefined' ? i18n.t('mds.table.noData') : '暂无数据'}
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
                <td style="width: 40px; min-width: 40px; max-width: 40px; white-space: nowrap;">
                    <input 
                        type="checkbox" 
                        class="form-check-input row-checkbox" 
                        data-id="${row._staging_id}"
                        ${isSelected ? 'checked' : ''}
                    >
                </td>
                ${this.columns.map(col => {
                    const cellStyle = col.width 
                        ? 'white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: ' + col.width + ';'
                        : 'white-space: nowrap;';
                    // 状态字段或有错误的字段不设置title，避免覆盖错误提示框
                    const hasError = errorMap[col.field];
                    const cellTitle = (col.field === '_status' || hasError) ? '' : `title="${String(row[col.field] || '').replace(/"/g, '&quot;')}"`;
                    return `<td style="${cellStyle}" ${cellTitle}>${this.renderCell(col, row, errorMap)}</td>`;
                }).join('')}
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
        if (row._status === 'compliance_error') {
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
                // 支持多字段错误高亮（如业务规则涉及多个字段）
                if (err.error_fields && Array.isArray(err.error_fields)) {
                    err.error_fields.forEach(field => {
                        if (!errorMap[field]) {
                            errorMap[field] = { type: err.error_type, message: err.error_message };
                        } else {
                            // 合并多个错误信息
                            errorMap[field].message += ' | ' + err.error_message;
                        }
                    });
                } else if (err.error_field) {
                    if (!errorMap[err.error_field]) {
                        errorMap[err.error_field] = {
                            type: err.error_type,
                            message: err.error_message
                        };
                    } else {
                        // 合并多个错误信息
                        errorMap[err.error_field].message += ' | ' + err.error_message;
                    }
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
            return `<span class="font-mono">${formatDate(value, true)}</span>`;
        }
        
        // 空值处理（包括 null、undefined 和空字符串）
        if (value === null || value === undefined || value === '') {
            return this.renderNullCell(col, errorMap);
        }
        
        // 错误处理 - 优先级最高
        const errorInfo = errorMap[col.field];
        if (errorInfo) {
            return this.renderErrorCell(value, errorInfo, col);
        }
        
        // 枚举字段
        if (this.enumFields.includes(col.field)) {
            return this.renderEnumCell(value, col.field);
        }
        
        // 外键字段
        const isForeignKey = this.foreignKeys.some(fk => fk.field === col.field);
        if (isForeignKey) {
            return this.renderForeignKeyCell(value, col.field);
        }
        
        // 普通文本
        return this.renderTextCell(value, col);
    }
    
    /**
     * 渲染状态单元格
     */
    renderStatusCell(status, row) {
        if (status === 'compliance_error') {
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
        const isRequired = this.requiredFields.includes(col.field);
        const hasDefault = this.fieldDefaults[col.field] !== undefined && this.fieldDefaults[col.field] !== null;
        const showNullBg = isRequired && !hasDefault;
        const errorInfo = errorMap[col.field];
        
        if (errorInfo) {
            return `
                <span 
                    class="error-cell null-cell" 
                    data-error-type="${errorInfo.type}" 
                    data-error-msg="${escapeHtml(errorInfo.message)}"
                ><i class="bi bi-slash-square-fill" style="color:#dc3545"></i></span>
            `;
        }
        
        // 必填字段缺失时使用醒目的红色图标
        if (showNullBg) {
            return '<span class="null-cell"><i class="bi bi-slash-square-fill" style="color:#ff9800"></i></span>';
        }
        
        // 非必填字段使用浅灰色
        return '<span class="text-muted"><i class="bi bi-slash-square-fill" style="color:#bdbdbd"></i></span>';
    }
    
    /**
     * 渲染错误单元格
     */
    renderErrorCell(value, errorInfo, col) {
        const displayValue = typeof value === 'string' && value.length > 30 
            ? truncateText(value, 30) 
            : value;
        
        const isEnumField = this.enumFields.includes(col.field);
        const isForeignKey = this.foreignKeys.some(fk => fk.field === col.field);
        
        if (isEnumField) {
            // 枚举字段错误样式
            return `
                <span class="enum-tag enum-tag-error" data-error-type="${errorInfo.type}" data-error-msg="${escapeHtml(errorInfo.message)}">
                    ${escapeHtml(displayValue)}
                </span>
            `;
        }
        
        if (isForeignKey) {
            // 外键字段错误样式 - 优先级高于外键普通样式
            return `
                <span class="foreign-key-tag foreign-key-tag-error" data-error-type="${errorInfo.type}" data-error-msg="${escapeHtml(errorInfo.message)}">
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
     * 设置外键选项缓存
     * @param {string} fieldName - 字段名
     * @param {Array} options - 选项数组 [{value, label}, ...]
     */
    setForeignKeyOptions(fieldName, options) {
        this.foreignKeyOptions[fieldName] = options;
    }

    /**
     * 渲染外键单元格（所有外键字段在列表中只显示数据库 value）
     */
    renderForeignKeyCell(value, fieldName) {
        // 获取外键配置
        const fkConfig = this.foreignKeys.find(fk => fk.field === fieldName);
        const refTableDisplayName = fkConfig ? fkConfig.refTableDisplayName : '';
        
        // 所有外键字段只显示数据库 value
        return `<span class="foreign-key-tag" title="引用: ${escapeHtml(refTableDisplayName)}">${escapeHtml(value)}</span>`;
    }
    
    /**
     * 渲染文本单元格
     */
    renderTextCell(value, col) {
        if (typeof value === 'string' && value.length > 30) {
            return `
                <span class="font-mono" title="${value.replace(/"/g, '&quot;')}">
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
        
        // 如果已存在 tooltip，先移除避免重复
        if (e.target._tooltip) {
            e.target._tooltip.remove();
            e.target._tooltip = null;
        }
        
        const tooltip = document.createElement('div');
        tooltip.className = 'error-tooltip error-tooltip-wide';
        
        try {
            const errors = JSON.parse(errorJson);
            
            // 按错误类型分组
            const groupedErrors = {};
            errors.forEach(err => {
                const type = err.error_type || 'unknown';
                if (!groupedErrors[type]) {
                    groupedErrors[type] = [];
                }
                groupedErrors[type].push(err);
            });
            
            // 生成分组后的HTML - 错误类型横向排列
            let html = '<div class="error-groups-container">';
            
            Object.keys(groupedErrors).forEach((type, index) => {
                const typeErrors = groupedErrors[type];
                const count = typeErrors.length;
                
                // 错误类型标题（带数量）
                html += `
                    <div class="error-group">
                        <div class="error-group-header">
                            <span class="error-group-type">${type}</span>
                            <span class="error-group-badge">${count}处</span>
                        </div>
                        <div class="error-group-items">
                `;
                
                // 该类型下的具体错误（纵向排列）
                typeErrors.forEach(err => {
                    let fieldHtml = '';
                    if (err.error_fields && Array.isArray(err.error_fields)) {
                        fieldHtml = `<span class="error-field-tag">${err.error_fields.join(', ')}</span>`;
                    } else if (err.error_field) {
                        fieldHtml = `<span class="error-field-tag">${err.error_field}</span>`;
                    }
                    
                    html += `
                        <div class="error-group-item">
                            ${fieldHtml}
                            <span class="error-msg-text">${escapeHtml(err.error_message || '')}</span>
                        </div>
                    `;
                });
                
                html += `
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            tooltip.innerHTML = html;
        } catch (ex) {
            tooltip.innerHTML = `<pre class="error-tooltip-json">${escapeHtml(errorJson)}</pre>`;
        }
        
        document.body.appendChild(tooltip);
        e.target._tooltip = tooltip;
        
        // 智能定位逻辑
        const rect = e.target.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();
        const tooltipWidth = 520; // 加宽以容纳横向排列的错误类型
        const tooltipHeight = tooltipRect.height || 200;
        const gap = 5; // 与触发元素的间距
        
        // 计算水平位置
        let left = rect.left;
        // 如果右侧空间不足，向左展开
        if (left + tooltipWidth > window.innerWidth - 10) {
            left = Math.max(10, window.innerWidth - tooltipWidth - 10);
        }
        
        // 计算垂直位置
        let top;
        const spaceBelow = window.innerHeight - rect.bottom - gap;
        const spaceAbove = rect.top - gap;
        
        // 判断应该向上还是向下展开
        if (spaceBelow >= tooltipHeight || spaceBelow >= spaceAbove) {
            // 向下展开：提示框上缘对齐到触发元素下缘
            top = rect.bottom + gap;
        } else {
            // 向上展开：提示框下缘对齐到触发元素上缘
            top = rect.top - tooltipHeight - 2; // 留2px间隙
        }
        
        // 最终边界检查
        top = Math.max(10, Math.min(top, window.innerHeight - tooltipHeight - 10));
        
        tooltip.style.left = left + 'px';
        tooltip.style.top = top + 'px';
        tooltip.style.display = 'block';
    }
    
    /**
     * 获取错误类型的中文标签
     * @param {string} type - 错误类型
     * @returns {string} 中文标签
     */
        getErrorTypeLabel(type) {
            const labels = {
                'bom_structure_error': 'BOM结构错误',
                'bom_structure_warning': 'BOM结构警告',
                'unit_inconsistency': '单位不一致',
                'fk_not_found': '外键引用缺失',
                'required_field': '必填字段缺失',
                'invalid_enum': '枚举值非法',
                'invalid_type': '类型错误',
                'invalid_range': '数值范围错误',
                'invalid_length': '字符串长度超限',
                'duplicate_key': '主键重复',
                'business_rule': '业务规则违反',
                'process_error': '处理异常'
            };
            return labels[type] || type;
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
        const exportBtnText = document.getElementById('exportBtnText');
        
        if (selectedCount) selectedCount.textContent = count;
        if (selectedCountDup) selectedCountDup.textContent = count;
        if (batchEditBtn) batchEditBtn.disabled = count === 0;
        if (batchDeleteBtn) batchDeleteBtn.disabled = count === 0;
        if (exportBtnText) exportBtnText.textContent = count === 0 ? '导出模板' : `导出(${count})`;
        
        this.updateSelectAllBtn();
        
        if (this.onSelectionChange) {
            this.onSelectionChange(Array.from(this.selectedIds));
        }
    }
    
    /**
     * 更新全选按钮状态
     */
    updateSelectAllBtn() {
        const btn = document.getElementById('selectAllPagesBtn');
        if (!btn) return;
        
        const isAllSelected = this.selectedAllPages || this.selectedIds.size === this.total;
        const selectAllText = typeof i18n !== 'undefined' ? i18n.t('mds.action.selectAll') : '全选';
        const selectedText = typeof i18n !== 'undefined' ? i18n.t('mds.table.selected', {count: this.selectedIds.size}) : `已全选${this.selectedIds.size}条`;
        
        if (isAllSelected && this.selectedIds.size > 0) {
            btn.className = 'btn btn-sm btn-success font-monospace';
            btn.innerHTML = `<i class="bi bi-check-all"></i> ${selectedText}`;
        } else {
            btn.className = 'btn btn-sm btn-outline-success font-monospace';
            btn.innerHTML = `<i class="bi bi-check-all"></i> ${selectAllText}`;
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
        this.updateSelectAllBtn();
    }
    
    /**
     * 全选所有页
     * @returns {Promise<void>}
     */
    async selectAllPages() {
        // 如果已全选，则取消全选
        if (this.selectedAllPages || this.selectedIds.size === this.total) {
            this.clearSelection();
            const cancelMsg = typeof i18n !== 'undefined' ? i18n.t('mds.other.confirm') : '已取消全选';
            showMessage(cancelMsg, 'info');
            return;
        }
        
        if (this.total === 0) {
            showMessage('没有可选择的记录', 'warning');
            return;
        }
        
        // 如果数据量不超过当前页大小，直接选中
        if (this.total <= this.pageSize) {
            this.selectedIds.clear();
            document.querySelectorAll('.row-checkbox').forEach(cb => {
                cb.checked = true;
                this.selectedIds.add(parseInt(cb.dataset.id));
            });
            
            if (this.data.length === this.total) {
                this.selectedAllPages = true;
            }
            
            this.updateSelectedCount();
            showMessage(`已选中 ${this.selectedIds.size} 条记录`, 'success');
            return;
        }
        
        // 数据量超过 1000 条时需要确认（防止误操作导致大量请求）
        if (this.total > 1000) {
            if (!confirm(`确定选中全部 ${this.total} 条记录吗？\n\n数据量较大，获取所有记录可能需要较长时间。`)) {
                return;
            }
        }
        
        // 1000 条以内，直接执行全选（用户已点击全选按钮，说明意图明确）
        showLoading();
        
        try {
            const queryParams = new URLSearchParams({
                page: 1,
                page_size: this.selectAllPageSize,
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
            const errorMsg = typeof i18n !== 'undefined' ? i18n.t('mds.error.queryFailed') : '全选失败';
            showMessage(errorMsg, 'danger');
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
                this.selectedAllPages = false;
                const selectAll = document.getElementById('selectAll');
                if (selectAll) selectAll.checked = false;
                this.updateSelectedCount();
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
     * 获取选中的数据
     * @returns {Promise<Array>} 选中的数据数组
     */
    async getSelectedData() {
        if (this.selectedIds.size === 0) {
            return [];
        }
        
        // 如果选中了所有页，需要获取全部数据
        if (this.selectedAllPages) {
            showLoading();
            try {
                const queryParams = new URLSearchParams({
                    page: 1,
                    page_size: this.selectAllPageSize,
                    sort_field: this.sortField,
                    sort_order: this.sortOrder,
                    ...this.filters
                });
                
                if (this.advancedFilters && this.advancedFilters.length > 0) {
                    queryParams.set('advanced_filters', JSON.stringify(this.advancedFilters));
                }
                
                const response = await callApi(`/list/${this.tableName}?${queryParams}`);
                
                let data = [];
                handleResponse(response, (responseData) => {
                    data = responseData.data.records || [];
                });
                return data;
            } catch (error) {
                console.error('获取数据失败:', error);
                showMessage('获取数据失败', 'danger');
                return [];
            } finally {
                hideLoading();
            }
        }
        
        // 只选中了当前页，直接从this.data中过滤
        return this.data.filter(row => this.selectedIds.has(row._staging_id));
    }
    
    /**
     * 导出选中数据
     */
    async exportSelected() {
        try {
            let selectedData = await this.getSelectedData();
            
            // 从列配置中获取业务字段，保证与表格显示顺序一致
            const businessFields = this.columns
                .filter(col => !col.field.startsWith('_'))
                .map(col => col.field);
            
            if (businessFields.length === 0) {
                showMessage('没有可导出的业务字段', 'warning');
                return;
            }
            
            // 构建字段名到中文列名的映射
            const fieldTitleMap = {};
            this.columns.forEach(col => {
                fieldTitleMap[col.field] = col.title;
            });
            
            // 准备导出数据
            const headers = businessFields.map(field => fieldTitleMap[field]);
            const rows = selectedData.map(row => {
                return businessFields.map(field => this.getExportValue(field, row[field], row));
            });
            
            // 生成本地时间戳
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hour = String(now.getHours()).padStart(2, '0');
            const minute = String(now.getMinutes()).padStart(2, '0');
            const second = String(now.getSeconds()).padStart(2, '0');
            const timestamp = `${year}${month}${day}_${hour}${minute}${second}`;
            
            // 估算数据大小，超过1MB用CSV，否则用XLSX
            const estimatedSize = this.estimateExportSize(headers, rows);
            const useCSV = estimatedSize > 1024 * 1024;
            
            if (useCSV) {
                this.downloadAsCSV(headers, rows, timestamp);
            } else {
                this.downloadAsExcel(headers, rows, timestamp);
            }
            
            if (selectedData.length > 0) {
                showMessage(`成功导出 ${selectedData.length} 条数据`, 'success');
            } else {
                showMessage('已导出模板文件', 'success');
            }
        } catch (error) {
            console.error('导出失败:', error);
            showMessage('导出失败: ' + error.message, 'danger');
        }
    }
    
    /**
     * 估算导出数据大小
     */
    estimateExportSize(headers, rows) {
        let size = headers.join(',').length + 1;
        for (let i = 0; i < Math.min(rows.length, 100); i++) {
            size += rows[i].join(',').length + 1;
        }
        return size * (rows.length / Math.min(rows.length, 100));
    }
    
    /**
     * 下载为CSV文件
     */
    downloadAsCSV(headers, rows, timestamp) {
        let csvContent = '\ufeff' + headers.join(',') + '\n';
        rows.forEach(row => {
            csvContent += row.map(v => this.formatCsvValue(v)).join(',') + '\n';
        });
        
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        this.downloadBlob(blob, `${this.tableName}_export_${timestamp}.csv`);
    }
    
    /**
     * 下载为Excel文件
     */
    downloadAsExcel(headers, rows, timestamp) {
        const wsData = [headers, ...rows];
        const ws = XLSX.utils.aoa_to_sheet(wsData);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
        
        const excelBuffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        const blob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        this.downloadBlob(blob, `${this.tableName}_export_${timestamp}.xlsx`);
    }
    
    /**
     * 下载Blob文件
     */
    downloadBlob(blob, filename) {
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }
    
    /**
     * 获取导出用的显示值
     * 注意：保持原始值以便重新导入，枚举/外键字段不做转换
     * @param {string} field - 字段名
     * @param {*} value - 原始值
     * @param {Object} row - 行数据
     * @returns {*} 显示值
     */
    getExportValue(field, value, row) {
        if (value === null || value === undefined) {
            return '';
        }
        
        if (['_createtime', '_updatetime', '_synced_time'].includes(field)) {
            return formatDate(value, true);
        }
        
        return value;
    }
    
    /**
     * 格式化CSV值（处理逗号、引号、换行符）
     * @param {*} value - 值
     * @returns {string} 格式化后的CSV值
     */
    formatCsvValue(value) {
        if (value === null || value === undefined) {
            return '';
        }
        
        let strValue = String(value);
        
        // 如果包含逗号、引号或换行符，需要用引号包裹并转义
        if (strValue.includes(',') || strValue.includes('"') || strValue.includes('\n') || strValue.includes('\r')) {
            // 转义引号（双引号变两个双引号）
            strValue = strValue.replace(/"/g, '""');
            // 移除换行符（或替换为空格）
            strValue = strValue.replace(/[\r\n]+/g, ' ');
            // 用引号包裹
            strValue = '"' + strValue + '"';
        }
        
        return strValue;
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
     * 检查删除权限并控制按钮显示
     */
    checkRemovePermission() {
        // 从全局配置中获取删除模式（由后端模板注入）
        if (typeof MDS_PAGE_CONFIG !== 'undefined' && MDS_PAGE_CONFIG) {
            const { removeMode, removeAllowed } = MDS_PAGE_CONFIG;
            
            // 控制批量删除按钮
            const batchDeleteBtn = document.getElementById('batchDeleteBtn');
            if (batchDeleteBtn) {
                if (removeAllowed === false) {
                    batchDeleteBtn.style.display = 'none';
                } else {
                    batchDeleteBtn.style.display = '';
                }
            }
            
            // 保存删除模式到实例
            this.removeMode = removeMode;
            this.removeAllowed = removeAllowed;
        } else {
            // 配置未注入时的默认行为
            console.warn('MDS_PAGE_CONFIG未定义，删除权限检查失败');
            this.removeAllowed = true;  // 默认允许
        }
    }
    
    /**
     * 销毁组件
     */
    destroy() {
        // 清除所有 tooltip
        document.querySelectorAll('.error-tooltip, .error-tooltip-wide').forEach(el => el.remove());
        
        // 清除选中状态
        this.selectedIds.clear();
        
        // 清空容器（会自动移除大部分事件监听器）
        this.container.innerHTML = '';
        
        // 清空数据引用
        this.data = [];
        this.columns = [];
    }
}
