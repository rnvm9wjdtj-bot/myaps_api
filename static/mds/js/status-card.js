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
        this.bindLanguageChangeListener();
    }
    
    /**
     * 监听语言切换事件
     */
    bindLanguageChangeListener() {
        window.addEventListener('languageChanged', () => {
            this.render();
        });
    }
    
    /**
     * 渲染状态卡片
     */
    render() {
        const labels = {
            all: typeof i18n !== 'undefined' ? i18n.t('mds.status.all') : '全部',
            pending: STAGING_STATUS.PENDING.label,
            compliancePass: STAGING_STATUS.COMPLIANCE_PASS.label,
            complianceError: STAGING_STATUS.COMPLIANCE_ERROR.label,
            relationPass: STAGING_STATUS.RELATION_PASS.label,
            relationError: STAGING_STATUS.RELATION_ERROR.label,
            syncError: STAGING_STATUS.SYNC_ERROR.label,
            synced: STAGING_STATUS.SYNCED.label
        };
        
        this.container.innerHTML = `
            <div class="row g-2">
                <div class="col">
                    <div class="card status-card active" data-status="">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #191919;" id="statusTotalCount">-</div>
                            <div class="status-label">${labels.all}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="pending">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #9e9e9e;" id="pendingCount">-</div>
                            <div class="status-label">${labels.pending}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="compliance_pass">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #00c345;" id="compliancePassCount">-</div>
                            <div class="status-label">${labels.compliancePass}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="compliance_error">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #ff9300;" id="complianceErrorCount">-</div>
                            <div class="status-label">${labels.complianceError}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="relation_pass">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #1677ff;" id="relationPassCount">-</div>
                            <div class="status-label">${labels.relationPass}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="relation_error">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #f52222;" id="relationErrorCount">-</div>
                            <div class="status-label">${labels.relationError}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="sync_error">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #eb2f96;" id="syncErrorCount">-</div>
                            <div class="status-label">${labels.syncError}</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="synced">
                        <div class="card-body text-center">
                            <div class="status-number" style="color: #7500ea;" id="syncedCount">-</div>
                            <div class="status-label">${labels.synced}</div>
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
        document.getElementById('statusTotalCount').textContent = total;
        
        // 更新各状态计数
        const statusMappings = [
            { status: 'pending', elementId: 'pendingCount' },
            { status: 'compliance_pass', elementId: 'compliancePassCount' },
            { status: 'compliance_error', elementId: 'complianceErrorCount' },
            { status: 'relation_pass', elementId: 'relationPassCount' },
            { status: 'relation_error', elementId: 'relationErrorCount' },
            { status: 'sync_error', elementId: 'syncErrorCount' },
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
        return this.stats.total 
            || this.getStatusCount('pending') 
                + this.getStatusCount('compliance_pass') 
                + this.getStatusCount('compliance_error') 
                + this.getStatusCount('relation_pass') 
                + this.getStatusCount('relation_error') 
                + this.getStatusCount('sync_error')
                + this.getStatusCount('synced');
    }
    
    /**
     * 获取指定状态的计数
     * @param {string} status - 状态值
     * @returns {number} 计数值
     */
    getStatusCount(status) {
        return this.stats[status] || 0;
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
            if (status === 'compliance_error' || status === 'relation_error' || status === 'sync_error') {
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
     * 手动刷新（重新渲染和加载数据）
     */
    refresh() {
        this.render();
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
     * 获取可推送数量（联合校验通过 + 同步失败）
     * @returns {number} 可推送数量
     */
    getReadyToSyncCount() {
        return this.getStatusCount('relation_pass') + this.getStatusCount('sync_error');
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
