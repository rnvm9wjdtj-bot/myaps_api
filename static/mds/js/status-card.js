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
                    <div class="card status-card" data-status="synced">
                        <div class="card-body text-center">
                            <div class="status-number text-info" id="syncedCount">-</div>
                            <div class="status-label">已同步</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="ready_sync">
                        <div class="card-body text-center">
                            <div class="status-number text-success" id="readySyncCount">-</div>
                            <div class="status-label">可同步</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="pending">
                        <div class="card-body text-center">
                            <div class="status-number text-warning" id="pendingCount">-</div>
                            <div class="status-label">待处理</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="validated">
                        <div class="card-body text-center">
                            <div class="status-number text-success" id="validatedCount">-</div>
                            <div class="status-label">校验通过</div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <div class="card status-card" data-status="rejected">
                        <div class="card-body text-center">
                            <div class="status-number text-danger" id="rejectedCount">-</div>
                            <div class="status-label">校验失败</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.bindEvents();
        this.activeStatus = '';
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
                    
                    let actualStatus = status;
                    if (status === 'ready_sync') {
                        actualStatus = 'validated';
                    }
                    
                    if (this.onStatusClick) {
                        this.onStatusClick(actualStatus);
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
        const total = document.getElementById('totalCount');
        const pending = document.getElementById('pendingCount');
        const validated = document.getElementById('validatedCount');
        const rejected = document.getElementById('rejectedCount');
        const synced = document.getElementById('syncedCount');
        const readySync = document.getElementById('readySyncCount');
        
        if (total) total.textContent = this.stats.total || 0;
        if (pending) pending.textContent = this.stats.pending || 0;
        if (validated) validated.textContent = this.stats.validated || 0;
        if (rejected) rejected.textContent = this.stats.rejected || 0;
        if (synced) synced.textContent = this.stats.synced || 0;
        
        const readySyncCount = (this.stats.validated || 0);
        if (readySync) readySync.textContent = readySyncCount;
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
