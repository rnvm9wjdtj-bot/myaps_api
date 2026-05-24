# MDS模块国际化实施方案

**文档类型**：技术方案  
**创建日期**：2026-05-24  
**版本**：v1.0  
**状态**：待评审  

---

## 一、项目概况

### 1.1 背景

监控模块（Monitor）已完成国际化支持，支持中文、英文、德语三语切换。现需对MDS（数据清洗管理）模块实施相同的国际化改造。

### 1.2 目标

- 支持简体中文、英语、德语三种语言（与Monitor模块保持一致）
- 与Monitor模块使用统一的国际化框架
- 用户切换语言时，Monitor和MDS同时生效
- 保持代码简洁，避免重复实现
- 支持无刷新语言切换，保持页面状态

### 1.3 范围

- 3个HTML页面
- 7个JavaScript文件
- 约5,682行代码
- 约746处中文文本需翻译

---

## 二、当前状态分析

### 2.1 文件结构

**HTML页面**（3个）：

| 文件 | 行数 | 用途 |
|------|------|------|
| `index.html` | 318 | 首页：模块卡片导航、全局操作 |
| `user-guide.html` | 202 | 操作指引页面 |
| `pages/template.html` | 258 | 数据操作页面模板 |

**JavaScript文件**（7个）：

| 文件 | 行数 | 功能 |
|------|------|------|
| `mds-page-controller.js` | 1892 | 页面控制器（核心） |
| `data-table.js` | 1517 | 数据表格组件 |
| `modal-manager.js` | 564 | 模态框管理器 |
| `common.js` | 540 | 公共函数库、状态枚举 |
| `form-renderer.js` | 346 | 表单渲染器 |
| `global-ops-controller.js` | 343 | 全局操作控制器 |
| `status-card.js` | 302 | 状态统计卡片 |

**总代码量**：5,682行

### 2.2 文本分类统计

| 优先级 | 类型 | 数量 | 示例 |
|--------|------|------|------|
| P0 | 状态标签 | 28处 | 待处理、已推送 |
| P1 | 操作按钮 | 45处 | 导入、校验、推送 |
| P2 | 导航菜单 | 14处 | 物料、BOM、模具 |
| P3 | 弹窗文本 | 120处 | 确认、取消、提示 |
| P4 | 错误消息 | 85处 | 查询失败、上传失败 |
| P5 | 表格文本 | 150处 | 编辑、删除、分页 |
| P6 | 其他提示 | 304处 | 加载中、暂无数据 |
| **合计** | | **746处** | |

### 2.3 复杂度评估

**等级**：⭐⭐⭐⭐☆（高复杂度）

**高复杂度因素**：
- 硬编码文本数量庞大（746处）
- 动态拼接文本多（需参数化翻译）
- 组件嵌套深（表格、表单、弹窗多层嵌套）

**低复杂度因素**：
- 代码结构清晰，模块化设计
- 页面数量少，模板复用率高
- 无第三方UI组件库

---

## 三、语言包组织方案

### 3.1 方案对比

| 方案 | 目录结构 | 支持语言 | 优点 | 缺点 | 推荐度 |
|------|----------|----------|------|------|--------|
| **A. 统一管理** | `static/lib/i18n/` | 中/英/德 | 框架复用<br>全局切换<br>维护简单<br>与Monitor一致 | 单文件较大 | ⭐⭐⭐⭐⭐ |
| **B. 独立目录** | `static/mds/locales/` | 中/英/德 | 模块独立<br>按需加载 | 重复代码<br>切换复杂 | ⭐⭐☆☆☆ |
| **C. 命名空间** | `static/lib/i18n/{module}/` | 中/英/德 | 框架复用<br>模块隔离 | 需改造框架 | ⭐⭐⭐☆☆ |

### 3.2 推荐方案：A（统一管理 + 命名空间）

**目录结构**：
```
static/lib/i18n/
├── i18n.js              # 统一框架（已存在）
├── zh-CN.js             # 中文语言包（扩展）
├── en-US.js             # 英文语言包（扩展）
└── de-DE.js             # 德语语言包（扩展）
```

**语言包结构**（命名空间）：
```javascript
// zh-CN.js（简体中文）
window.__i18n_zh_CN__ = {
    // ========== 通用文本 ==========
    'common.confirm': '确定',
    'common.cancel': '取消',
    'common.loading': '加载中...',
    
    // ========== Monitor模块 ==========
    'monitor.page.title': 'MyAPI 系统监控面板',
    'monitor.status.healthy': '● 系统正常',
    // ... (现有405条)
    
    // ========== MDS模块 ==========
    'mds.app.title': '数据清洗管理系统',
    'mds.nav.material': '物料',
    'mds.action.validate': '校验',
    'mds.status.pending': '待处理',
    // ... (新增约750条)
};

// en-US.js（英语）
window.__i18n_en_US__ = {
    // ========== Common ==========
    'common.confirm': 'Confirm',
    'common.cancel': 'Cancel',
    'common.loading': 'Loading...',
    
    // ========== Monitor Module ==========
    'monitor.page.title': 'MyAPI System Monitor',
    'monitor.status.healthy': '● System Healthy',
    // ... (现有405条)
    
    // ========== MDS Module ==========
    'mds.app.title': 'Data Staging Management System',
    'mds.nav.material': 'Material',
    'mds.action.validate': 'Validate',
    'mds.status.pending': 'Pending',
    // ... (新增约750条)
};

// de-DE.js（德语）
window.__i18n_de_DE__ = {
    // ========== Allgemein ==========
    'common.confirm': 'Bestätigen',
    'common.cancel': 'Abbrechen',
    'common.loading': 'Laden...',
    
    // ========== Monitor-Modul ==========
    'monitor.page.title': 'MyAPI Systemüberwachung',
    'monitor.status.healthy': '● System gesund',
    // ... (现有405条)
    
    // ========== MDS-Modul ==========
    'mds.app.title': 'Daten-Staging-Verwaltungssystem',
    'mds.nav.material': 'Material',
    'mds.action.validate': 'Validieren',
    'mds.status.pending': 'Ausstehend',
    // ... (新增约750条)
};
```

### 3.3 方案优势

1. ✅ **框架复用**：Monitor的i18n.js已成熟，无需重复开发
2. ✅ **全局切换**：用户切换语言，Monitor和MDS同时生效
3. ✅ **代码简洁**：避免多套i18n实例，降低复杂度
4. ✅ **维护方便**：语言包集中管理，便于批量修改
5. ✅ **命名清晰**：通过`monitor.`和`mds.`前缀区分模块

### 3.4 语言包大小预估

| 模块 | 翻译条目 |
|------|----------|
| Monitor（现有） | 405条 |
| MDS（新增） | 750条 |
| **合并后** | **约1155条/语言** |
| **文件大小** | **约60-80KB** |

单文件大小可接受，无需拆分。

---

## 四、实施计划

### 4.1 分阶段实施（推荐）

**Phase 1**：基础准备 + P0/P1（状态+按钮）
- 工作量：4天
- 输出：框架复用、三语言包创建、状态枚举改造

**Phase 2**：P2/P3（导航+弹窗）
- 工作量：5天
- 输出：HTML改造、弹窗翻译

**Phase 3**：P4/P5（错误+表格）
- 工作量：6天
- 输出：错误处理、表格组件改造

**Phase 4**：P6（其他提示）
- 工作量：4天
- 输出：完成所有翻译、全面测试

**总工作量**：19人天（约4周）

**说明**：相比Monitor模块的4人日，MDS模块工作量更大，原因：
1. 翻译文本数量更多（746处 vs 158处）
2. 三语言翻译工作量增加50%
3. 状态枚举、表格组件改造复杂度高
4. 动态消息参数化处理更复杂

### 4.2 详细实施步骤

#### Phase 1: 基础准备（4天）

**Day 1: 框架复用与语言包创建**
- [ ] 在现有语言包中添加MDS命名空间
- [ ] 提取P0级文本（状态标签，28处）
- [ ] 提取P1级文本（操作按钮，45处）
- [ ] 编写简体中文、英语、德语三语言翻译

**Day 2: 状态枚举改造**
- [ ] 改造`common.js`的`STAGING_STATUS`
- [ ] 将label改为getter动态翻译
- [ ] 改造`status-card.js`
- [ ] 测试三语言状态标签翻译

**Day 3-4: 验证与测试**
- [ ] 测试状态标签三语言翻译
- [ ] 测试操作按钮三语言翻译
- [ ] 测试语言切换功能（无刷新）
- [ ] 测试德语文本布局适配

#### Phase 2: 导航与弹窗（5天）

**Day 5-6: HTML改造**
- [ ] `index.html`添加data-i18n属性
- [ ] `template.html`添加data-i18n属性
- [ ] `user-guide.html`添加data-i18n属性
- [ ] 提取P2级文本（导航菜单，14处）
- [ ] 测试三语言HTML文本翻译

**Day 7-9: 弹窗改造**
- [ ] 改造`modal-manager.js`
- [ ] 改造`form-renderer.js`
- [ ] 提取P3级文本（弹窗文本，120处）
- [ ] 编写三语言翻译
- [ ] 测试弹窗三语言显示

#### Phase 3: 错误与表格（6天）

**Day 10-11: 错误处理**
- [ ] 改造错误消息处理函数
- [ ] 创建后端错误码+参数处理机制
- [ ] 提取P4级文本（错误消息，85处）
- [ ] 编写三语言翻译
- [ ] 测试三语言错误提示

**Day 12-15: 表格改造**
- [ ] 改造`data-table.js`
- [ ] 改造分页控件
- [ ] 改造空状态提示
- [ ] 提取P5级文本（表格文本，150处）
- [ ] 编写三语言翻译
- [ ] 测试表格三语言显示

#### Phase 4: 完成与测试（4天）

**Day 16-17: 完成翻译**
- [ ] 提取P6级文本（其他提示，304处）
- [ ] 改造`mds-page-controller.js`
- [ ] 改造`global-ops-controller.js`
- [ ] 编写三语言翻译

**Day 18-19: 测试验证**
- [ ] 功能测试：所有页面文本翻译
- [ ] 三语言切换测试（无刷新）
- [ ] 德语文本布局验证
- [ ] 回归测试：现有功能不受影响
- [ ] 编写实施文档

---

## 五、技术方案

### 5.1 状态枚举改造

**改造前**：
```javascript
const STAGING_STATUS = {
    PENDING: {
        value: 'pending',
        label: '待处理',
        color: '#ff9300',
        icon: '⏳'
    }
};
```

**改造后**：
```javascript
const STAGING_STATUS = {
    PENDING: {
        value: 'pending',
        labelKey: 'mds.status.pending',  // 翻译键
        color: '#ff9300',
        icon: '⏳',
        get label() {
            return typeof i18n !== 'undefined' ? 
                i18n.t(this.labelKey) : '待处理';
        }
    }
};
```

### 5.2 动态消息参数化

**改造前**：
```javascript
showMessage(`校验完成: 通过${pass}条，失败${fail}条`, 'success');
```

**改造后**：
```javascript
const msg = typeof i18n !== 'undefined' ?
    i18n.t('mds.validation.complete', { pass, fail }) :
    `校验完成: 通过${pass}条，失败${fail}条`;
showMessage(msg, 'success');
```

**语言包定义**：
```javascript
// zh-CN.js（简体中文）
'mds.validation.complete': '校验完成: 通过{pass}条，失败{fail}条',

// en-US.js（英语）
'mds.validation.complete': 'Validation: {pass} passed, {fail} failed',

// de-DE.js（德语）
'mds.validation.complete': 'Validierung: {pass} bestanden, {fail} fehlgeschlagen',
```

### 5.3 后端错误消息处理

**方案：后端返回错误码+参数，前端统一翻译**

**后端响应格式**：
```python
# 后端返回错误码和参数
{
    "success": false,
    "error": {
        "code": "DUPLICATE_KEY",  # 错误码
        "params": {                # 动态参数
            "field": "MaterialNo",
            "value": "MAT001"
        }
    }
}
```

**前端翻译处理**：
```javascript
// 错误码翻译映射表（在语言包中定义）
// zh-CN.js
'mds.error.DUPLICATE_KEY': '数据重复: {field}={value} 已存在',
'mds.error.INVALID_FORMAT': '格式错误: {field} 格式不正确',
'mds.error.FOREIGN_KEY_VIOLATION': '外键约束违反: {field} 引用不存在',
'mds.error.VALIDATION_FAILED': '校验失败: {reason}',

// en-US.js
'mds.error.DUPLICATE_KEY': 'Duplicate data: {field}={value} already exists',
'mds.error.INVALID_FORMAT': 'Invalid format: {field} format is incorrect',
'mds.error.FOREIGN_KEY_VIOLATION': 'Foreign key violation: {field} reference not found',
'mds.error.VALIDATION_FAILED': 'Validation failed: {reason}',

// de-DE.js
'mds.error.DUPLICATE_KEY': 'Doppelter Dateneintrag: {field}={value} bereits vorhanden',
'mds.error.INVALID_FORMAT': 'Ungültiges Format: {field} Format ist fehlerhaft',
'mds.error.FOREIGN_KEY_VIOLATION': 'Fremdschlüssel-Verletzung: {field} Referenz nicht gefunden',
'mds.error.VALIDATION_FAILED': 'Validierung fehlgeschlagen: {reason}',

// 翻译函数
function translateError(response) {
    if (!response.error) {
        return response.message || 'Unknown error';
    }
    
    const { code, params = {} } = response.error;
    const errorKey = `mds.error.${code}`;
    
    // 使用i18n翻译
    if (typeof i18n !== 'undefined') {
        return i18n.t(errorKey, params);
    }
    
    // 回退：返回错误码
    return code;
}

// 使用示例
async function handleApiResponse(response) {
    if (!response.success) {
        const errorMsg = translateError(response);
        showError(errorMsg);
    }
}
```

**方案优势**：
- ✅ 后端无需关心具体翻译文本，只需返回错误码
- ✅ 前端统一翻译，支持多语言
- ✅ 错误码和参数分离，灵活性高
- ✅ 新增错误类型只需在语言包中添加翻译项

### 5.4 HTML模板改造

**改造前**：
```html
<button><i class="bi bi-shield-check"></i> 校验</button>
```

**改造后**：
```html
<button>
    <i class="bi bi-shield-check"></i> 
    <span data-i18n="mds.action.validate">校验</span>
</button>
```

**初始化翻译**：
```javascript
// 页面加载后
document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const text = typeof i18n !== 'undefined' ? i18n.t(key) : key;
    el.textContent = text;
});
```

### 5.5 语言切换UI集成

**在导航栏添加语言选择器**：
```html
<select id="lang-selector" onchange="switchLanguage(this.value)">
    <option value="zh-CN">🇨🇳 中文</option>
    <option value="en-US">🇺🇸 English</option>
    <option value="de-DE">🇩🇪 Deutsch</option>
</select>
```

**无刷新语言切换方案**：
```javascript
/**
 * 语言切换（无刷新）
 * 保持页面状态，动态更新所有文本
 */
async function switchLanguage(lang) {
    if (typeof i18n === 'undefined') {
        console.warn('i18n not initialized');
        return;
    }
    
    // 调用i18n框架切换语言
    await i18n.switchLanguage(lang);
    
    // 更新状态枚举（使用getter动态翻译，已自动更新）
    // 无需手动处理
    
    // 更新动态生成的DOM元素
    updateDynamicElements();
    
    // 触发自定义事件（供组件监听）
    window.dispatchEvent(new CustomEvent('languageChanged', {
        detail: { lang: lang }
    }));
    
    console.log(`[i18n] Language switched to ${lang} (no page reload)`);
}

/**
 * 更新动态生成的DOM元素
 * 如：表格内容、弹窗内容、状态卡片等
 */
function updateDynamicElements() {
    // 1. 更新表格内容（如果表格已渲染）
    if (window.dataTableInstance) {
        window.dataTableInstance.refresh();
    }
    
    // 2. 更新状态卡片
    if (window.statusCardInstance) {
        window.statusCardInstance.refresh();
    }
    
    // 3. 更新已打开的模态框
    const modals = document.querySelectorAll('.modal.show');
    modals.forEach(modal => {
        // 重新应用翻译到模态框内的元素
        modal.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            el.textContent = i18n.t(key);
        });
    });
    
    // 4. 更新表格操作按钮（编辑、删除等）
    document.querySelectorAll('[data-i18n-action]').forEach(el => {
        const key = el.getAttribute('data-i18n-action');
        el.textContent = i18n.t(key);
    });
}

// 监听语言切换事件（组件可订阅）
window.addEventListener('languageChanged', (e) => {
    const newLang = e.detail.lang;
    console.log(`Component notified: language changed to ${newLang}`);
    
    // 组件特定的更新逻辑
    // 例如：重新渲染图表标题、更新提示文本等
});
```

**i18n框架增强（支持无刷新切换）**：
```javascript
// i18n.js中的switchLanguage方法
async switchLanguage(lang) {
    if (lang === this.currentLang) return;
    
    try {
        // 1. 保存到localStorage
        localStorage.setItem('monitor-lang', lang);
        
        // 2. 加载新语言包
        this.currentLang = lang;
        await this.loadLanguage(lang);
        
        // 3. 应用翻译到所有静态元素
        this.applyTranslations();
        
        // 4. 更新语言选择器状态
        this.updateLangSelector();
        
        // 5. 触发事件（不刷新页面）
        window.dispatchEvent(new CustomEvent('langchange', { 
            detail: { lang: lang } 
        }));
        
        console.log(`[i18n] Language switched to: ${lang} (no reload)`);
    } catch (error) {
        console.error('[i18n] Language switch failed:', error);
    }
}
```

**无刷新切换优势**：
- ✅ 保持页面滚动位置
- ✅ 保持表单输入状态
- ✅ 保持表格筛选条件
- ✅ 保持分页状态
- ✅ 用户体验流畅，无白屏闪烁

---

## 六、风险与对策

### 6.1 风险清单

| 风险 | 级别 | 影响 | 对策 |
|------|------|------|------|
| 后端错误消息硬编码 | 高 | 错误提示无法翻译 | 后端返回错误码+参数，前端统一翻译 |
| 动态消息参数化 | 中 | 翻译不准确 | 使用i18n插值功能，三语言测试验证 |
| Bootstrap弹窗动态生成 | 中 | 弹窗内容不更新 | 弹窗打开时重新应用翻译，语言切换事件监听 |
| 状态枚举多处使用 | 中 | 改造遗漏 | 改造为getter动态翻译，无需手动刷新 |
| 德语文本较长 | 中 | 布局溢出 | CSS增加文本自适应，德语专项布局测试 |
| 三语言翻译质量 | 低 | 德语翻译不准确 | 使用专业翻译工具+人工校对 |
| 工作量大 | 低 | 实施周期长 | 分阶段实施，P0优先，三语言并行翻译 |

### 6.2 质量保证措施

1. **代码审查**：每个阶段完成后进行代码审查
2. **单元测试**：编写翻译函数单元测试
3. **回归测试**：确保现有功能不受影响
4. **性能测试**：验证语言包加载性能
5. **用户验收**：邀请用户测试语言切换功能

---

## 七、翻译示例

### 7.1 核心翻译键设计

#### 7.1.1 简体中文（zh-CN.js）

```javascript
// zh-CN.js 扩展内容
{
    // ========== MDS模块 ==========
    
    // 应用标题
    'mds.app.title': '数据清洗管理系统',
    'mds.app.guide': '操作指引',
    'mds.app.apiDoc': 'API文档',
    
    // 导航菜单
    'mds.nav.material': '物料',
    'mds.nav.matVer': '产线版本',
    'mds.nav.workcenter': '工作中心',
    'mds.nav.matWc': '工艺路线',
    'mds.nav.bom': 'BOM',
    'mds.nav.mold': '模具',
    'mds.nav.matWcMold': '机台模具',
    
    // 操作按钮
    'mds.action.import': '导入',
    'mds.action.validate': '校验',
    'mds.action.sync': '推送',
    'mds.action.query': '查询',
    'mds.action.reset': '重置',
    'mds.action.save': '保存',
    'mds.action.delete': '删除',
    'mds.action.cancel': '取消',
    'mds.action.confirm': '确定',
    
    // 状态标签
    'mds.status.all': '全部',
    'mds.status.pending': '待处理',
    'mds.status.compliancePass': '初检通过',
    'mds.status.complianceError': '初检错误',
    'mds.status.relationPass': '联检通过',
    'mds.status.relationError': '联检错误',
    'mds.status.syncError': '推送失败',
    'mds.status.synced': '已推送',
    
    // 校验相关
    'mds.validation.complete': '校验完成: 通过{pass}条，失败{fail}条',
    'mds.validation.noPending': '没有待处理的记录',
    'mds.validation.confirmStart': '缺失的字段值将自动填充为默认值，确定开始校验吗？',
    'mds.validation.processing': '校验中',
    'mds.validation.failed': '校验失败',
    'mds.validation.progress': '已处理 {current}/{total}',
    
    // 推送相关
    'mds.sync.complete': '推送完成: {accounts}个账套, 成功{synced}条, 去重失败{dedup}条, 其他失败{failed}条',
    'mds.sync.noData': '没有【联合校验通过】或【同步失败】的记录可推送',
    'mds.sync.selectTarget': '请至少选择一个目标账套',
    'mds.sync.selectMode': '选择推送模式',
    'mds.sync.incremental': '增量推送',
    'mds.sync.refresh': '刷新推送',
    'mds.sync.confirmRefresh': '刷新推送将删除正式表所有数据，请谨慎操作！',
    
    // 上传相关
    'mds.upload.success': '导入完成: 成功{inserted}条, 跳过{skipped}条',
    'mds.upload.invalidType': '请上传Excel或CSV文件',
    'mds.upload.noFile': '请先选择文件',
    'mds.upload.dragDrop': '点击或拖拽文件上传（支持 .xlsx, .xls, .csv）',
    
    // 表格相关
    'mds.table.noData': '暂无数据',
    'mds.table.loading': '加载中...',
    'mds.table.selectAll': '全选',
    'mds.table.perPage': '条/页',
    'mds.table.total': '共 {count} 条',
    'mds.table.edit': '编辑',
    'mds.table.delete': '删除',
    'mds.table.export': '导出模板',
    
    // 弹窗相关
    'mds.modal.confirm': '确认',
    'mds.modal.cancel': '取消',
    'mds.modal.close': '关闭',
    'mds.modal.importTitle': '导入Excel数据',
    'mds.modal.filterTitle': '精准筛选',
    'mds.modal.editTitle': '编辑记录',
    'mds.modal.validationRules': '校验规则',
    
    // 错误消息
    'mds.error.queryFailed': '查询失败',
    'mds.error.uploadFailed': '上传失败',
    'mds.error.timeout': '请求超时',
    'mds.error.loadFailed': '加载失败，请重试'
}
```

#### 7.1.2 英语（en-US.js）

```javascript
// en-US.js 扩展内容
{
    // ========== MDS Module ==========
    
    // Application Title
    'mds.app.title': 'Data Staging Management System',
    'mds.app.guide': 'User Guide',
    'mds.app.apiDoc': 'API Documentation',
    
    // Navigation Menu
    'mds.nav.material': 'Material',
    'mds.nav.matVer': 'Material Version',
    'mds.nav.workcenter': 'Work Center',
    'mds.nav.matWc': 'Routing',
    'mds.nav.bom': 'BOM',
    'mds.nav.mold': 'Mold',
    'mds.nav.matWcMold': 'Machine Mold',
    
    // Action Buttons
    'mds.action.import': 'Import',
    'mds.action.validate': 'Validate',
    'mds.action.sync': 'Sync',
    'mds.action.query': 'Query',
    'mds.action.reset': 'Reset',
    'mds.action.save': 'Save',
    'mds.action.delete': 'Delete',
    'mds.action.cancel': 'Cancel',
    'mds.action.confirm': 'Confirm',
    
    // Status Labels
    'mds.status.all': 'All',
    'mds.status.pending': 'Pending',
    'mds.status.compliancePass': 'Compliance Pass',
    'mds.status.complianceError': 'Compliance Error',
    'mds.status.relationPass': 'Relation Pass',
    'mds.status.relationError': 'Relation Error',
    'mds.status.syncError': 'Sync Failed',
    'mds.status.synced': 'Synced',
    
    // Validation Related
    'mds.validation.complete': 'Validation: {pass} passed, {fail} failed',
    'mds.validation.noPending': 'No pending records',
    'mds.validation.confirmStart': 'Missing field values will be filled with defaults. Proceed?',
    'mds.validation.processing': 'Validating',
    'mds.validation.failed': 'Validation Failed',
    'mds.validation.progress': 'Processed {current}/{total}',
    
    // Sync Related
    'mds.sync.complete': 'Sync complete: {accounts} accounts, {synced} synced, {dedup} dedup failed, {failed} other failed',
    'mds.sync.noData': 'No [Relation Pass] or [Sync Failed] records to sync',
    'mds.sync.selectTarget': 'Please select at least one target account',
    'mds.sync.selectMode': 'Select Sync Mode',
    'mds.sync.incremental': 'Incremental Sync',
    'mds.sync.refresh': 'Refresh Sync',
    'mds.sync.confirmRefresh': 'Refresh sync will delete all data in the main table. Proceed with caution!',
    
    // Upload Related
    'mds.upload.success': 'Import complete: {inserted} inserted, {skipped} skipped',
    'mds.upload.invalidType': 'Please upload Excel or CSV file',
    'mds.upload.noFile': 'Please select a file first',
    'mds.upload.dragDrop': 'Click or drag file to upload (supports .xlsx, .xls, .csv)',
    
    // Table Related
    'mds.table.noData': 'No data',
    'mds.table.loading': 'Loading...',
    'mds.table.selectAll': 'Select All',
    'mds.table.perPage': 'per page',
    'mds.table.total': 'Total {count} records',
    'mds.table.edit': 'Edit',
    'mds.table.delete': 'Delete',
    'mds.table.export': 'Export Template',
    
    // Modal Related
    'mds.modal.confirm': 'Confirm',
    'mds.modal.cancel': 'Cancel',
    'mds.modal.close': 'Close',
    'mds.modal.importTitle': 'Import Excel Data',
    'mds.modal.filterTitle': 'Advanced Filter',
    'mds.modal.editTitle': 'Edit Record',
    'mds.modal.validationRules': 'Validation Rules',
    
    // Error Messages
    'mds.error.queryFailed': 'Query Failed',
    'mds.error.uploadFailed': 'Upload Failed',
    'mds.error.timeout': 'Request Timeout',
    'mds.error.loadFailed': 'Load Failed, Please Retry'
}
```

#### 7.1.3 德语（de-DE.js）

```javascript
// de-DE.js 扩展内容
{
    // ========== MDS-Modul ==========
    
    // Anwendungstitel
    'mds.app.title': 'Daten-Staging-Verwaltungssystem',
    'mds.app.guide': 'Benutzerhandbuch',
    'mds.app.apiDoc': 'API-Dokumentation',
    
    // Navigationsmenü
    'mds.nav.material': 'Material',
    'mds.nav.matVer': 'Materialversion',
    'mds.nav.workcenter': 'Arbeitsplatz',
    'mds.nav.matWc': 'Arbeitsplan',
    'mds.nav.bom': 'Stückliste',
    'mds.nav.mold': 'Werkzeug',
    'mds.nav.matWcMold': 'Maschinen-Werkzeug',
    
    // Aktionsschaltflächen
    'mds.action.import': 'Importieren',
    'mds.action.validate': 'Validieren',
    'mds.action.sync': 'Synchronisieren',
    'mds.action.query': 'Abfragen',
    'mds.action.reset': 'Zurücksetzen',
    'mds.action.save': 'Speichern',
    'mds.action.delete': 'Löschen',
    'mds.action.cancel': 'Abbrechen',
    'mds.action.confirm': 'Bestätigen',
    
    // Statusbezeichnungen
    'mds.status.all': 'Alle',
    'mds.status.pending': 'Ausstehend',
    'mds.status.compliancePass': 'Compliance bestanden',
    'mds.status.complianceError': 'Compliance fehlerhaft',
    'mds.status.relationPass': 'Relation bestanden',
    'mds.status.relationError': 'Relation fehlerhaft',
    'mds.status.syncError': 'Sync fehlgeschlagen',
    'mds.status.synced': 'Synchronisiert',
    
    // Validierungsbezogen
    'mds.validation.complete': 'Validierung: {pass} bestanden, {fail} fehlgeschlagen',
    'mds.validation.noPending': 'Keine ausstehenden Datensätze',
    'mds.validation.confirmStart': 'Fehlende Feldwerte werden mit Standardwerten gefüllt. Fortfahren?',
    'mds.validation.processing': 'Validierung läuft',
    'mds.validation.failed': 'Validierung fehlgeschlagen',
    'mds.validation.progress': 'Verarbeitet {current}/{total}',
    
    // Synchronisationsbezogen
    'mds.sync.complete': 'Sync abgeschlossen: {accounts} Konten, {synced} synchronisiert, {dedup} Dedup fehlgeschlagen, {failed} sonstige fehlgeschlagen',
    'mds.sync.noData': 'Keine [Relation bestanden] oder [Sync fehlgeschlagen] Datensätze zum Synchronisieren',
    'mds.sync.selectTarget': 'Bitte mindestens ein Zielkonto auswählen',
    'mds.sync.selectMode': 'Synchronisationsmodus wählen',
    'mds.sync.incremental': 'Inkrementelle Synchronisation',
    'mds.sync.refresh': 'Aktualisierungs-Sync',
    'mds.sync.confirmRefresh': 'Aktualisierungs-Sync löscht alle Daten in der Haupttabelle. Mit Vorsicht fortfahren!',
    
    // Upload-bezogen
    'mds.upload.success': 'Import abgeschlossen: {inserted} eingefügt, {skipped} übersprungen',
    'mds.upload.invalidType': 'Bitte Excel- oder CSV-Datei hochladen',
    'mds.upload.noFile': 'Bitte zuerst eine Datei auswählen',
    'mds.upload.dragDrop': 'Klicken oder Datei ziehen (unterstützt .xlsx, .xls, .csv)',
    
    // Tabellenbezogen
    'mds.table.noData': 'Keine Daten',
    'mds.table.loading': 'Laden...',
    'mds.table.selectAll': 'Alle auswählen',
    'mds.table.perPage': 'pro Seite',
    'mds.table.total': 'Gesamt {count} Datensätze',
    'mds.table.edit': 'Bearbeiten',
    'mds.table.delete': 'Löschen',
    'mds.table.export': 'Vorlage exportieren',
    
    // Modal-bezogen
    'mds.modal.confirm': 'Bestätigen',
    'mds.modal.cancel': 'Abbrechen',
    'mds.modal.close': 'Schließen',
    'mds.modal.importTitle': 'Excel-Daten importieren',
    'mds.modal.filterTitle': 'Erweiterter Filter',
    'mds.modal.editTitle': 'Datensatz bearbeiten',
    'mds.modal.validationRules': 'Validierungsregeln',
    
    // Fehlermeldungen
    'mds.error.queryFailed': 'Abfrage fehlgeschlagen',
    'mds.error.uploadFailed': 'Upload fehlgeschlagen',
    'mds.error.timeout': 'Anfrage-Timeout',
    'mds.error.loadFailed': 'Laden fehlgeschlagen, bitte erneut versuchen'
}
```

---

## 八、验收标准

### 8.1 功能验收

- [ ] 所有页面支持语言切换（简体中文、英语、德语）
- [ ] 三语言文本正确显示
- [ ] 状态枚举动态翻译
- [ ] 操作按钮文本翻译
- [ ] 弹窗内容翻译
- [ ] 表单验证消息翻译
- [ ] 错误提示翻译（支持参数化）
- [ ] 表格空状态翻译
- [ ] 分页控件翻译
- [ ] 无刷新语言切换（保持页面状态）

### 8.2 性能验收

- [ ] 语言包加载时间 < 300ms（三语言包总计约120KB）
- [ ] 语言切换响应时间 < 100ms（无刷新）
- [ ] 内存占用增加 < 8MB（三语言包加载）
- [ ] 无刷新切换无白屏闪烁

### 8.3 兼容性验收

- [ ] Chrome浏览器兼容
- [ ] Firefox浏览器兼容
- [ ] Edge浏览器兼容
- [ ] Safari浏览器兼容（如有条件）
- [ ] 德语文本在不同浏览器下正确显示（无乱码）

### 8.4 文档验收

- [ ] 实施文档完整
- [ ] 翻译键命名规范
- [ ] 代码注释清晰

---

## 九、后续维护

### 9.1 新增翻译流程

1. 在代码中使用翻译键：`i18n.t('mds.new.key')`
2. 在所有语言包中添加对应翻译
3. 更新翻译键文档
4. 测试验证

### 9.2 翻译质量保证

- 使用统一的翻译键命名规范
- 定期检查未使用的翻译键
- 保持翻译文本简洁准确

### 9.3 扩展其他语言

如需支持其他语言（如日语、法语等）：
1. 创建新语言包文件（如`ja-JP.js`）
2. 复制`zh-CN.js`作为模板
3. 翻译所有文本
4. 在语言选择器中添加选项

---

## 十、附录

### 10.1 相关文档

- [Monitor模块国际化实施计划](./Monitor-i18n-Implementation-Plan.md)
- [Monitor模块国际化测试报告](./Monitor-i18n-Test-Report.md)
- [AGENTS.md 开发指南](../../AGENTS.md)

### 10.2 参考资料

- i18next官方文档：https://www.i18next.com/
- Bootstrap国际化最佳实践
- FastAPI国际化方案

### 10.3 变更历史

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-05-24 | 初版创建 | CodeArts |
| v1.1 | 2026-05-24 | 优化技术方案：支持简体中文/英语/德语三语言、无刷新语言切换、后端错误码+参数化处理 | CodeArts |

---

**文档状态**：待评审  
**下一步**：评审通过后开始Phase 1实施

---

## 十一、三语言支持补充说明

### 11.1 语言包文件规划

基于Monitor模块已实现的三语言支持，MDS模块将复用相同的语言包文件：

```
static/lib/i18n/
├── i18n.js              # 核心框架（已存在，无需修改）
├── zh-CN.js             # 简体中文（扩展MDS命名空间）
├── en-US.js             # 英语（扩展MDS命名空间）
└── de-DE.js             # 德语（扩展MDS命名空间）
```

### 11.2 德语翻译注意事项

**1. 文本长度**
德语文本通常比中文和英文长20%-40%，需特别注意：
- 按钮文本：如"Validieren"（德语）vs "Validate"（英语）
- 表格列名：需预留足够的列宽
- 错误提示：可能需要自动换行或省略

**2. 特殊字符**
德语包含特殊字符（ä, ö, ü, ß），需确保：
- HTML文件使用UTF-8编码
- 语言包文件保存为UTF-8无BOM格式
- 服务器响应头正确设置Content-Type

**3. 复合词**
德语倾向使用复合词，翻译时需考虑：
- 可读性：适当使用连字符提高可读性
- 一致性：统一术语翻译规则

**示例对比**：
| 中文 | 英语 | 德语 | 长度对比 |
|------|------|------|----------|
| 数据清洗管理系统 | Data Staging Management System | Daten-Staging-Verwaltungssystem | 德语最长 |
| 校验 | Validate | Validieren | 德语较长 |
| 待处理 | Pending | Ausstehend | 德语较长 |

### 11.3 三语言翻译流程

**流程图**：
```
1. 提取中文文本 → 2. 编写中文翻译键
                  ↓
3. 翻译为英语     → 4. 校验英语翻译准确性
                  ↓
5. 翻译为德语     → 6. 校验德语翻译准确性
                  ↓
7. 三语言对比测试 → 8. 布局适配验证
```

**翻译工具建议**：
- DeepL（德语翻译质量较高）
- Google Translate
- 人工校对（关键术语和用户界面文本）

### 11.4 三语言切换用户体验

**无刷新切换优势**：
- ✅ 保持表格筛选条件
- ✅ 保持分页状态
- ✅ 保持表单输入
- ✅ 保持滚动位置
- ✅ 无白屏闪烁，体验流畅

**切换流程**：
```
用户选择语言 → i18n.switchLanguage(lang)
              ↓
更新localStorage → 加载新语言包
              ↓
应用翻译到DOM → 更新动态元素
              ↓
触发语言切换事件 → 组件响应更新
              ↓
完成（无刷新）
```

### 11.5 与Monitor模块协同

**共享机制**：
- 同一个i18n实例
- 同一个语言选择器
- 同一个localStorage存储键（`monitor-lang`）

**切换同步**：
- 用户在Monitor页面切换语言 → MDS页面同时生效
- 用户在MDS页面切换语言 → Monitor页面同时生效
- 无需重复切换，全局生效

**命名空间隔离**：
```javascript
// Monitor模块使用 monitor. 前缀
'monitor.page.title': 'MyAPI System Monitor'

// MDS模块使用 mds. 前缀
'mds.app.title': 'Data Staging Management System'

// 避免键冲突，清晰区分
```

---

## 十二、实施检查清单（三语言）

### 12.1 Phase 1 检查清单

- [ ] zh-CN.js添加MDS命名空间（约750条）
- [ ] en-US.js添加MDS命名空间（约750条）
- [ ] de-DE.js添加MDS命名空间（约750条）
- [ ] 三语言翻译项数量一致
- [ ] 状态枚举getter动态翻译测试通过
- [ ] 三语言切换无报错
- [ ] 德语文本无乱码

### 12.2 Phase 2 检查清单

- [ ] HTML三语言文本正确显示
- [ ] 弹窗三语言翻译测试通过
- [ ] 德语文本无溢出
- [ ] 导航菜单三语言正确

### 12.3 Phase 3 检查清单

- [ ] 错误码+参数机制测试通过
- [ ] 三语言错误提示正确
- [ ] 表格三语言显示正确
- [ ] 分页控件三语言正确

### 12.4 Phase 4 检查清单

- [ ] 所有页面三语言完整测试
- [ ] 无刷新切换测试通过
- [ ] 德语布局专项测试通过
- [ ] 与Monitor模块协同测试通过
- [ ] 性能验收通过
- [ ] 浏览器兼容性测试通过

---

**补充说明结束**
