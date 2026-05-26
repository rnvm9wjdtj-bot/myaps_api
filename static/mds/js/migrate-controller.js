/**
 * MDS 数据库迁移控制器
 * 独立命名空间，不与 GlobalOpsController 冲突
 * 
 * 安全特性：
 * 1. 按钮默认隐藏且禁用
 * 2. 鼠标悬停右下角5秒后显示
 * 3. 点击前校验数据库权限
 */
var MigrateController = (function() {
    var API = {
        checkPermission: '/api/mds/migrate/check-permission',
        diff: '/api/mds/migrate/diff',
        execute: '/api/mds/migrate/execute',
        versions: '/api/mds/migrate/versions'
    };

    var HOVER_DELAY = 5000;

    var state = {
        diffData: null,
        isExecuting: false,
        hoverTimer: null,
        isUnlocked: false
    };

    var dom = {};

    function cacheDOM() {
        dom.migrateTriggerZone = document.getElementById('migrateTriggerZone');
        dom.migrateBtn = document.getElementById('migrateBtn');
        dom.migrateDialog = document.getElementById('migrateDialog');
        dom.migrateDiffBody = document.getElementById('migrateDiffBody');
        dom.migrateProgress = document.getElementById('migrateProgress');
        dom.migrateProgressBar = document.getElementById('migrateProgressBar');
        dom.migrateProgressText = document.getElementById('migrateProgressText');
        dom.migrateResult = document.getElementById('migrateResult');
        dom.migrateResultBody = document.getElementById('migrateResultBody');
        dom.confirmMigrateBtn = document.getElementById('confirmMigrateBtn');
        dom.closeMigrateDialogBtn = document.getElementById('closeMigrateDialogBtn');
        dom.closeMigrateResultBtn = document.getElementById('closeMigrateResultBtn');
    }

    function bindEvents() {
        if (dom.migrateTriggerZone) {
            dom.migrateTriggerZone.addEventListener('mouseenter', handleMouseEnter);
            dom.migrateTriggerZone.addEventListener('mouseleave', handleMouseLeave);
        }
        
        if (dom.migrateBtn) {
            dom.migrateBtn.addEventListener('click', handleMigrateClick);
        }
        if (dom.confirmMigrateBtn) {
            dom.confirmMigrateBtn.addEventListener('click', executeMigration);
        }
        if (dom.closeMigrateDialogBtn) {
            dom.closeMigrateDialogBtn.addEventListener('click', function() {
                var modal = bootstrap.Modal.getInstance(dom.migrateDialog);
                if (modal) modal.hide();
            });
        }
        if (dom.closeMigrateResultBtn) {
            dom.closeMigrateResultBtn.addEventListener('click', function() {
                var modal = bootstrap.Modal.getInstance(dom.migrateResult);
                if (modal) modal.hide();
            });
        }
    }

    function handleMouseEnter() {
        if (state.hoverTimer) {
            clearTimeout(state.hoverTimer);
        }
        
        state.hoverTimer = setTimeout(function() {
            showButton();
        }, HOVER_DELAY);
    }

    function handleMouseLeave() {
        if (state.hoverTimer) {
            clearTimeout(state.hoverTimer);
            state.hoverTimer = null;
        }
        
        hideButton();
        state.isUnlocked = false;
    }

    function showButton() {
        if (dom.migrateBtn) {
            dom.migrateBtn.disabled = false;
            dom.migrateBtn.style.opacity = '1';
            dom.migrateBtn.style.pointerEvents = 'auto';
            dom.migrateBtn.style.transition = 'opacity 0.3s ease';
        }
    }

    function hideButton() {
        if (dom.migrateBtn) {
            dom.migrateBtn.disabled = true;
            dom.migrateBtn.style.opacity = '0';
            dom.migrateBtn.style.pointerEvents = 'none';
        }
    }

    async function checkPermission() {
        try {
            var response = await fetch(API.checkPermission);
            var result = await response.json();
            
            if (result.success && result.data && result.data.has_permission) {
                return {
                    hasPermission: true,
                    user: result.data.user,
                    database: result.data.database
                };
            } else {
                var message = result.message || '权限不足';
                alert('数据库权限校验失败:\n' + message);
                return { hasPermission: false };
            }
        } catch (e) {
            alert('权限校验请求失败: ' + e.message);
            return { hasPermission: false };
        }
    }

    async function handleMigrateClick() {
        var permResult = await checkPermission();
        
        if (!permResult.hasPermission) {
            return;
        }
        
        state.isUnlocked = true;

        dom.migrateBtn.disabled = true;
        dom.migrateBtn.innerHTML = '<i class="bi bi-arrow-repeat spin-animation"></i>';

        try {
            var response = await fetch(API.diff);
            var result = await response.json();

            if (result.success && result.data) {
                state.diffData = result.data;
                showConfirmDialog(result.data);
            } else {
                alert('差异检测失败: ' + (result.message || '未知错误'));
            }
        } catch (e) {
            alert('请求失败: ' + e.message);
        } finally {
            dom.migrateBtn.disabled = false;
            dom.migrateBtn.innerHTML = '<i class="bi bi-database-gear"></i>';
        }
    }

    function showConfirmDialog(data) {
        var differences = data.differences || [];
        var totalTables = data.total_tables || 0;
        var totalFields = data.total_fields || 0;

        if (totalFields === 0) {
            alert('数据库结构已是最新，无需迁移');
            return;
        }

        var html = '<div class="alert alert-warning mb-3">' +
            '<i class="bi bi-exclamation-triangle-fill me-2"></i>' +
            '<strong>重要提醒：</strong>执行迁移前请先备份数据库！' +
            '</div>';

        html += '<div class="mb-3">' +
            '<span class="badge bg-info me-2">待迁移表: ' + totalTables + '</span>' +
            '<span class="badge bg-primary">待迁移字段: ' + totalFields + '</span>' +
            '</div>';

        html += '<div class="table-responsive" style="max-height: 300px; overflow-y: auto;">' +
            '<table class="table table-sm table-hover">' +
            '<thead class="table-light sticky-top">' +
            '<tr><th>表名</th><th>字段名</th><th>数据库字段</th><th>类型</th></tr>' +
            '</thead><tbody>';

        differences.forEach(function(diff) {
            html += '<tr>' +
                '<td><code>' + diff.table + '</code></td>' +
                '<td>' + diff.field + '</td>' +
                '<td><code>' + diff.db_field + '</code></td>' +
                '<td><small>' + diff.sql_type + '</small></td>' +
                '</tr>';
        });

        html += '</tbody></table></div>';

        if (dom.migrateDiffBody) {
            dom.migrateDiffBody.innerHTML = html;
        }

        var modal = new bootstrap.Modal(dom.migrateDialog);
        modal.show();
    }

    async function executeMigration() {
        if (!state.diffData || !state.diffData.differences || state.diffData.differences.length === 0) {
            alert('没有待迁移的数据');
            return;
        }

        var confirmDialog = bootstrap.Modal.getInstance(dom.migrateDialog);
        if (confirmDialog) confirmDialog.hide();

        var progressModal = new bootstrap.Modal(dom.migrateProgress);
        progressModal.show();

        updateProgress(10, '正在执行迁移...');

        try {
            var response = await fetch(API.execute, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    tables: [],
                    force: false
                })
            });

            var result = await response.json();

            updateProgress(100, '迁移完成');

            setTimeout(function() {
                progressModal.hide();
                showResultSummary(result);
            }, 500);

        } catch (e) {
            updateProgress(100, '迁移失败');
            setTimeout(function() {
                progressModal.hide();
                alert('迁移失败: ' + e.message);
            }, 500);
        }
    }

    function updateProgress(percent, text) {
        if (dom.migrateProgressBar) {
            dom.migrateProgressBar.style.width = percent + '%';
            dom.migrateProgressBar.setAttribute('aria-valuenow', percent);
        }
        if (dom.migrateProgressText) {
            dom.migrateProgressText.textContent = text;
        }
    }

    function showResultSummary(result) {
        var data = result.data || {};
        var version = data.version || 'N/A';
        var applied = data.applied_count || 0;
        var failed = data.failed_count || 0;
        var changes = data.changes || [];

        var html = '<div class="mb-3">' +
            '<span class="badge bg-secondary me-2">版本: ' + version + '</span>' +
            '<span class="badge bg-success me-2">成功: ' + applied + '</span>' +
            '<span class="badge bg-danger">失败: ' + failed + '</span>' +
            '</div>';

        if (changes.length > 0) {
            html += '<div class="table-responsive" style="max-height: 300px; overflow-y: auto;">' +
                '<table class="table table-sm">' +
                '<thead class="table-light sticky-top">' +
                '<tr><th>表名</th><th>字段</th><th>状态</th></tr>' +
                '</thead><tbody>';

            changes.forEach(function(change) {
                var statusIcon = change.success
                    ? '<i class="bi bi-check-circle text-success"></i>'
                    : '<i class="bi bi-x-circle text-danger"></i>';
                html += '<tr>' +
                    '<td><code>' + change.table + '</code></td>' +
                    '<td>' + change.db_field + '</td>' +
                    '<td>' + statusIcon + '</td>' +
                    '</tr>';
            });

            html += '</tbody></table></div>';
        }

        if (dom.migrateResultBody) {
            dom.migrateResultBody.innerHTML = html;
        }

        var resultModal = new bootstrap.Modal(dom.migrateResult);
        resultModal.show();
    }

    function init() {
        cacheDOM();
        bindEvents();
    }

    return {
        init: init
    };
})();
