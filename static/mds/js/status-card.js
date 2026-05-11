/**
 * 状态统计卡片组件
 */

class StatusCard {
    constructor(config) {
        this.tableName = config.tableName;
        this.container = config.container || document.getElementById('statusCardContainer');
        this.onStatusClick = config.onStatusClick;
        this.activeStatus = null;
        this.stats = {};
        
        this.init();
    }
    
    init() {
        this.render();
        this.loadStats();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="row g-3">
                <div class="col-md-3">
                    <div class="card status-card" data-status="pending">
                        <div class="card-body text-center">
                            <div class="status-number text-warning" id="pendingCount">-</div>
                            <div class="status-label">待处理</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card status-card" data-status="validated">
                        <div class="card-body text-center">
                            <div class="status-number text-success" id="validatedCount">-</div>
                            <div class="status-label">校验通过</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card status-card" data-status="rejected">
                        <div class="card-body text-center">
                            <div class="status-number text-danger" id="rejectedCount">-</div>
                            <div class="status-label">校验失败</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card status-card" data-status="synced">
                        <div class="card-body text-center">
                            <div class="status-number text-info" id="syncedCount">-</div>
                            <div class="status-label">已同步</div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="text-center mt-2">
                <small class="text-muted">总计: <span id="totalCount">0</span> 条数据</small>
            </div>
        `;
        
        this.bindEvents();
    }
    
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
    
    async loadStats() {
        const response = await callApi(`/status/${this.tableName}`);
        
        handleResponse(response, (data) => {
            this.stats = data.data || {};
            this.updateDisplay();
        });
    }
    
    updateDisplay() {
        const pending = document.getElementById('pendingCount');
        const validated = document.getElementById('validatedCount');
        const rejected = document.getElementById('rejectedCount');
        const synced = document.getElementById('syncedCount');
        const total = document.getElementById('totalCount');
        
        if (pending) pending.textContent = this.stats.pending || 0;
        if (validated) validated.textContent = this.stats.validated || 0;
        if (rejected) rejected.textContent = this.stats.rejected || 0;
        if (synced) synced.textContent = this.stats.synced || 0;
        if (total) total.textContent = this.stats.total || 0;
    }
    
    refresh() {
        this.loadStats();
    }
    
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
    
    getStats() {
        return this.stats;
    }
}
