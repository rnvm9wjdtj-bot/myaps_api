/**
 * @file form-renderer.js
 * @description 配置化表单渲染组件 - 根据字段配置自动生成表单
 * @author Frontend Team
 * @version 1.0.0
 * @date 2026-05-14
 * @requires ./common.js
 */

class FormRenderer {
    constructor(config) {
        this.container = config.container;
        this.fields = config.fields || [];
        this.data = config.data || {};
        this.enumOptions = config.enumOptions || {};
        this.requiredFields = config.requiredFields || [];
        this.fieldLabels = config.fieldLabels || {};
        this.onFieldChange = config.onFieldChange;
        this.readonly = config.readonly || false;
        
        this.init();
    }
    
    init() {
        this.render();
        this.bindEvents();
    }
    
    /**
     * 渲染表单
     */
    render() {
        if (!this.container) return;
        
        const html = this.fields.map(field => this.renderField(field)).join('');
        this.container.innerHTML = html;
    }
    
    /**
     * 渲染单个字段
     * @param {Object} fieldConfig - 字段配置
     * @returns {string} HTML字符串
     */
    renderField(fieldConfig) {
        const { field, type = 'text', title, options, required, readonly, placeholder, className } = fieldConfig;
        const value = this.data[field] !== null && this.data[field] !== undefined ? this.data[field] : '';
        const isRequired = required || this.requiredFields.includes(field);
        const isReadonly = readonly || this.readonly;
        const label = title || this.fieldLabels[field] || field;
        
        const labelHtml = `
            <label class="form-label mb-1">
                ${label}${isRequired ? '<span class="text-danger">*</span>' : ''}
            </label>
        `;
        
        let inputHtml = '';
        
        switch (type) {
            case 'select':
                inputHtml = this.renderSelect(field, value, options, isRequired, isReadonly, placeholder);
                break;
            case 'textarea':
                inputHtml = this.renderTextarea(field, value, isRequired, isReadonly, placeholder, className);
                break;
            case 'number':
                inputHtml = this.renderNumber(field, value, isRequired, isReadonly, placeholder);
                break;
            case 'date':
                inputHtml = this.renderDate(field, value, isRequired, isReadonly, placeholder);
                break;
            case 'checkbox':
                inputHtml = this.renderCheckbox(field, value, isReadonly, title);
                break;
            case 'enum':
                inputHtml = this.renderEnumSelect(field, value, isRequired, isReadonly);
                break;
            default:
                inputHtml = this.renderText(field, value, isRequired, isReadonly, placeholder, className);
        }
        
        return `
            <div class="mb-2 form-field-wrapper" data-field="${field}">
                ${type !== 'checkbox' ? labelHtml : ''}
                ${inputHtml}
            </div>
        `;
    }
    
    /**
     * 渲染文本输入框
     */
    renderText(field, value, required, readonly, placeholder, className) {
        return `
            <input 
                type="text" 
                class="form-control font-mono ${className || ''}" 
                name="${field}" 
                id="field_${field}"
                value="${escapeHtml(String(value))}"
                ${required ? 'required' : ''}
                ${readonly ? 'readonly' : ''}
                placeholder="${placeholder || ''}"
            >
        `;
    }
    
    /**
     * 渲染数字输入框
     */
    renderNumber(field, value, required, readonly, placeholder) {
        return `
            <input 
                type="number" 
                class="form-control font-mono" 
                name="${field}" 
                id="field_${field}"
                value="${value || ''}"
                ${required ? 'required' : ''}
                ${readonly ? 'readonly' : ''}
                placeholder="${placeholder || ''}"
            >
        `;
    }
    
    /**
     * 渲染日期输入框
     */
    renderDate(field, value, required, readonly, placeholder) {
        return `
            <input 
                type="date" 
                class="form-control font-mono" 
                name="${field}" 
                id="field_${field}"
                value="${value || ''}"
                ${required ? 'required' : ''}
                ${readonly ? 'readonly' : ''}
                placeholder="${placeholder || ''}"
            >
        `;
    }
    
    /**
     * 渲染多行文本框
     */
    renderTextarea(field, value, required, readonly, placeholder, className) {
        return `
            <textarea 
                class="form-control font-mono ${className || ''}" 
                name="${field}" 
                id="field_${field}"
                rows="3"
                ${required ? 'required' : ''}
                ${readonly ? 'readonly' : ''}
                placeholder="${placeholder || ''}"
            >${escapeHtml(String(value))}</textarea>
        `;
    }
    
    /**
     * 渲染下拉选择框
     */
    renderSelect(field, value, options, required, readonly, placeholder) {
        const optionHtml = options ? options.map(opt => `
            <option value="${opt.value}" ${String(value) === String(opt.value) ? 'selected' : ''}>
                ${opt.label || opt.value}
            </option>
        `).join('') : '';
        
        return `
            <select 
                class="form-select font-mono" 
                name="${field}" 
                id="field_${field}"
                ${required ? 'required' : ''}
                ${readonly ? 'disabled' : ''}
            >
                <option value="">${placeholder || '-- 请选择 --'}</option>
                ${optionHtml}
            </select>
        `;
    }
    
    /**
     * 渲染枚举选择框
     */
    renderEnumSelect(field, value, required, readonly) {
        const options = this.enumOptions[field] || [];
        return this.renderSelect(field, value, options, required, readonly, '-- 请选择 --');
    }
    
    /**
     * 渲染复选框
     */
    renderCheckbox(field, value, readonly, title) {
        const isChecked = value === true || value === 'true' || value === '1' || value === 1;
        return `
            <div class="form-check">
                <input 
                    type="checkbox" 
                    class="form-check-input" 
                    name="${field}" 
                    id="field_${field}"
                    ${isChecked ? 'checked' : ''}
                    ${readonly ? 'disabled' : ''}
                >
                <label class="form-check-label" for="field_${field}">
                    ${title || this.fieldLabels[field] || field}
                </label>
            </div>
        `;
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        if (this.onFieldChange) {
            this.container.querySelectorAll('input, select, textarea').forEach(input => {
                input.addEventListener('change', (e) => {
                    this.onFieldChange({
                        field: e.target.name,
                        value: e.target.type === 'checkbox' ? e.target.checked : e.target.value
                    });
                });
            });
        }
    }
    
    /**
     * 设置表单数据
     * @param {Object} data - 数据对象
     */
    setData(data) {
        this.data = data;
        this.render();
    }
    
    /**
     * 获取表单数据
     * @returns {Object} 表单数据
     */
    getData() {
        const data = {};
        const formData = new FormData(this.container);
        
        formData.forEach((value, key) => {
            if (value === '') {
                data[key] = null;
            } else {
                // 尝试转换数字类型
                const numValue = parseFloat(value);
                if (!isNaN(numValue)) {
                    data[key] = numValue;
                } else {
                    data[key] = value;
                }
            }
        });
        
        return data;
    }
    
    /**
     * 验证表单
     * @returns {Object} 验证结果
     */
    validate() {
        const errors = [];
        
        this.requiredFields.forEach(field => {
            const input = this.container.querySelector(`[name="${field}"]`);
            if (input) {
                const value = input.type === 'checkbox' ? input.checked : input.value;
                if (!value) {
                    errors.push({
                        field: field,
                        message: `${this.fieldLabels[field] || field} 是必填字段`
                    });
                }
            }
        });
        
        return {
            isValid: errors.length === 0,
            errors: errors
        };
    }
    
    /**
     * 添加字段
     * @param {Object} fieldConfig - 字段配置
     */
    addField(fieldConfig) {
        if (!this.fields.find(f => f.field === fieldConfig.field)) {
            this.fields.push(fieldConfig);
            this.render();
        }
    }
    
    /**
     * 移除字段
     * @param {string} fieldName - 字段名
     */
    removeField(fieldName) {
        this.fields = this.fields.filter(f => f.field !== fieldName);
        this.render();
    }
    
    /**
     * 设置字段只读状态
     * @param {boolean} readonly - 是否只读
     */
    setReadonly(readonly) {
        this.readonly = readonly;
        this.container.querySelectorAll('input, select, textarea').forEach(input => {
            input.readOnly = readonly;
            if (input.tagName === 'SELECT') {
                input.disabled = readonly;
            }
        });
    }
    
    /**
     * 重置表单
     */
    reset() {
        this.data = {};
        this.render();
    }
}
