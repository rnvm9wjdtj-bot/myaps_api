# 监控模块国际化实施计划

## 1. 概述

### 1.1 目标

为监控模块添加多语言支持，支持**中文（zh-CN）**、**英语（en-US）**、**德语（de-DE）**三种语言。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| 无后端改动 | 所有国际化逻辑在前端实现 |
| 最小改动 | 仅添加data-i18n属性和引入脚本 |
| 零依赖 | 不引入第三方i18n库，自研轻量级方案 |
| 渐进式 | 分阶段实施，每阶段可独立验证 |
| 用户友好 | 自动识别浏览器语言，支持热切换 |

### 1.3 技术方案

**核心机制**：
1. 使用 `data-i18n` 属性标记静态文本
2. 语言包以独立JS文件存储于 `static/lib/i18n/`
3. 页面加载时自动检测语言并替换文本
4. 语言切换存储到 localStorage

**文件存储位置**：
```
static/lib/i18n/
├── i18n.js           # 核心脚本（~80行）
├── zh-CN.js          # 中文语言包
├── en-US.js          # 英文语言包
└── de-DE.js          # 德语语言包
```

---

## 2. 实施阶段

### 阶段1：框架搭建（0.5人日）

**目标**：创建i18n核心脚本和语言包骨架

**交付物**：
- `static/lib/i18n/i18n.js` - 核心脚本
- `static/lib/i18n/zh-CN.js` - 中文语言包（骨架）
- `static/lib/i18n/en-US.js` - 英文语言包（骨架）
- `static/lib/i18n/de-DE.js` - 德语语言包（骨架）

**验收标准**：
- [ ] 浏览器控制台无报错
- [ ] `i18n.t('key')` 可正常调用
- [ ] 语言包加载成功

---

### 阶段2：静态文本国际化（1人日）

**目标**：HTML页面中的静态文本添加国际化支持

**改动文件**：
- `static/monitor/index.html`
- `static/monitor/live-logs.html`
- `static/monitor/history-logs.html`

**改动方式**：
```html
<!-- 修改前 -->
<h1>📊 日志历史查询</h1>
<button class="btn btn-primary">查询</button>

<!-- 修改后 -->
<h1 data-i18n="page.history_logs">📊 日志历史查询</h1>
<button class="btn btn-primary" data-i18n="btn.query">查询</button>
```

**验收标准**：
- [ ] 切换语言后，静态文本正确显示对应语言
- [ ] 切换后刷新页面，语言设置保持
- [ ] 所有静态文本无遗漏

---

### 阶段3：动态文本国际化（1.5人日）

**目标**：JavaScript动态生成的文本支持国际化

**改动文件**：
- `static/monitor/js/monitor.js`
- `static/monitor/live-logs.html`（内联脚本）
- `static/monitor/history-logs.html`（内联脚本）

**改动方式**：
```javascript
// 修改前
badge.textContent = '查询中...';
alert('开始时间不能大于结束时间');

// 修改后
badge.textContent = i18n.t('status.querying');
alert(i18n.t('error.time_range_invalid'));
```

**动态文本类型统计**：

| 文件 | alert数 | textContent数 | innerHTML数 | 合计 |
|------|---------|---------------|-------------|------|
| live-logs.html | 0 | 18 | 5 | 23 |
| history-logs.html | 5 | 35 | 15 | 55 |
| monitor.js | ~10 | ~50 | ~20 | ~80 |
| **总计** | **~15** | **~103** | **~40** | **~158** |

**验收标准**：
- [ ] 表格内容正确翻译
- [ ] 弹窗提示正确翻译
- [ ] 状态文本正确翻译
- [ ] 无硬编码中文遗漏

---

### 阶段4：完善与测试（0.5人日）

**目标**：添加语言切换UI，处理边界情况

**交付物**：
- 语言切换下拉菜单组件
- CSS样式调整
- 测试报告

**验收标准**：
- [ ] 语言切换菜单显示正确
- [ ] 切换语言后页面无刷新异常
- [ ] 浏览器语言自动识别正常
- [ ] 三种语言文本无乱码
- [ ] 文本溢出不破坏布局

---

## 3. 详细改动清单

### 3.1 新增文件

#### 3.1.1 i18n核心脚本

**文件路径**：`static/lib/i18n/i18n.js`

**核心代码**（约80行）：
```javascript
/**
 * 轻量级国际化框架
 * 支持中文、英语、德语
 */
class I18n {
    constructor() {
        this.currentLang = this.detectLanguage();
        this.messages = {};
        this.fallbackLang = 'zh-CN';
    }
    
    /**
     * 检测用户语言
     * 优先级：localStorage > 浏览器语言 > 默认中文
     */
    detectLanguage() {
        // 1. 检查localStorage
        const saved = localStorage.getItem('monitor-lang');
        if (saved && ['zh-CN', 'en-US', 'de-DE'].includes(saved)) {
            return saved;
        }
        
        // 2. 检查浏览器语言
        const browserLang = navigator.language || navigator.userLanguage || 'zh-CN';
        
        // 映射浏览器语言到支持的语言
        const langMap = {
            'zh': 'zh-CN',
            'zh-CN': 'zh-CN',
            'zh-Hans': 'zh-CN',
            'en': 'en-US',
            'en-US': 'en-US',
            'en-GB': 'en-US',
            'de': 'de-DE',
            'de-DE': 'de-DE',
            'de-AT': 'de-DE',
            'de-CH': 'de-DE'
        };
        
        return langMap[browserLang] || langMap[browserLang.split('-')[0]] || 'zh-CN';
    }
    
    /**
     * 初始化i18n
     */
    async init() {
        try {
            // 加载语言包
            await this.loadLanguage(this.currentLang);
            
            // 应用翻译
            this.applyTranslations();
            
            // 更新语言选择器
            this.updateLangSelector();
            
            console.log(`[i18n] Initialized with language: ${this.currentLang}`);
        } catch (error) {
            console.error('[i18n] Initialization failed:', error);
            // 回退到中文
            if (this.currentLang !== this.fallbackLang) {
                this.currentLang = this.fallbackLang;
                await this.init();
            }
        }
    }
    
    /**
     * 加载语言包
     */
    async loadLanguage(lang) {
        // 检查是否已加载
        if (window[`__i18n_${lang.replace('-', '_')}__`]) {
            this.messages = window[`__i18n_${lang.replace('-', '_')}__`];
            return;
        }
        
        // 动态加载脚本
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = `/static/lib/i18n/${lang}.js`;
            script.onload = () => {
                this.messages = window[`__i18n_${lang.replace('-', '_')}__`];
                resolve();
            };
            script.onerror = () => reject(new Error(`Failed to load language: ${lang}`));
            document.head.appendChild(script);
        });
    }
    
    /**
     * 应用翻译到DOM
     */
    applyTranslations() {
        // 1. 处理 data-i18n（文本内容）
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const text = this.t(key);
            if (text !== key) {
                el.textContent = text;
            }
        });
        
        // 2. 处理 data-i18n-placeholder（占位符）
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const text = this.t(key);
            if (text !== key) {
                el.placeholder = text;
            }
        });
        
        // 3. 处理 data-i18n-title（标题）
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const text = this.t(key);
            if (text !== key) {
                el.title = text;
            }
        });
        
        // 4. 处理 data-i18n-value（input值）
        document.querySelectorAll('[data-i18n-value]').forEach(el => {
            const key = el.getAttribute('data-i18n-value');
            const text = this.t(key);
            if (text !== key) {
                el.value = text;
            }
        });
        
        // 5. 更新页面标题
        const pageTitle = document.querySelector('[data-i18n-page-title]');
        if (pageTitle) {
            const key = pageTitle.getAttribute('data-i18n-page-title');
            const text = this.t(key);
            if (text !== key) {
                document.title = text;
            }
        }
    }
    
    /**
     * 获取翻译文本
     * @param {string} key - 翻译键
     * @param {object} params - 插值参数（可选）
     */
    t(key, params = {}) {
        let text = this.messages[key] || key;
        
        // 支持插值，如：t('msg.welcome', {name: 'John'}) => "Welcome, John!"
        Object.keys(params).forEach(k => {
            text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), params[k]);
        });
        
        return text;
    }
    
    /**
     * 切换语言
     */
    async switchLanguage(lang) {
        if (lang === this.currentLang) return;
        
        try {
            // 保存到localStorage
            localStorage.setItem('monitor-lang', lang);
            
            // 重新加载
            this.currentLang = lang;
            await this.loadLanguage(lang);
            this.applyTranslations();
            this.updateLangSelector();
            
            // 触发自定义事件（供业务代码监听）
            window.dispatchEvent(new CustomEvent('langchange', { 
                detail: { lang: lang } 
            }));
            
            console.log(`[i18n] Language switched to: ${lang}`);
        } catch (error) {
            console.error('[i18n] Language switch failed:', error);
        }
    }
    
    /**
     * 更新语言选择器状态
     */
    updateLangSelector() {
        const selector = document.getElementById('lang-selector');
        if (selector) {
            selector.value = this.currentLang;
        }
    }
    
    /**
     * 获取当前语言
     */
    getCurrentLang() {
        return this.currentLang;
    }
    
    /**
     * 获取支持的语言列表
     */
    getSupportedLanguages() {
        return [
            { code: 'zh-CN', name: '中文', flag: '🇨🇳' },
            { code: 'en-US', name: 'English', flag: '🇺🇸' },
            { code: 'de-DE', name: 'Deutsch', flag: '🇩🇪' }
        ];
    }
}

// 创建全局实例
const i18n = new I18n();

// 页面加载后自动初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => i18n.init());
} else {
    i18n.init();
}
```

---

#### 3.1.2 中文语言包

**文件路径**：`static/lib/i18n/zh-CN.js`

**语言包结构**：
```javascript
/**
 * 中文语言包（简体中文）
 */
window.__i18n_zh_CN__ = {
    // ============ 页面标题 ============
    'page.title': 'MyAPI 系统监控面板',
    'page.live_logs': '实时日志 - 系统监控',
    'page.history_logs': '日志历史查询 - 系统监控',
    
    // ============ 导航菜单 ============
    'nav.overview': '📊 Overview',
    'nav.database': '🗃️ 数据库',
    'nav.events': '☎️ 事件处理',
    'nav.scheduler': '⏰ 定时任务',
    'nav.http_requests': '📥 接收请求',
    'nav.outbound_requests': '📤 发送请求',
    'nav.logs': '📋 日志',
    
    // ============ 标签页 ============
    'tab.overview': '概览',
    'tab.database': '数据库',
    'tab.events': '事件处理',
    'tab.scheduler': '定时任务',
    'tab.http': '接收请求',
    'tab.outbound': '发送请求',
    'tab.logs': '系统日志',
    'tab.timeline': '时间线',
    'tab.chart': '图表分析',
    
    // ============ 卡片标题 ============
    'card.resource': '资源使用',
    'card.db_status': '账套状态',
    'card.db_connections': '数据库连接状态',
    'card.event_helpers': '事件辅助模块',
    'card.scheduler': '定时任务调度器',
    'card.api_requests': 'HTTP请求统计',
    'card.outbound_requests': '对外HTTP请求',
    'card.redis': 'Redis状态',
    
    // ============ 指标标签 ============
    'metric.cpu': 'CPU 使用率',
    'metric.memory': '内存使用',
    'metric.threads': '线程数',
    'metric.uptime': '运行时间',
    'metric.total_connections': '总连接数',
    'metric.healthy': '健康',
    'metric.unhealthy': '异常',
    'metric.degraded': '降级',
    'metric.total': '总数',
    'metric.success': '成功',
    'metric.failed': '失败',
    'metric.pending': '待处理',
    
    // ============ 状态 ============
    'status.healthy': '● 系统正常',
    'status.unhealthy': '● 系统异常',
    'status.degraded': '● 系统降级',
    'status.running': '运行中',
    'status.checking': '检查中',
    'status.stopped': '已停止',
    'status.loading': '加载中...',
    'status.querying': '查询中...',
    'status.no_data': '暂无数据',
    'status.connected': '已连接',
    'status.connecting': '连接中...',
    'status.disconnected': '已断开',
    'status.reconnecting': '重连中...',
    
    // ============ 按钮 ============
    'btn.query': '查询',
    'btn.reset': '重置',
    'btn.refresh': '刷新',
    'btn.export': '导出',
    'btn.detail': '详情',
    'btn.pause': '暂停',
    'btn.resume': '继续',
    'btn.clear': '清空',
    'btn.save': '保存',
    'btn.delete': '删除',
    'btn.close': '关闭',
    'btn.confirm': '确认',
    'btn.cancel': '取消',
    'btn.test': '测试',
    'btn.realtime_on': '实时追踪: 开',
    'btn.realtime_off': '实时追踪: 关',
    
    // ============ 表格列名 ============
    'col.index': '序号',
    'col.time': '时间',
    'col.level': '级别',
    'col.module': '模块',
    'col.message': '消息',
    'col.method': '方法',
    'col.path': '端点',
    'col.url': 'URL',
    'col.status': '状态码',
    'col.duration': '响应时间',
    'col.client_ip': '客户端IP',
    'col.source': '来源',
    'col.function': '函数',
    'col.line': '行号',
    'col.operation': '操作',
    
    // ============ 快捷时间 ============
    'time.last_10m': '最近10分钟',
    'time.last_30m': '最近30分钟',
    'time.last_1h': '最近1小时',
    'time.last_6h': '最近6小时',
    'time.last_24h': '最近24小时',
    
    // ============ 过滤条件 ============
    'filter.level': '全部级别',
    'filter.type': '全部数据',
    'filter.module': '模块',
    'filter.keyword': '关键词',
    'filter.method': '请求方法',
    'filter.client_ip': '客户端IP',
    'filter.status_range': '状态码范围',
    'filter.duration_range': '响应时间范围',
    'filter.advanced': '高级过滤',
    'filter.collapse': '收起',
    'filter.expand': '展开',
    'filter.clear': '清空',
    
    // ============ 图表 ============
    'chart.request_trend': '📊 请求量趋势',
    'chart.level_distribution': '📊 日志级别分布',
    'chart.status_distribution': '📈 状态码分布',
    'chart.slow_requests': '⏱️ 慢请求TOP10',
    'chart.total_requests': '总请求',
    'chart.error_count': '错误',
    'chart.slow_count': '慢请求',
    'chart.no_slow': '✅ 无慢请求',
    
    // ============ 错误提示 ============
    'error.time_range_invalid': '开始时间不能大于结束时间',
    'error.time_range_required': '请选择开始时间和结束时间',
    'error.query_failed': '查询失败，请稍后重试',
    'error.export_failed': '导出失败，请重试',
    'error.connection_failed': '连接失败，请刷新页面',
    'error.max_templates': '最多保存10个模板，请先删除部分模板',
    
    // ============ 成功提示 ============
    'success.query_complete': '查询完成',
    'success.export_complete': '导出完成',
    'success.template_saved': '模板"{name}"已保存',
    'success.logs_cleared': '日志已清空',
    
    // ============ 时间线 ============
    'timeline.title': '时间线',
    'timeline.no_data': '暂无数据，请先执行查询',
    'timeline.anomaly_detected': '⚠️ 发现 {count} 处异常',
    'timeline.error_burst': '连续{count}条ERROR日志',
    'timeline.slow_anomaly': '异常慢请求({duration}ms > 平均{avg}ms×3)',
    'timeline.duplicate_error': '重复错误"{msg}"出现{count}次',
    
    // ============ 其他 ============
    'other.last_update': '最后更新',
    'other.auto_reconnect': '5秒后重连',
    'other.waiting_logs': '正在等待日志数据...',
    'other.no_matching_logs': '没有匹配的日志',
    'other.precise_mode': '精确定位',
    'other.saved_queries': '已保存查询...',
    'other.all_time': '全部时间',
    'other.linked_query': '联动查询'
};
```

---

#### 3.1.3 英文语言包

**文件路径**：`static/lib/i18n/en-US.js`

**示例片段**：
```javascript
/**
 * English Language Pack (US English)
 */
window.__i18n_en_US__ = {
    // ============ Page Titles ============
    'page.title': 'MyAPI System Monitor',
    'page.live_logs': 'Live Logs - System Monitor',
    'page.history_logs': 'Log History Query - System Monitor',
    
    // ============ Navigation ============
    'nav.overview': '📊 Overview',
    'nav.database': '🗃️ Database',
    'nav.events': '☎️ Events',
    'nav.scheduler': '⏰ Scheduler',
    'nav.http_requests': '📥 HTTP Requests',
    'nav.outbound_requests': '📤 Outbound',
    'nav.logs': '📋 Logs',
    
    // ============ Tabs ============
    'tab.overview': 'Overview',
    'tab.database': 'Database',
    'tab.events': 'Events',
    'tab.scheduler': 'Scheduler',
    'tab.http': 'HTTP Requests',
    'tab.outbound': 'Outbound',
    'tab.logs': 'System Logs',
    'tab.timeline': 'Timeline',
    'tab.chart': 'Charts',
    
    // ============ Cards ============
    'card.resource': 'Resource Usage',
    'card.db_status': 'Database Status',
    'card.db_connections': 'Database Connections',
    'card.event_helpers': 'Event Helpers',
    'card.scheduler': 'Job Scheduler',
    'card.api_requests': 'HTTP Requests',
    'card.outbound_requests': 'Outbound Requests',
    'card.redis': 'Redis Status',
    
    // ============ Metrics ============
    'metric.cpu': 'CPU Usage',
    'metric.memory': 'Memory Usage',
    'metric.threads': 'Threads',
    'metric.uptime': 'Uptime',
    'metric.total_connections': 'Total Connections',
    'metric.healthy': 'Healthy',
    'metric.unhealthy': 'Unhealthy',
    'metric.degraded': 'Degraded',
    'metric.total': 'Total',
    'metric.success': 'Success',
    'metric.failed': 'Failed',
    'metric.pending': 'Pending',
    
    // ============ Status ============
    'status.healthy': '● System Healthy',
    'status.unhealthy': '● System Unhealthy',
    'status.degraded': '● System Degraded',
    'status.running': 'Running',
    'status.checking': 'Checking',
    'status.stopped': 'Stopped',
    'status.loading': 'Loading...',
    'status.querying': 'Querying...',
    'status.no_data': 'No data',
    'status.connected': 'Connected',
    'status.connecting': 'Connecting...',
    'status.disconnected': 'Disconnected',
    'status.reconnecting': 'Reconnecting...',
    
    // ============ Buttons ============
    'btn.query': 'Query',
    'btn.reset': 'Reset',
    'btn.refresh': 'Refresh',
    'btn.export': 'Export',
    'btn.detail': 'Detail',
    'btn.pause': 'Pause',
    'btn.resume': 'Resume',
    'btn.clear': 'Clear',
    'btn.save': 'Save',
    'btn.delete': 'Delete',
    'btn.close': 'Close',
    'btn.confirm': 'Confirm',
    'btn.cancel': 'Cancel',
    'btn.test': 'Test',
    'btn.realtime_on': 'Realtime: ON',
    'btn.realtime_off': 'Realtime: OFF',
    
    // ============ Table Columns ============
    'col.index': '#',
    'col.time': 'Time',
    'col.level': 'Level',
    'col.module': 'Module',
    'col.message': 'Message',
    'col.method': 'Method',
    'col.path': 'Path',
    'col.url': 'URL',
    'col.status': 'Status',
    'col.duration': 'Duration',
    'col.client_ip': 'Client IP',
    'col.source': 'Source',
    'col.function': 'Function',
    'col.line': 'Line',
    'col.operation': 'Action',
    
    // ... 其余翻译项（见完整文件）
};
```

---

#### 3.1.4 德语语言包

**文件路径**：`static/lib/i18n/de-DE.js`

**示例片段**：
```javascript
/**
 * Deutsches Sprachpaket (Deutsch)
 */
window.__i18n_de_DE__ = {
    // ============ Seitentitel ============
    'page.title': 'MyAPI Systemüberwachung',
    'page.live_logs': 'Echtzeit-Logs - Systemüberwachung',
    'page.history_logs': 'Protokollverlauf - Systemüberwachung',
    
    // ============ Navigation ============
    'nav.overview': '📊 Übersicht',
    'nav.database': '🗃️ Datenbank',
    'nav.events': '☎️ Ereignisse',
    'nav.scheduler': '⏰ Planer',
    'nav.http_requests': '📥 HTTP-Anfragen',
    'nav.outbound_requests': '📤 Ausgehend',
    'nav.logs': '📋 Protokolle',
    
    // ============ Tabs ============
    'tab.overview': 'Übersicht',
    'tab.database': 'Datenbank',
    'tab.events': 'Ereignisse',
    'tab.scheduler': 'Planer',
    'tab.http': 'HTTP-Anfragen',
    'tab.outbound': 'Ausgehend',
    'tab.logs': 'Systemprotokolle',
    'tab.timeline': 'Zeitachse',
    'tab.chart': 'Diagramme',
    
    // ============ Karten ============
    'card.resource': 'Ressourcennutzung',
    'card.db_status': 'Datenbankstatus',
    'card.db_connections': 'Datenbankverbindungen',
    'card.event_helpers': 'Ereignis-Helfer',
    'card.scheduler': 'Aufgabenplaner',
    'card.api_requests': 'HTTP-Anfragen',
    'card.outbound_requests': 'Ausgehende Anfragen',
    'card.redis': 'Redis-Status',
    
    // ============ Kennzahlen ============
    'metric.cpu': 'CPU-Auslastung',
    'metric.memory': 'Speichernutzung',
    'metric.threads': 'Threads',
    'metric.uptime': 'Laufzeit',
    'metric.total_connections': 'Verbindungen',
    'metric.healthy': 'Gesund',
    'metric.unhealthy': 'Fehlerhaft',
    'metric.degraded': 'Eingeschränkt',
    'metric.total': 'Gesamt',
    'metric.success': 'Erfolg',
    'metric.failed': 'Fehler',
    'metric.pending': 'Ausstehend',
    
    // ============ Status ============
    'status.healthy': '● System gesund',
    'status.unhealthy': '● System fehlerhaft',
    'status.degraded': '● System eingeschränkt',
    'status.running': 'Läuft',
    'status.checking': 'Prüfe',
    'status.stopped': 'Gestoppt',
    'status.loading': 'Laden...',
    'status.querying': 'Abfrage...',
    'status.no_data': 'Keine Daten',
    'status.connected': 'Verbunden',
    'status.connecting': 'Verbinde...',
    'status.disconnected': 'Getrennt',
    'status.reconnecting': 'Verbinde neu...',
    
    // ============ Schaltflächen ============
    'btn.query': 'Abfrage',
    'btn.reset': 'Zurücksetzen',
    'btn.refresh': 'Aktualisieren',
    'btn.export': 'Exportieren',
    'btn.detail': 'Details',
    'btn.pause': 'Pause',
    'btn.resume': 'Fortsetzen',
    'btn.clear': 'Löschen',
    'btn.save': 'Speichern',
    'btn.delete': 'Löschen',
    'btn.close': 'Schließen',
    'btn.confirm': 'Bestätigen',
    'btn.cancel': 'Abbrechen',
    'btn.test': 'Testen',
    'btn.realtime_on': 'Echtzeit: AN',
    'btn.realtime_off': 'Echtzeit: AUS',
    
    // ============ Tabellenspalten ============
    'col.index': '#',
    'col.time': 'Zeit',
    'col.level': 'Stufe',
    'col.module': 'Modul',
    'col.message': 'Nachricht',
    'col.method': 'Methode',
    'col.path': 'Pfad',
    'col.url': 'URL',
    'col.status': 'Status',
    'col.duration': 'Dauer',
    'col.client_ip': 'Client-IP',
    'col.source': 'Quelle',
    'col.function': 'Funktion',
    'col.line': 'Zeile',
    'col.operation': 'Aktion',
    
    // ... 其余翻译项（见完整文件）
};
```

---

### 3.2 修改文件清单

#### 3.2.1 index.html

**文件路径**：`static/monitor/index.html`

**改动位置**：

| 行号范围 | 改动类型 | 改动内容 |
|----------|----------|----------|
| 2 | 修改 | `<html lang="zh-CN">` → `<html>`（动态设置） |
| 6 | 添加属性 | `<title data-i18n-page-title="page.title">` |
| 9-12后 | 新增 | 引入i18n脚本 |
| 18-24 | 添加属性 | 导航菜单添加 `data-i18n` |
| 27-29 | 添加属性 | 状态文本添加 `data-i18n` |
| 30后 | 新增 | 语言切换下拉菜单 |
| 38 | 添加属性 | 卡片标题添加 `data-i18n` |
| 44,51,60,64 | 添加属性 | 指标标签添加 `data-i18n` |
| ... | ... | 所有静态文本添加 `data-i18n` |

**引入脚本示例**（添加到 `<head>` 末尾）：
```html
<!-- i18n 国际化 -->
<script src="/static/lib/i18n/i18n.js"></script>
```

**语言切换菜单示例**（添加到 header-info 区域）：
```html
<div class="header-info">
    <select id="lang-selector" class="lang-selector" onchange="i18n.switchLanguage(this.value)">
        <option value="zh-CN">🇨🇳 中文</option>
        <option value="en-US">🇺🇸 English</option>
        <option value="de-DE">🇩🇪 Deutsch</option>
    </select>
    <span id="status-indicator" class="status healthy" data-i18n="status.healthy">● 系统正常</span>
    ...
</div>
```

---

#### 3.2.2 live-logs.html

**文件路径**：`static/monitor/live-logs.html`

**改动位置**：

| 行号 | 改动内容 |
|------|----------|
| 547 | `statusText.textContent = i18n.t('error.connection_failed');` |
| 603 | `text.textContent = i18n.t('status.connected');` |
| 607 | `text.textContent = i18n.t('status.connecting');` |
| 610 | `text.textContent = i18n.t('status.disconnected') + ' (' + i18n.t('other.auto_reconnect') + ')';` |
| 725 | `container.innerHTML = '<div class="no-logs">' + i18n.t('other.waiting_logs') + '</div>';` |
| 741 | `container.innerHTML = '<div class="no-logs">' + i18n.t('other.no_matching_logs') + '</div>';` |
| 814 | `pauseBtnText.textContent = isPaused ? i18n.t('btn.resume') : i18n.t('btn.pause');` |
| 859 | `logsContainer.innerHTML = '<div class="no-logs">' + i18n.t('success.logs_cleared') + '</div>';` |

---

#### 3.2.3 history-logs.html

**文件路径**：`static/monitor/history-logs.html`

**改动位置**（部分示例）：

| 行号 | 改动内容 |
|------|----------|
| 1179 | `alert(i18n.t('error.time_range_invalid'));` |
| 1192 | `badge.textContent = i18n.t('status.querying');` |
| 1199 | `queryBtn.textContent = i18n.t('status.querying');` |
| 1304 | `badge.textContent = i18n.t('success.query_complete');` |
| 1310 | `queryBtn.textContent = i18n.t('btn.query');` |
| 1315 | `alert(i18n.t('error.query_failed'));` |
| 1351 | `innerHTML = '<tr><td colspan="8" class="no-data">' + i18n.t('status.no_data') + '</td></tr>'` |
| 1654 | `container.innerHTML = '<div class="timeline-empty">' + i18n.t('status.no_data') + '</div>';` |
| 1767 | `innerHTML = '<div>...">' + i18n.t('status.query_required') + '</div>'` |
| 1880 | `btn.textContent = i18n.t('btn.realtime_on');` |
| 1884 | `btn.textContent = i18n.t('btn.realtime_off');` |
| 1900 | `alert(i18n.t('error.auto_pause'));` |

---

### 3.3 CSS改动

**文件路径**：`static/monitor/css/monitor.css`

**新增样式**（约20行）：
```css
/* 语言切换器 */
.lang-selector {
    padding: 4px 8px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    background: white;
    margin-right: 12px;
}

.lang-selector:hover {
    border-color: var(--primary-color);
}

.lang-selector option {
    padding: 4px 8px;
}
```

---

## 4. 语言包完整翻译项统计

### 4.1 按分类统计

| 分类 | 翻译项数 | 示例 |
|------|----------|------|
| 页面标题 | 3 | page.title, page.live_logs, page.history_logs |
| 导航菜单 | 7 | nav.overview, nav.database, ... |
| 标签页 | 9 | tab.overview, tab.database, ... |
| 卡片标题 | 8 | card.resource, card.db_status, ... |
| 指标标签 | 12 | metric.cpu, metric.memory, ... |
| 状态 | 13 | status.healthy, status.loading, ... |
| 按钮 | 15 | btn.query, btn.reset, ... |
| 表格列名 | 15 | col.time, col.level, ... |
| 快捷时间 | 5 | time.last_10m, time.last_1h, ... |
| 过滤条件 | 10 | filter.level, filter.keyword, ... |
| 图表 | 8 | chart.request_trend, ... |
| 错误提示 | 6 | error.time_range_invalid, ... |
| 成功提示 | 4 | success.query_complete, ... |
| 时间线 | 5 | timeline.title, ... |
| 其他 | 8 | other.last_update, ... |
| **总计** | **~128项** | - |

---

## 5. 测试计划

### 5.1 测试环境

| 项目 | 要求 |
|------|------|
| 浏览器 | Chrome, Firefox, Edge (最新版本) |
| 操作系统 | Windows, macOS, Linux |
| 屏幕分辨率 | 1920x1080, 1366x768 |

---

### 5.2 测试用例

#### TC-01：自动语言检测

**前置条件**：浏览器语言设置为中文

**测试步骤**：
1. 打开监控页面
2. 观察页面语言

**预期结果**：页面显示中文

---

#### TC-02：语言切换（中文→英文）

**测试步骤**：
1. 打开监控页面
2. 在语言选择器中选择"English"
3. 刷新页面

**预期结果**：
- 页面文本切换为英文
- 刷新后仍显示英文
- localStorage中保存 `monitor-lang=en-US`

---

#### TC-03：语言切换（英文→德语）

**测试步骤**：
1. 语言选择器中选择"Deutsch"
2. 检查所有页面（Overview, Database, Logs等）

**预期结果**：
- 所有页面文本切换为德语
- 图表标题正确翻译
- 表格列名正确翻译

---

#### TC-04：动态文本翻译

**测试步骤**：
1. 切换到英文
2. 执行日志查询（不选时间范围）
3. 观察错误提示

**预期结果**：alert显示英文错误消息 "Please select start time and end time"

---

#### TC-05：实时日志翻译

**测试步骤**：
1. 打开实时日志页面
2. 切换到德语
3. 观察连接状态

**预期结果**：
- "已连接" 显示为 "Verbunden"
- "连接中..." 显示为 "Verbinde..."

---

#### TC-06：历史查询翻译

**测试步骤**：
1. 打开历史日志页面
2. 切换到英文
3. 执行查询
4. 切换到时间线标签页

**预期结果**：
- 标签页名称正确翻译
- 表格内容正确翻译
- 时间线事件正确翻译

---

#### TC-07：边界情况测试

**测试步骤**：
1. 切换到德语
2. 执行各种操作（导出、分页、排序等）

**预期结果**：
- 所有提示文本正确显示德语
- 无中文硬编码遗漏
- 文本无截断或溢出

---

#### TC-08：回退机制测试

**测试步骤**：
1. 手动设置localStorage为不存在的语言（如`ja-JP`）
2. 刷新页面

**预期结果**：回退到中文（fallback语言）

---

### 5.3 测试检查清单

| 检查项 | 中文 | 英文 | 德语 | 通过 |
|--------|------|------|------|------|
| 页面标题 | ☐ | ☐ | ☐ | - |
| 导航菜单 | ☐ | ☐ | ☐ | - |
| 标签页名称 | ☐ | ☐ | ☐ | - |
| 卡片标题 | ☐ | ☐ | ☐ | - |
| 指标标签 | ☐ | ☐ | ☐ | - |
| 状态文本 | ☐ | ☐ | ☐ | - |
| 按钮文本 | ☐ | ☐ | ☐ | - |
| 表格列名 | ☐ | ☐ | ☐ | - |
| 过滤条件 | ☐ | ☐ | ☐ | - |
| 图表标题 | ☐ | ☐ | ☐ | - |
| 错误提示 | ☐ | ☐ | ☐ | - |
| 成功提示 | ☐ | ☐ | ☐ | - |
| 时间线 | ☐ | ☐ | ☐ | - |
| **总计通过率** | - | - | - | **0%** |

---

## 6. 风险与缓解

### 6.1 风险清单

| 风险 | 影响 | 可能性 | 缓解措施 |
|------|------|--------|----------|
| 翻译不准确 | 用户体验差 | 中 | 德语翻译使用专业翻译工具+人工校对 |
| 文本溢出 | 布局破坏 | 低 | 测试时检查所有分辨率 |
| 语言包加载失败 | 页面空白 | 低 | 回退机制（fallback到中文） |
| 动态文本遗漏 | 部分文本未翻译 | 高 | 详细清单+代码审查 |
| 性能影响 | 加载变慢 | 低 | 语言包仅~5KB，影响可忽略 |

---

### 6.2 回滚方案

如遇严重问题，可快速回滚：

1. 移除 `<script src="/static/lib/i18n/i18n.js"></script>` 引入
2. 移除所有 `data-i18n` 属性
3. 移除语言选择器

**回滚命令**：
```bash
# 移除i18n脚本引入（示例）
sed -i '/i18n.js/d' static/monitor/index.html
sed -i '/i18n.js/d' static/monitor/live-logs.html
sed -i '/i18n.js/d' static/monitor/history-logs.html
```

---

## 7. 时间估算

| 阶段 | 工作内容 | 预计时间 |
|------|----------|----------|
| 阶段1 | 框架搭建 | 0.5人日 |
| 阶段2 | 静态文本国际化 | 1人日 |
| 阶段3 | 动态文本国际化 | 1.5人日 |
| 阶段4 | 完善与测试 | 0.5人日 |
| 缓冲 | 预留问题处理 | 0.5人日 |
| **总计** | - | **4人日** |

---

## 8. 附录

### 8.1 语言代码映射表

| 浏览器语言 | 映射到 | 说明 |
|------------|--------|------|
| zh, zh-CN, zh-Hans | zh-CN | 简体中文 |
| zh-TW, zh-HK | zh-CN | 繁体中文暂不支持，映射到简体 |
| en, en-US, en-GB | en-US | 英语 |
| de, de-DE, de-AT, de-CH | de-DE | 德语（含奥地利、瑞士德语） |
| 其他 | zh-CN | 不支持的语言默认中文 |

---

### 8.2 文本长度对比（示例）

| 键名 | 中文 | 英文 | 德语 | 最长 |
|------|------|------|------|------|
| btn.query | 查询 (2) | Query (5) | Abfrage (7) | 德语 |
| status.loading | 加载中... (5) | Loading... (10) | Laden... (7) | 英文 |
| metric.cpu | CPU 使用率 (7) | CPU Usage (9) | CPU-Auslastung (14) | 德语 |

**注意**：德语文本通常较长，需测试布局适配。

---

### 8.3 实施检查清单

#### 阶段1检查清单
- [ ] 创建 `static/lib/i18n/` 目录
- [ ] 创建 `i18n.js` 核心脚本
- [ ] 创建 `zh-CN.js` 中文语言包
- [ ] 创建 `en-US.js` 英文语言包
- [ ] 创建 `de-DE.js` 德语语言包
- [ ] 控制台无报错
- [ ] `i18n.t('test')` 可调用

#### 阶段2检查清单
- [ ] index.html 引入i18n脚本
- [ ] index.html 静态文本添加data-i18n
- [ ] live-logs.html 引入i18n脚本
- [ ] live-logs.html 静态文本添加data-i18n
- [ ] history-logs.html 引入i18n脚本
- [ ] history-logs.html 静态文本添加data-i18n
- [ ] 语言切换菜单添加
- [ ] 静态文本切换测试通过

#### 阶段3检查清单
- [ ] monitor.js 动态文本替换
- [ ] live-logs.html 动态文本替换
- [ ] history-logs.html 动态文本替换
- [ ] alert提示翻译
- [ ] 表格内容翻译
- [ ] 弹窗内容翻译
- [ ] 动态文本测试通过

#### 阶段4检查清单
- [ ] CSS样式调整
- [ ] 边界情况处理
- [ ] 回退机制测试
- [ ] 三语言完整测试
- [ ] 文本溢出检查
- [ ] 测试报告输出

---

**文档版本**：v1.0  
**创建日期**：2026-05-23  
**作者**：MyAPS开发团队  
**预计完成时间**：4人日
