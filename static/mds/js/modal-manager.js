/**
 * @file modal-manager.js
 * @description 模态框管理器组件 - 统一管理弹窗的打开、关闭、数据传递
 * @author Frontend Team
 * @version 1.0.0
 * @date 2026-05-14
 */

class ModalManager {
    constructor() {
        this.modals = {};
        this.activeModal = null;
        this.backdropCount = 0;
    }
    
    /**
     * 注册模态框
     * @param {string} name - 模态框名称
     * @param {Object} config - 模态框配置
     */
    register(name, config) {
        this.modals[name] = {
            id: config.id || `modal_${name}`,
            title: config.title || '',
            size: config.size || 'md',
            backdrop: config.backdrop !== undefined ? config.backdrop : true,
            keyboard: config.keyboard !== undefined ? config.keyboard : true,
            centered: config.centered !== undefined ? config.centered : true,
            body: config.body || '',
            footer: config.footer || this.getDefaultFooter(),
            onOpen: config.onOpen,
            onClose: config.onClose,
            onConfirm: config.onConfirm,
            onCancel: config.onCancel
        };
    }
    
    /**
     * 获取默认底部按钮
     * @returns {string} HTML字符串
     */
    getDefaultFooter() {
        return `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-primary" id="modalConfirmBtn">确定</button>
        `;
    }
    
    /**
     * 打开模态框
     * @param {string} name - 模态框名称
     * @param {Object} [data] - 传递给模态框的数据
     * @returns {Promise<any>} 关闭时返回的数据
     */
    open(name, data = {}) {
        return new Promise((resolve, reject) => {
            const config = this.modals[name];
            if (!config) {
                reject(new Error(`未注册的模态框: ${name}`));
                return;
            }
            
            this.activeModal = name;
            
            // 生成唯一ID防止冲突
            const modalId = config.id;
            
            // 创建模态框HTML
            const modalHtml = this.generateModalHtml(modalId, config, data);
            
            // 添加到DOM
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            
            // 获取模态框元素
            const modalElement = document.getElementById(modalId);
            
            // 绑定事件
            this.bindModalEvents(modalElement, config, resolve, reject, data);
            
            // 显示模态框
            const modal = new bootstrap.Modal(modalElement, {
                backdrop: config.backdrop,
                keyboard: config.keyboard
            });
            modal.show();
            
            // 存储模态框实例
            modalElement._bsModal = modal;
            
            // 触发onOpen回调
            if (config.onOpen) {
                config.onOpen(data, modalElement);
            }
        });
    }
    
    /**
     * 生成模态框HTML
     * @param {string} modalId - 模态框ID
     * @param {Object} config - 模态框配置
     * @param {Object} data - 传递的数据
     * @returns {string} HTML字符串
     */
    generateModalHtml(modalId, config, data) {
        const sizeClass = this.getSizeClass(config.size);
        const centeredClass = config.centered ? 'modal-dialog-centered' : '';
        
        // 处理body - 支持函数或字符串
        let bodyContent = config.body;
        if (typeof config.body === 'function') {
            bodyContent = config.body(data);
        }
        
        return `
            <div class="modal fade" id="${modalId}" tabindex="-1" role="dialog" aria-hidden="true">
                <div class="modal-dialog ${sizeClass} ${centeredClass}" role="document">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${config.title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body" id="${modalId}_body">
                            ${bodyContent}
                        </div>
                        ${config.footer ? `
                            <div class="modal-footer" id="${modalId}_footer">
                                ${typeof config.footer === 'function' ? config.footer(data) : config.footer}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * 获取尺寸类名
     * @param {string} size - 尺寸类型
     * @returns {string} 类名字符串
     */
    getSizeClass(size) {
        const sizeMap = {
            'sm': 'modal-sm',
            'md': '',
            'lg': 'modal-lg',
            'xl': 'modal-xl',
            'full': 'modal-fullscreen'
        };
        return sizeMap[size] || '';
    }
    
    /**
     * 绑定模态框事件
     * @param {HTMLElement} modalElement - 模态框元素
     * @param {Object} config - 模态框配置
     * @param {Function} resolve - Promise resolve函数
     * @param {Function} reject - Promise reject函数
     * @param {Object} data - 传递的数据
     */
    bindModalEvents(modalElement, config, resolve, reject, data) {
        const modalId = modalElement.id;
        
        // 监听关闭事件
        modalElement.addEventListener('hidden.bs.modal', (e) => {
            // 判断关闭原因
            const closeReason = e.target._closeReason || 'cancel';
            
            // 触发onClose回调
            if (config.onClose) {
                config.onClose(closeReason, data);
            }
            
            // 清理DOM
            setTimeout(() => {
                if (modalElement.parentNode) {
                    modalElement.parentNode.removeChild(modalElement);
                }
            }, 100);
            
            // 重置激活状态
            this.activeModal = null;
            
            // 处理Promise
            if (closeReason === 'confirm') {
                const result = e.target._modalResult;
                resolve(result);
            } else if (closeReason === 'error') {
                reject(e.target._modalError);
            } else {
                // 取消或其他原因，resolve为空
                resolve(null);
            }
        });
        
        // 绑定确定按钮
        const confirmBtn = modalElement.querySelector('#modalConfirmBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => {
                this.handleConfirm(modalElement, config, data);
            });
        }
        
        // 绑定取消按钮
        const cancelBtn = modalElement.querySelector('[data-bs-dismiss="modal"]');
        if (cancelBtn && cancelBtn !== confirmBtn) {
            cancelBtn.addEventListener('click', () => {
                if (config.onCancel) {
                    config.onCancel(data);
                }
            });
        }
    }
    
    /**
     * 处理确定按钮点击
     * @param {HTMLElement} modalElement - 模态框元素
     * @param {Object} config - 模态框配置
     * @param {Object} data - 传递的数据
     */
    handleConfirm(modalElement, config, data) {
        // 获取表单数据（如果有表单）
        const form = modalElement.querySelector('form');
        let resultData = data;
        
        if (form) {
            resultData = this.collectFormData(form);
            // 合并原始数据
            resultData = { ...data, ...resultData };
        }
        
        // 触发onConfirm回调
        if (config.onConfirm) {
            const confirmResult = config.onConfirm(resultData, modalElement);
            
            // 支持异步回调
            if (confirmResult instanceof Promise) {
                confirmResult.then((result) => {
                    this.closeModal(modalElement, 'confirm', result);
                }).catch((error) => {
                    this.closeModal(modalElement, 'error', error);
                });
            } else if (confirmResult !== false) {
                // 返回false阻止关闭
                this.closeModal(modalElement, 'confirm', confirmResult || resultData);
            }
        } else {
            this.closeModal(modalElement, 'confirm', resultData);
        }
    }
    
    /**
     * 收集表单数据
     * @param {HTMLFormElement} form - 表单元素
     * @returns {Object} 表单数据
     */
    collectFormData(form) {
        const data = {};
        const formData = new FormData(form);
        
        formData.forEach((value, key) => {
            // 处理数组字段
            if (key.endsWith('[]')) {
                const fieldName = key.slice(0, -2);
                if (!data[fieldName]) {
                    data[fieldName] = [];
                }
                data[fieldName].push(value);
            } else {
                data[key] = value;
            }
        });
        
        return data;
    }
    
    /**
     * 关闭模态框
     * @param {HTMLElement} modalElement - 模态框元素
     * @param {string} reason - 关闭原因
     * @param {any} result - 返回结果
     */
    closeModal(modalElement, reason, result) {
        modalElement._closeReason = reason;
        modalElement._modalResult = result;
        
        const modal = modalElement._bsModal;
        if (modal) {
            modal.hide();
        }
    }
    
    /**
     * 关闭当前激活的模态框
     * @param {string} [reason='cancel'] - 关闭原因
     * @param {any} [result] - 返回结果
     */
    closeActive(reason = 'cancel', result) {
        if (this.activeModal) {
            const config = this.modals[this.activeModal];
            if (config) {
                const modalElement = document.getElementById(config.id);
                if (modalElement) {
                    this.closeModal(modalElement, reason, result);
                }
            }
        }
    }
    
    /**
     * 打开一个简单的确认对话框
     * @param {string} message - 提示消息
     * @param {Object} [options] - 选项
     * @returns {Promise<boolean>} 是否确认
     */
    confirm(message, options = {}) {
        const config = {
            id: 'confirmModal',
            title: options.title || '确认',
            size: options.size || 'sm',
            body: `<div class="mb-2">${message}</div>`,
            onConfirm: () => true
        };
        
        return this.open('confirm', {}).then((result) => {
            return result !== null;
        });
    }
    
    /**
     * 打开一个简单的提示对话框
     * @param {string} message - 提示消息
     * @param {Object} [options] - 选项
     * @returns {Promise<void>}
     */
    alert(message, options = {}) {
        const config = {
            id: 'alertModal',
            title: options.title || '提示',
            size: options.size || 'sm',
            body: `<div class="mb-2">${message}</div>`,
            footer: '<button type="button" class="btn btn-primary" data-bs-dismiss="modal">确定</button>'
        };
        
        return this.open('alert', {});
    }
    
    /**
     * 打开一个带输入的对话框
     * @param {string} message - 提示消息
     * @param {Object} [options] - 选项
     * @returns {Promise<string|null>} 用户输入的值
     */
    prompt(message, options = {}) {
        const defaultValue = options.defaultValue || '';
        const placeholder = options.placeholder || '';
        const required = options.required || false;
        
        return new Promise((resolve) => {
            const config = {
                id: 'promptModal',
                title: options.title || '输入',
                size: options.size || 'md',
                body: `
                    <div class="mb-2">${message}</div>
                    <input 
                        type="text" 
                        class="form-control" 
                        id="promptInput" 
                        value="${defaultValue}" 
                        placeholder="${placeholder}"
                        ${required ? 'required' : ''}
                    >
                `,
                onConfirm: (data, modalElement) => {
                    const input = modalElement.querySelector('#promptInput');
                    const value = input ? input.value.trim() : '';
                    
                    if (required && !value) {
                        showMessage('请输入内容', 'warning');
                        return false;
                    }
                    
                    return value;
                }
            };
            
            this.open('prompt', {}).then((result) => {
                resolve(result);
            });
        });
    }
    
    /**
     * 打开一个加载对话框
     * @param {string} [message='加载中...'] - 加载消息
     * @returns {Function} 关闭函数
     */
    loading(message = '加载中...') {
        const config = {
            id: 'loadingModal',
            title: '',
            size: 'sm',
            backdrop: 'static',
            keyboard: false,
            centered: true,
            body: `
                <div class="text-center py-4">
                    <div class="spinner-border text-primary" role="status" style="width: 2rem; height: 2rem;">
                        <span class="visually-hidden">加载中...</span>
                    </div>
                    <div class="mt-2 text-muted">${message}</div>
                </div>
            `,
            footer: ''
        };
        
        let closeFn;
        const closePromise = new Promise((resolve) => {
            closeFn = () => {
                this.closeActive('confirm');
                resolve();
            };
        });
        
        this.open('loading', {});
        
        return closeFn;
    }
    
    /**
     * 显示消息对话框（基于bootstrap-toast）
     * @param {string} message - 消息内容
     * @param {string} [type='info'] - 消息类型
     * @param {Object} [options] - 选项
     */
    toast(message, type = 'info', options = {}) {
        const iconClass = this.getToastIcon(type);
        const bgClass = this.getToastBgClass(type);
        const delay = options.delay || 3000;
        
        // 创建toast容器
        const toastContainer = document.getElementById('toastContainer') || this.createToastContainer();
        
        // 创建toast元素
        const toastId = `toast_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const toastElement = document.createElement('div');
        toastElement.className = `toast ${bgClass} text-white border-0`;
        toastElement.id = toastId;
        toastElement.setAttribute('role', 'alert');
        toastElement.setAttribute('aria-live', 'assertive');
        toastElement.setAttribute('aria-atomic', 'true');
        
        toastElement.innerHTML = `
            <div class="d-flex">
                <div class="toast-body d-flex align-items-center gap-2">
                    <i class="${iconClass}" style="font-size: 1.2rem;"></i>
                    <span>${message}</span>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;
        
        toastContainer.appendChild(toastElement);
        
        // 初始化并显示
        const toast = new bootstrap.Toast(toastElement, { delay });
        toast.show();
        
        // 自动清理
        toastElement.addEventListener('hidden.bs.toast', () => {
            if (toastElement.parentNode) {
                toastElement.parentNode.removeChild(toastElement);
            }
        });
    }
    
    /**
     * 创建toast容器
     * @returns {HTMLElement} 容器元素
     */
    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = 9999;
        document.body.appendChild(container);
        return container;
    }
    
    /**
     * 获取toast图标类
     * @param {string} type - 消息类型
     * @returns {string} 图标类名
     */
    getToastIcon(type) {
        const iconMap = {
            'success': 'bi bi-check-circle-fill',
            'error': 'bi bi-x-circle-fill',
            'danger': 'bi bi-x-circle-fill',
            'warning': 'bi bi-exclamation-triangle-fill',
            'info': 'bi bi-info-circle-fill'
        };
        return iconMap[type] || iconMap['info'];
    }
    
    /**
     * 获取toast背景类
     * @param {string} type - 消息类型
     * @returns {string} 背景类名
     */
    getToastBgClass(type) {
        const bgMap = {
            'success': 'bg-success',
            'error': 'bg-danger',
            'danger': 'bg-danger',
            'warning': 'bg-warning',
            'info': 'bg-info'
        };
        return bgMap[type] || bgMap['info'];
    }
    
    /**
     * 检查是否有模态框正在显示
     * @returns {boolean} 是否有活动模态框
     */
    hasActiveModal() {
        return this.activeModal !== null;
    }
    
    /**
     * 获取当前活动的模态框名称
     * @returns {string|null} 模态框名称
     */
    getActiveModal() {
        return this.activeModal;
    }
    
    /**
     * 销毁所有模态框
     */
    destroyAll() {
        Object.keys(this.modals).forEach(name => {
            const config = this.modals[name];
            const modalElement = document.getElementById(config.id);
            if (modalElement) {
                const modal = modalElement._bsModal;
                if (modal) {
                    modal.hide();
                }
                setTimeout(() => {
                    if (modalElement.parentNode) {
                        modalElement.parentNode.removeChild(modalElement);
                    }
                }, 100);
            }
        });
        
        this.modals = {};
        this.activeModal = null;
    }
}

// 创建全局实例
const modalManager = new ModalManager();
