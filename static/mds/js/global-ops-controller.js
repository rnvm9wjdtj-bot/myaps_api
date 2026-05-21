var GlobalOpsController = (function() {
    var MODULE_ORDER = [
        { key: 't_material', name: '物料', icon: 'bi-box-seam' },
        { key: 't_mat_ver', name: '产线版本', icon: 'bi-tags' },
        { key: 't_workcenter', name: '工作中心', icon: 'bi-building-gear' },
        { key: 't_mat_wc', name: '工艺路线', icon: 'bi-tools' },
        { key: 't_mat_wc_bom', name: 'BOM', icon: 'bi-diagram-3' },
        { key: 't_mold', name: '模具', icon: 'bi-device-ssd' },
        { key: 't_mat_wc_mold', name: '机台模具', icon: 'bi-gear-wide-connected' }
    ];

    var STATUS_ICONS = {
        pending: '<i class="bi bi-circle text-secondary"></i>',
        processing: '<i class="bi bi-arrow-repeat spin-animation text-primary"></i>',
        success: '<i class="bi bi-check-circle text-success"></i>',
        failed: '<i class="bi bi-x-circle text-danger"></i>'
    };

    var state = {
        operationType: null,
        moduleStats: {},
        executionResults: {},
        isExecuting: true,
        startTime: null
    };

    var dom = {};

    function cacheDOM() {
        dom.globalValidateBtn = document.getElementById('globalValidateBtn');
        dom.globalSyncBtn = document.getElementById('globalSyncBtn');
        dom.globalOpsDialog = document.getElementById('globalOpsDialog');
        dom.globalOpsDialogTitle = document.getElementById('globalOpsDialogTitle');
        dom.globalOpsDesc = document.getElementById('globalOpsDesc');
        dom.dependencyFlow = document.getElementById('dependencyFlow');
        dom.moduleListBody = document.getElementById('moduleListBody');
        dom.totalPending = document.getElementById('totalPending');
        dom.confirmGlobalOps = document.getElementById('confirmGlobalOps');
        dom.globalOpsProgress = document.getElementById('globalOpsProgress');
        dom.progressIcon = document.getElementById('progressIcon');
        dom.progressTitle = document.getElementById('progressTitle');
        dom.overallProgress = document.getElementById('overallProgress');
        dom.moduleStatusCards = document.getElementById('moduleStatusCards');
        dom.execLog = document.getElementById('execLog');
        dom.summaryReport = document.getElementById('summaryReport');
        dom.totalSuccess = document.getElementById('totalSuccess');
        dom.totalFailed = document.getElementById('totalFailed');
        dom.totalTime = document.getElementById('totalTime');
        dom.detailResultBody = document.getElementById('detailResultBody');
        dom.cancelExecutionBtn = document.getElementById('cancelExecutionBtn');
        dom.viewDetailBtn = document.getElementById('viewDetailBtn');
        dom.closeProgressBtn = document.getElementById('closeProgressBtn');
    }

    function bindEvents() {
        if (dom.globalValidateBtn) {
            dom.globalValidateBtn.addEventListener('click', function() {
                handleOperationStart('validate');
            });
        }
        if (dom.globalSyncBtn) {
            dom.globalSyncBtn.addEventListener('click', function() {
                handleOperationStart('sync');
            });
        }
        if (dom.confirmGlobalOps) {
            dom.confirmGlobalOps.addEventListener('click', handleConfirm);
        }
        if (dom.cancelExecutionBtn) {
            dom.cancelExecutionBtn.addEventListener('click', handleCancelExecution);
        }
        if (dom.viewDetailBtn) {
            dom.viewDetailBtn.addEventListener('click', function() {
                window.location.reload();
            });
        }
    }

    function handleOperationStart(type) {
        state.operationType = type;
        state.moduleStats = {};
        
        var title = type === 'validate' ? '校验全部模块' : '推送全部模块';
        var desc = type === 'validate' 
            ? '校验操作将按依赖顺序检查所有模块数据的完整性和正确性' 
            : '推送操作将按依赖顺序将校验通过的数据同步到正式表';
        
        if (dom.globalOpsDialogTitle) dom.globalOpsDialogTitle.textContent = title;
        if (dom.globalOpsDesc) dom.globalOpsDesc.textContent = desc;
        
        renderDependencyFlow();
        loadModuleStats();
        
        var modal = new bootstrap.Modal(dom.globalOpsDialog);
        modal.show();
    }

    function renderDependencyFlow() {
        var flow = MODULE_ORDER.map(function(m, i) {
            return '<span class="badge bg-light text-dark me-1">' + m.name + '</span>' +
                   (i < MODULE_ORDER.length - 1 ? '<i class="bi bi-arrow-right text-muted me-1"></i>' : '');
        }).join('');
        if (dom.dependencyFlow) dom.dependencyFlow.innerHTML = flow;
    }

    function loadModuleStats() {
        if (dom.moduleListBody) {
            dom.moduleListBody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">加载中...</td></tr>';
        }
        
        fetch('/api/mds/index-stats')
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success === 1) {
                    data.data.forEach(function(item) {
                        state.moduleStats[item.table] = item;
                    });
                }
                renderModuleList();
            })
            .catch(function() {
                renderModuleList();
            });
    }

    function renderModuleList() {
        var totalPending = 0;
        var html = '';
        
        MODULE_ORDER.forEach(function(m, i) {
            var tableKey = m.key + '_staging';
            var stats = state.moduleStats[tableKey] || {};
            var pending = stats.pending || 0;
            totalPending += pending;
            
            html += '<tr>' +
                '<td>' + (i + 1) + '</td>' +
                '<td><i class="bi ' + m.icon + ' me-2"></i>' + m.name + '</td>' +
                '<td class="text-center">' + pending + '</td>' +
                '</tr>';
        });
        
        if (dom.moduleListBody) dom.moduleListBody.innerHTML = html;
        if (dom.totalPending) dom.totalPending.textContent = totalPending;
    }

    function handleConfirm() {
        bootstrap.Modal.getInstance(dom.globalOpsDialog).hide();
        initProgressUI();
        
        var modal = new bootstrap.Modal(dom.globalOpsProgress);
        modal.show();
        
        setTimeout(executeOperation, 500);
    }

    function initProgressUI() {
        state.executionResults = {};
        state.isExecuting = true;
        state.startTime = Date.now();
        
        if (dom.progressIcon) dom.progressIcon.className = 'bi bi-hourglass-split';
        if (dom.progressTitle) dom.progressTitle.textContent = '执行中...';
        if (dom.overallProgress) {
            dom.overallProgress.style.width = '0%';
            dom.overallProgress.textContent = '0%';
        }
        if (dom.execLog) dom.execLog.innerHTML = '';
        if (dom.summaryReport) dom.summaryReport.style.display = 'none';
        
        if (dom.cancelExecutionBtn) dom.cancelExecutionBtn.classList.remove('d-none');
        if (dom.viewDetailBtn) dom.viewDetailBtn.classList.add('d-none');
        if (dom.closeProgressBtn) dom.closeProgressBtn.classList.add('d-none');
        
        var cardsHtml = MODULE_ORDER.map(function(m) {
            return '<div class="col-12 col-sm-6 col-md-4">' +
                '<div class="card" id="card-' + m.key + '">' +
                '<div class="card-body text-center py-2">' +
                '<div>' + STATUS_ICONS.pending + ' <strong>' + m.name + '</strong></div>' +
                '<small class="text-muted" id="card-status-' + m.key + '">等待中</small>' +
                '</div></div></div>';
        }).join('');
        if (dom.moduleStatusCards) dom.moduleStatusCards.innerHTML = cardsHtml;
    }

    async function executeOperation() {
        var apiEndpoint = state.operationType === 'validate' 
            ? '/api/mds/validate_all' 
            : '/api/mds/sync_all';
        
        for (var i = 0; i < MODULE_ORDER.length; i++) {
            if (!state.isExecuting) break;
            
            var m = MODULE_ORDER[i];
            updateModuleStatus(m.key, 'processing');
            addLog('开始处理: ' + m.name, 'info');
            
            try {
                var url = apiEndpoint + '?table_name=' + encodeURIComponent(m.key);
                var response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                var result = await response.json();
                
                if (result.success === 1) {
                    var stats = result.data[m.key] || {};
                    var successCount = state.operationType === 'validate' 
                        ? (stats.processed || 0) 
                        : (stats.synced || 0);
                    var failedCount = stats.failed || 0;
                    
                    state.executionResults[m.key] = {
                        success: successCount,
                        failed: failedCount,
                        status: 'success'
                    };
                    
                    updateModuleStatus(m.key, 'success', successCount, failedCount);
                    addLog(m.name + ' 完成: 成功 ' + successCount + ', 失败 ' + failedCount, 'success');
                } else {
                    throw new Error(result.message || '执行失败');
                }
            } catch (error) {
                state.executionResults[m.key] = {
                    success: 0,
                    failed: 0,
                    status: 'failed',
                    error: error.message
                };
                updateModuleStatus(m.key, 'failed');
                addLog(m.name + ' 失败: ' + error.message, 'danger');
            }
            
            updateOverallProgress(i + 1);
        }
        
        showSummaryReport();
    }

    function updateModuleStatus(moduleKey, status, success, failed) {
        var card = document.getElementById('card-' + moduleKey);
        var statusEl = document.getElementById('card-status-' + moduleKey);
        
        if (card) {
            card.classList.remove('border-primary', 'border-success', 'border-danger');
            if (status === 'processing') card.classList.add('border-primary');
            if (status === 'success') card.classList.add('border-success');
            if (status === 'failed') card.classList.add('border-danger');
        }
        
        if (statusEl) {
            var icon = STATUS_ICONS[status] || STATUS_ICONS.pending;
            if (status === 'processing') {
                statusEl.innerHTML = icon + ' 处理中...';
            } else if (status === 'success') {
                statusEl.innerHTML = icon + ' 成功:' + (success || 0) + ' 失败:' + (failed || 0);
            } else if (status === 'failed') {
                statusEl.innerHTML = icon + ' 失败';
            }
        }
    }

    function updateOverallProgress(completed) {
        var percent = Math.round((completed / MODULE_ORDER.length) * 100);
        if (dom.overallProgress) {
            dom.overallProgress.style.width = percent + '%';
            dom.overallProgress.textContent = percent + '%';
        }
    }

    function addLog(message, type) {
        var time = new Date().toLocaleTimeString();
        var colorClass = {
            info: 'text-info',
            success: 'text-success',
            warning: 'text-warning',
            danger: 'text-danger'
        }[type] || 'text-light';
        
        var logEntry = '<div class="' + colorClass + '">[' + time + '] ' + message + '</div>';
        if (dom.execLog) {
            dom.execLog.innerHTML += logEntry;
            dom.execLog.scrollTop = dom.execLog.scrollHeight;
        }
    }

    function showSummaryReport() {
        var totalTime = ((Date.now() - state.startTime) / 1000).toFixed(1);
        var totalSuccess = 0;
        var totalFailed = 0;
        
        var detailHtml = '';
        MODULE_ORDER.forEach(function(m) {
            var result = state.executionResults[m.key] || {};
            totalSuccess += result.success || 0;
            totalFailed += result.failed || 0;
            
            var statusIcon = result.status === 'success' 
                ? '<i class="bi bi-check-circle text-success"></i>' 
                : '<i class="bi bi-x-circle text-danger"></i>';
            
            detailHtml += '<tr>' +
                '<td>' + m.name + '</td>' +
                '<td>' + (result.success || 0) + '</td>' +
                '<td>' + (result.failed || 0) + '</td>' +
                '<td>' + statusIcon + '</td>' +
                '</tr>';
        });
        
        if (dom.totalSuccess) dom.totalSuccess.textContent = totalSuccess;
        if (dom.totalFailed) dom.totalFailed.textContent = totalFailed;
        if (dom.totalTime) dom.totalTime.textContent = totalTime + 's';
        if (dom.detailResultBody) dom.detailResultBody.innerHTML = detailHtml;
        
        if (dom.progressIcon) dom.progressIcon.className = 'bi bi-check-circle text-success';
        if (dom.progressTitle) dom.progressTitle.textContent = '执行完成';
        if (dom.summaryReport) dom.summaryReport.style.display = 'block';
        
        if (dom.cancelExecutionBtn) dom.cancelExecutionBtn.classList.add('d-none');
        if (dom.viewDetailBtn) dom.viewDetailBtn.classList.remove('d-none');
        if (dom.closeProgressBtn) dom.closeProgressBtn.classList.remove('d-none');
    }

    function handleCancelExecution() {
        if (confirm('确定要取消执行吗？已处理的模块将保留结果。')) {
            state.isExecuting = false;
            addLog('用户取消执行', 'warning');
        }
    }

    function init() {
        cacheDOM();
        bindEvents();
    }

    return { init: init };
})();

document.addEventListener('DOMContentLoaded', function() {
    GlobalOpsController.init();
});
