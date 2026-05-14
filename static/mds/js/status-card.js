/**
 * @file status-card.js
 * @description 状态统计卡片组件 - 支持6种状态、趋势展示、点击筛选
 * @author Frontend Team
 * @version 1.1.0
 * @date 2026-05-14
 * @requires ./common.js
 */

class StatusCard {
    constructor(config) {
        this.tableName = config.tableName;
        this.container = config.container || document.getElementById('statusCardContainer');
        this.onStatusClick = config.onStatusClick;
        this.activeStatus = null;
        this.stats = {};
        this.refreshInterval = null;
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadStats();
        this.startAutoRefresh();
    }
    
    /**
     * 渲染状态卡片
     */
    render() {
        this.container.innerHTML = `
            <div class="row g-2">
                <div class="col">
                    <div class="card status-card active" data-status="">
                        <div class="card-body text-center">
                            <div class="status-number text-primary" id="totalCount">-</div>
                            <div class="status-label">全部</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="pending">
                        <div class="card-body text-center">
                            <div class="status-number text-muted" id="pendingCount">-</div>
                            <div class="status-label">待处理</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="compliance_pass">
                        <div class="card-body text-center">
                            <div class="status-number text-info" id="compliancePassCount">-</div>
                            <div class="status-label">合规通过</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="compliance_error">
                        <div class="card-body text-center">
                            <div class="status-number text-danger" id="complianceErrorCount">-</div>
                            <div class="status-label">合规错误</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="relation_pass">
                        <div class="card-body text-center">
                            <div class="status-number text-success" id="relationPassCount">-</div>
                            <div class="status-label">关联通过</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="relation_error">
                        <div class="card-body text-center">
                            <div class="status-number text-warning" id="relationErrorCount">-</div>
                            <div class="status-label">关联错误</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="synced">
                        <div class="card-body text-center">
                            <div class="status-number text-secondary" id="syncedCount">-</div>
                            <div class="status-label">已推送</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.bindEvents();
        this.activeStatus = '';
    }
    
    /**
     * 绑定点击事件
     */
    bindEvents() {
        this.container.querySelectorAll('.status-card').forEach(card => {
            card.addEventListener('click', () => {
                const status = card.dataset.status;
                
                if (this.activeStatus === status) {
                    this.activeStatus = null;
                    card.classList.remove('active');
                    if (this.onStatusClick) {
                        this.onStatusClick(null);
                    }
                } else {
                    this.container.querySelectorAll('.status-card').forEach(c => c.classList.remove('active'));
                    card.classList.add('active');
                    this.activeStatus = status;
                    
                    if (this.onStatusClick) {
                        this.onStatusClick(status);
                    }
                }
            });
        });
    }
    
    /**
     * 加载状态统计数据
     * @returns {Promise<void>}
     */
    async loadStats() {
        const response = await callApi(`/status/${this.tableName}`);
        
        handleResponse(response, (data) => {
            this.stats = data.data || {};
            this.updateDisplay();
        });
    }
    
    /**
     * 更新显示数据
     */
    updateDisplay() {
        // 计算总数
        const total = this.calculateTotal();
        document.getElementById('totalCount').textContent = total;
        
        // 更新各状态计数
        const statusMappings = [
            { status: 'pending', elementId: 'pendingCount' },
            { status: 'compliance_pass', elementId: 'compliancePassCount' },
            { status: 'compliance_error', elementId: 'complianceErrorCount' },
            { status: 'relation_pass', elementId: 'relationPassCount' },
            { status: 'relation_error', elementId: 'relationErrorCount' },
            { status: 'synced', elementId: 'syncedCount' }
        ];
        
        for (const mapping of statusMappings) {
            const element = document.getElementById(mapping.elementId);
            if (element) {
                const count = this.getStatusCount(mapping.status);
                element.textContent = count;
                
                // 根据数量添加特殊样式
                if (count > 0) {
                    element.classList.add('status-highlight');
                } else {
                    element.classList.remove('status-highlight');
                }
            }
        }
        
        // 更新卡片视觉反馈
        this.updateCardVisualFeedback();
    }
    
    /**
     * 计算总数
     * @returns {number} 总数
     */
    calculateTotal() {
        return Object.values(STATUS_COLORS).reduce((sum, _) => sum, 0)
            || this.stats.total 
            || this.getStatusCount('pending') 
                + this.getStatusCount('compliance_pass') 
                + this.getStatusCount('compliance_error') 
                + this.getStatusCount('relation_pass') 
                + this.getStatusCount('relation_error') 
                + this.getStatusCount('synced');
    }
    
    /**
     * 获取指定状态的计数
     * @param {string} status - 状态值
     * @returns {number} 计数值
     */
    getStatusCount(status) {
        // 优先从stats获取
        if (this.stats[status] !== undefined) {
            return this.stats[status];
        }
        
        // 兼容旧状态命名
        const legacyMap = {
            'relation_pass': this.stats.validated,
            'compliance_error': this.stats.rejected
        };
        
        return legacyMap[status] || 0;
    }
    
    /**
     * 更新卡片视觉反馈
     */
    updateCardVisualFeedback() {
        this.container.querySelectorAll('.status-card').forEach(card => {
            const status = card.dataset.status;
            const numberElement = card.querySelector('.status-number');
            const count = parseInt(numberElement.textContent) || 0;
            
            // 根据状态和数量添加视觉反馈
            if (status === 'compliance_error' || status === 'relation_error') {
                if (count > 0) {
                    card.classList.add('status-card-error');
                } else {
                    card.classList.remove('status-card-error');
                }
            }
        });
    }
    
    /**
     * 开始自动刷新
     */
    startAutoRefresh() {
        // 每30秒自动刷新一次
        this.refreshInterval = setInterval(() => {
            this.loadStats();
        }, 30000);
    }
    
    /**
     * 停止自动刷新
     */
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    /**
     * 手动刷新
     */
    refresh() {
        this.loadStats();
    }
    
    /**
     * 设置激活状态
     * @param {string|null} status - 状态值
     */
    setActiveStatus(status) {
        this.activeStatus = status;
        this.container.querySelectorAll('.status-card').forEach(card => {
            if (card.dataset.status === status) {
                card.classList.add('active');
            } else {
                card.classList.remove('active');
            }
        });
    }
    
    /**
     * 获取统计数据
     * @returns {Object} 统计数据
     */
    getStats() {
        return this.stats;
    }
    
    /**
     * 获取可推送数量
     * @returns {number} 可推送数量
     */
    getReadyToSyncCount() {
        return this.getStatusCount('relation_pass');
    }
    
    /**
     * 获取待处理数量
     * @returns {number} 待处理数量
     */
    getPendingCount() {
        return this.getStatusCount('pending');
    }
    
    /**
     * 销毁组件
     */
    destroy() {
        this.stopAutoRefresh();
        if (this.container) {
            this.container.innerHTML = '';
        }
    }
}
