# MDS模块国际化编码任务规划

**文档类型**: 实施任务清单  
**创建日期**: 2026-05-24  
**版本**: v1.0  
**状态**: 待执行  

---

## 一、任务总览

### 1.1 项目信息

- **项目名称**: MDS模块国际化改造
- **目标**: 支持简体中文、英语、德语三语言切换
- **总工作量**: 19人天(约4周)
- **实施方式**: 分4个阶段递进实施

### 1.2 任务统计

| 阶段 | 任务数 | 工作量 | 优先级 |
|------|--------|--------|--------|
| Phase 1: 基础准备 | 14个任务 | 4天 | P0+P1 |
| Phase 2: 导航与弹窗 | 16个任务 | 5天 | P2+P3 |
| Phase 3: 错误与表格 | 18个任务 | 6天 | P4+P5 |
| Phase 4: 完成与测试 | 14个任务 | 4天 | P6 |
| **合计** | **62个任务** | **19天** | |

### 1.3 核心目标

- [x] 复用Monitor模块的i18n框架
- [x] 扩展现有语言包(增加MDS命名空间)
- [x] 实现无刷新语言切换
- [x] 状态枚举动态翻译
- [x] 后端错误码+参数化处理
- [x] 三语言翻译质量保证

---

## 二、Phase 1任务清单(基础准备,4天)

### 2.1 语言包创建(Day 1)

#### 任务1.1: 扩展zh-CN.js语言包

**任务描述**: 在现有中文语言包中添加MDS模块命名空间

**涉及文件**:
- `static/lib/i18n/zh-CN.js`

**具体工作**:
- 提取P0级文本(状态标签,28处): mds.status.*
- 提取P1级文本(操作按钮,45处): mds.action.*
- 编写翻译键,遵循命名规范
- 添加注释分隔模块

**预期产出**:
```javascript
// zh-CN.js 新增内容
{
    // ========== MDS模块 ==========
    'mds.status.pending': '待处理',
    'mds.status.compliancePass': '初检通过',
    'mds.status.complianceError': '初检错误',
    'mds.status.relationPass': '联检通过',
    'mds.status.relationError': '联检错误',
    'mds.status.syncError': '推送失败',
    'mds.status.synced': '已推送',
    
    'mds.action.import': '导入',
    'mds.action.validate': '校验',
    'mds.action.sync': '推送',
    'mds.action.query': '查询',
    'mds.action.reset': '重置',
    // ... 共约73条
}
```

**验收标准**:
- [ ] 翻译键数量符合预期(约73条)
- [ ] 键命名规范统一(mds.status.*, mds.action.*)
- [ ] 注释清晰分隔模块
- [ ] 无重复键定义

**工作量**: 1天

---

#### 任务1.2: 扩展en-US.js语言包

**任务描述**: 在现有英文语言包中添加MDS模块翻译

**涉及文件**:
- `static/lib/i18n/en-US.js`

**具体工作**:
- 将zh-CN.js中的MDS翻译键翻译为英文
- 对应翻译键与zh-CN.js保持一致
- 使用专业术语(如Compliance Pass, Sync)

**预期产出**:
```javascript
// en-US.js 新增内容
{
    // ========== MDS Module ==========
    'mds.status.pending': 'Pending',
    'mds.status.compliancePass': 'Compliance Pass',
    'mds.status.complianceError': 'Compliance Error',
    'mds.status.relationPass': 'Relation Pass',
    'mds.status.relationError': 'Relation Error',
    'mds.status.syncError': 'Sync Failed',
    'mds.status.synced': 'Synced',
    
    'mds.action.import': 'Import',
    'mds.action.validate': 'Validate',
    'mds.action.sync': 'Sync',
    // ... 共约73条
}
```

**验收标准**:
- [ ] 翻译键数量与zh-CN.js一致
- [ ] 英文翻译准确、专业
- [ ] 键顺序与zh-CN.js对应

**工作量**: 0.5天

---

#### 任务1.3: 扩展de-DE.js语言包

**任务描述**: 在现有德语语言包中添加MDS模块翻译

**涉及文件**:
- `static/lib/i18n/de-DE.js`

**具体工作**:
- 将zh-CN.js中的MDS翻译键翻译为德语
- 注意德语特殊字符(ä, ö, ü, ß)
- 关注德语文本长度(可能比英文长20%-40%)

**预期产出**:
```javascript
// de-DE.js 新增内容
{
    // ========== MDS-Modul ==========
    'mds.status.pending': 'Ausstehend',
    'mds.status.compliancePass': 'Compliance bestanden',
    'mds.status.complianceError': 'Compliance fehlerhaft',
    'mds.status.relationPass': 'Relation bestanden',
    'mds.status.relationError': 'Relation fehlerhaft',
    'mds.status.syncError': 'Sync fehlgeschlagen',
    'mds.status.synced': 'Synchronisiert',
    
    'mds.action.import': 'Importieren',
    'mds.action.validate': 'Validieren',
    'mds.action.sync': 'Synchronisieren',
    // ... 共约73条
}
```

**验收标准**:
- [ ] 翻译键数量与zh-CN.js一致
- [ ] 德语翻译准确,使用专业术语
- [ ] 特殊字符正确编码(UTF-8)
- [ ] 文件保存为UTF-8无BOM格式

**工作量**: 0.5天

---

### 2.2 状态枚举改造(Day 2)

#### 任务1.4: 改造STAGING_STATUS枚举

**任务描述**: 将common.js中的STAGING_STATUS改造为动态翻译

**涉及文件**:
- `static/mds/js/common.js`

**具体工作**:
- 将label字段改为labelKey
- 添加getter动态获取翻译
- 确保i18n未初始化时的回退机制

**改造前**:
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

**改造后**:
```javascript
const STAGING_STATUS = {
    PENDING: {
        value: 'pending',
        labelKey: 'mds.status.pending',
        color: '#ff9300',
        icon: '⏳',
        get label() {
            return typeof i18n !== 'undefined' ? 
                i18n.t(this.labelKey) : '待处理';
        }
    }
};
```

**验收标准**:
- [ ] 所有状态枚举都使用getter
- [ ] i18n未初始化时显示中文回退
- [ ] 语言切换后状态标签自动更新
- [ ] 控制台无报错

**工作量**: 0.5天

---

#### 任务1.5: 改造status-card.js组件

**任务描述**: 改造状态统计卡片组件,支持动态翻译

**涉及文件**:
- `static/mds/js/status-card.js`

**具体工作**:
- 渲染状态卡片时使用STAGING_STATUS.label
- 监听languageChanged事件,刷新卡片
- 确保切换语言后数据正确显示

**关键代码**:
```javascript
// 渲染状态卡片
function renderStatusCards() {
    const statuses = Object.values(STAGING_STATUS);
    statuses.forEach(status => {
        // label自动动态翻译
        const label = status.label;
        // ...
    });
}

// 监听语言切换事件
window.addEventListener('languageChanged', () => {
    renderStatusCards();
});
```

**验收标准**:
- [ ] 状态卡片显示三语言文本
- [ ] 语言切换后卡片自动刷新
- [ ] 数据统计正确

**工作量**: 0.5天

---

#### 任务1.6: 改造其他枚举对象

**任务描述**: 改造其他包含中文label的枚举对象

**涉及文件**:
- `static/mds/js/common.js`

**具体工作**:
- 检查其他枚举对象(如BUTTON_TEXT, ERROR_MSG等)
- 统一改造为labelKey + getter模式
- 确保所有硬编码文本都被翻译键替换

**验收标准**:
- [ ] 所有枚举都支持动态翻译
- [ ] 无遗漏的硬编码中文文本
- [ ] 三语言切换测试通过

**工作量**: 0.5天

---

### 2.3 验证与测试(Day 3-4)

#### 任务1.7: 创建语言切换UI

**任务描述**: 在导航栏添加三语言选择器

**涉及文件**:
- `static/mds/index.html`

**具体工作**:
- 添加语言选择下拉框
- 复用Monitor的语言选择器样式
- 绑定切换事件处理函数

**预期产出**:
```html
<select id="lang-selector" onchange="switchLanguage(this.value)" 
        class="form-select form-select-sm" style="width: auto;">
    <option value="zh-CN">🇨🇳 中文</option>
    <option value="en-US">🇺🇸 English</option>
    <option value="de-DE">🇩🇪 Deutsch</option>
</select>
```

**验收标准**:
- [ ] 语言选择器正确显示
- [ ] 样式与Monitor一致
- [ ] 三语言图标正确

**工作量**: 0.5天

---

#### 任务1.8: 实现无刷新语言切换

**任务描述**: 实现语言切换功能,无刷新更新页面文本

**涉及文件**:
- `static/mds/js/mds-page-controller.js` (新增函数)

**具体工作**:
- 实现switchLanguage函数
- 调用i18n.switchLanguage切换语言
- 更新动态元素(表格、卡片、弹窗)
- 触发languageChanged事件

**关键代码**:
```javascript
async function switchLanguage(lang) {
    if (typeof i18n === 'undefined') {
        console.warn('i18n not initialized');
        return;
    }
    
    await i18n.switchLanguage(lang);
    updateDynamicElements();
    
    window.dispatchEvent(new CustomEvent('languageChanged', {
        detail: { lang: lang }
    }));
}

function updateDynamicElements() {
    // 更新状态卡片
    if (window.statusCardInstance) {
        window.statusCardInstance.refresh();
    }
    
    // 更新表格
    if (window.dataTableInstance) {
        window.dataTableInstance.refresh();
    }
    
    // 更新已打开的模态框
    const modals = document.querySelectorAll('.modal.show');
    modals.forEach(modal => {
        modal.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            el.textContent = i18n.t(key);
        });
    });
}
```

**验收标准**:
- [ ] 语言切换无页面刷新
- [ ] 保持表格筛选条件
- [ ] 保持分页状态
- [ ] 保持滚动位置
- [ ] 无白屏闪烁

**工作量**: 1天

---

#### 任务1.9: 测试状态枚举翻译

**任务描述**: 测试状态枚举在三种语言下的翻译

**涉及文件**:
- 所有使用STAGING_STATUS的文件

**具体工作**:
- 切换到中文,验证状态标签显示"待处理"等
- 切换到英文,验证显示"Pending"等
- 切换到德语,验证显示"Ausstehend"等
- 测试语言切换后的自动更新

**验收标准**:
- [ ] 中英德三语言翻译正确
- [ ] 语言切换后立即更新
- [ ] 控制台无报错

**工作量**: 0.5天

---

#### 任务1.10: 测试操作按钮翻译

**任务描述**: 测试操作按钮在三语言下的翻译

**具体工作**:
- 测试"导入"、"校验"、"推送"等按钮
- 验证三语言显示
- 测试德语长文本布局

**验收标准**:
- [ ] 所有按钮文本翻译正确
- [ ] 德语文本无溢出
- [ ] 按钮样式正常

**工作量**: 0.5天

---

#### 任务1.11: 测试无刷新切换

**任务描述**: 测试无刷新语言切换功能

**具体工作**:
- 在表格筛选状态下切换语言
- 在分页状态下切换语言
- 在表单输入状态下切换语言
- 验证状态保持

**验收标准**:
- [ ] 筛选条件不丢失
- [ ] 分页状态保持
- [ ] 表单输入不丢失
- [ ] 滚动位置保持

**工作量**: 0.5天

---

#### 任务1.12: 测试德语布局适配

**任务描述**: 测试德语长文本的布局适配

**具体工作**:
- 检查所有按钮是否溢出
- 检查表格列宽是否足够
- 检查弹窗是否显示完整
- 必要时调整CSS样式

**验收标准**:
- [ ] 无文本溢出
- [ ] 无布局错乱
- [ ] 德语特殊字符正确显示

**工作量**: 0.5天

---

#### 任务1.13: 编写Phase 1测试报告

**任务描述**: 记录Phase 1的测试结果

**涉及文件**:
- `docs/spec/MDS-i18n-Phase1-Test-Report.md` (新建)

**具体工作**:
- 记录测试用例
- 记录测试结果
- 记录发现的问题
- 记录解决方案

**验收标准**:
- [ ] 测试报告完整
- [ ] 所有问题已解决

**工作量**: 0.5天

---

#### 任务1.14: Phase 1总结与评审

**任务描述**: 总结Phase 1工作,进行代码评审

**具体工作**:
- 检查代码质量
- 检查翻译键命名规范
- 检查三语言包一致性
- 进行代码评审

**验收标准**:
- [ ] 代码质量合格
- [ ] 翻译键规范统一
- [ ] 三语言包键数量一致
- [ ] 评审通过

**工作量**: 0.5天

---

## 三、Phase 2任务清单(导航与弹窗,5天)

### 3.1 HTML页面改造(Day 5-6)

#### 任务2.1: 改造index.html

**任务描述**: 为index.html添加data-i18n属性

**涉及文件**:
- `static/mds/index.html`

**具体工作**:
- 提取所有硬编码中文文本
- 为文本元素添加data-i18n属性
- 提取P2级文本(导航菜单,14处)

**改造示例**:
```html
<!-- 改造前 -->
<h5>数据清洗管理系统</h5>

<!-- 改造后 -->
<h5 data-i18n="mds.app.title">数据清洗管理系统</h5>
```

**预期产出**:
- 导航菜单翻译: mds.nav.material, mds.nav.bom等
- 全局操作按钮翻译
- 卡片标题翻译

**验收标准**:
- [ ] 所有中文文本都添加data-i18n
- [ ] 翻译键命名规范
- [ ] 页面结构不变

**工作量**: 1天

---

#### 任务2.2: 改造template.html

**任务描述**: 为数据操作页面模板添加data-i18n属性

**涉及文件**:
- `static/mds/pages/template.html`

**具体工作**:
- 提取所有硬编码中文文本
- 添加data-i18n属性
- 包括表格、筛选框、分页控件等

**改造示例**:
```html
<!-- 改造前 -->
<button class="btn btn-primary">校验</button>

<!-- 改造后 -->
<button class="btn btn-primary">
    <span data-i18n="mds.action.validate">校验</span>
</button>
```

**验收标准**:
- [ ] 所有文本元素都有data-i18n
- [ ] 动态生成的内容预留翻译钩子
- [ ] 页面功能不变

**工作量**: 1天

---

#### 任务2.3: 改造user-guide.html

**任务描述**: 为操作指引页面添加data-i18n属性

**涉及文件**:
- `static/mds/user-guide.html`

**具体工作**:
- 提取操作指引文本
- 添加data-i18n属性
- 翻译指引说明

**验收标准**:
- [ ] 所有文本都有翻译
- [ ] 三语言显示正确
- [ ] 布局不变

**工作量**: 0.5天

---

#### 任务2.4: 提取P2级翻译键

**任务描述**: 提取导航菜单等P2级文本的翻译键

**涉及文件**:
- `static/lib/i18n/zh-CN.js`
- `static/lib/i18n/en-US.js`
- `static/lib/i18n/de-DE.js`

**具体工作**:
- 提取导航菜单文本(14处)
- 添加到三语言包
- 编写翻译

**预期产出**:
```javascript
// zh-CN.js
'mds.nav.material': '物料',
'mds.nav.matVer': '产线版本',
'mds.nav.workcenter': '工作中心',
'mds.nav.matWc': '工艺路线',
'mds.nav.bom': 'BOM',
'mds.nav.mold': '模具',
'mds.nav.matWcMold': '机台模具',
```

**验收标准**:
- [ ] 翻译键数量正确(约14处)
- [ ] 三语言翻译准确

**工作量**: 0.5天

---

#### 任务2.5: 测试HTML页面翻译

**任务描述**: 测试三个HTML页面的翻译效果

**具体工作**:
- 测试index.html三语言显示
- 测试template.html三语言显示
- 测试user-guide.html三语言显示
- 测试语言切换功能

**验收标准**:
- [ ] 所有页面文本正确翻译
- [ ] 语言切换后立即更新
- [ ] 无布局错乱

**工作量**: 0.5天

---

### 3.2 弹窗组件改造(Day 7-9)

#### 任务2.6: 改造modal-manager.js基础函数

**任务描述**: 改造模态框管理器的基础函数

**涉及文件**:
- `static/mds/js/modal-manager.js`

**具体工作**:
- 改造showConfirm函数,支持翻译键
- 改造showAlert函数
- 改造showPrompt函数
- 确保弹窗标题、内容支持翻译

**改造示例**:
```javascript
// 改造前
function showConfirm(title, message, onConfirm) {
    // ...
}

// 改造后
function showConfirm(titleKey, messageKey, onConfirm, params = {}) {
    const title = typeof i18n !== 'undefined' ? 
        i18n.t(titleKey) : titleKey;
    const message = typeof i18n !== 'undefined' ? 
        i18n.t(messageKey, params) : messageKey;
    // ...
}
```

**验收标准**:
- [ ] 所有弹窗函数支持翻译键
- [ ] 支持参数化翻译
- [ ] 控制台无报错

**工作量**: 1天

---

#### 任务2.7: 改造导入弹窗

**任务描述**: 改造Excel导入弹窗的翻译

**涉及文件**:
- `static/mds/js/modal-manager.js`
- `static/lib/i18n/zh-CN.js`等

**具体工作**:
- 改造弹窗标题翻译
- 改造拖拽提示翻译
- 改造按钮翻译
- 提取P3级弹窗文本

**预期产出**:
```javascript
// 翻译键
'mds.modal.importTitle': '导入Excel数据',
'mds.upload.dragDrop': '点击或拖拽文件上传（支持 .xlsx, .xls, .csv）',
'mds.modal.confirm': '确认',
'mds.modal.cancel': '取消',
```

**验收标准**:
- [ ] 弹窗标题翻译正确
- [ ] 拖拽提示翻译正确
- [ ] 按钮翻译正确

**工作量**: 1天

---

#### 任务2.8: 改造筛选弹窗

**任务描述**: 改造精准筛选弹窗的翻译

**涉及文件**:
- `static/mds/js/modal-manager.js`

**具体工作**:
- 改造筛选弹窗标题
- 改造筛选条件文本
- 改造按钮文本

**验收标准**:
- [ ] 弹窗内容翻译正确
- [ ] 三语言显示正确

**工作量**: 0.5天

---

#### 任务2.9: 改造编辑弹窗

**任务描述**: 改造记录编辑弹窗的翻译

**涉及文件**:
- `static/mds/js/form-renderer.js`

**具体工作**:
- 改造form-renderer.js
- 改造表单标签翻译
- 改造表单验证消息翻译
- 改造按钮文本

**验收标准**:
- [ ] 表单标签翻译正确
- [ ] 验证消息翻译正确
- [ ] 三语言显示正确

**工作量**: 1天

---

#### 任务2.10: 提取P3级翻译键

**任务描述**: 提取弹窗相关文本的翻译键(约120处)

**涉及文件**:
- `static/lib/i18n/zh-CN.js`
- `static/lib/i18n/en-US.js`
- `static/lib/i18n/de-DE.js`

**具体工作**:
- 提取所有弹窗文本
- 编写三语言翻译
- 添加到语言包

**验收标准**:
- [ ] 翻译键数量正确(约120处)
- [ ] 三语言翻译准确
- [ ] 键命名规范统一

**工作量**: 1天

---

#### 任务2.11: 实现弹窗语言切换监听

**任务描述**: 实现弹窗在语言切换时的动态更新

**涉及文件**:
- `static/mds/js/modal-manager.js`

**具体工作**:
- 监听languageChanged事件
- 更新已打开弹窗的文本
- 确保切换语言后弹窗内容更新

**关键代码**:
```javascript
window.addEventListener('languageChanged', () => {
    const modals = document.querySelectorAll('.modal.show');
    modals.forEach(modal => {
        modal.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            el.textContent = i18n.t(key);
        });
    });
});
```

**验收标准**:
- [ ] 语言切换后弹窗内容更新
- [ ] 不关闭弹窗
- [ ] 数据不丢失

**工作量**: 0.5天

---

#### 任务2.12: 测试弹窗翻译

**任务描述**: 测试所有弹窗的翻译效果

**具体工作**:
- 测试导入弹窗三语言显示
- 测试筛选弹窗三语言显示
- 测试编辑弹窗三语言显示
- 测试确认弹窗三语言显示

**验收标准**:
- [ ] 所有弹窗翻译正确
- [ ] 语言切换后弹窗更新
- [ ] 功能正常

**工作量**: 0.5天

---

#### 任务2.13: 测试德语弹窗布局

**任务描述**: 测试德语环境下弹窗的布局

**具体工作**:
- 检查弹窗宽度是否足够
- 检查按钮文本是否溢出
- 必要时调整弹窗样式

**验收标准**:
- [ ] 无文本溢出
- [ ] 无布局错乱
- [ ] 弹窗美观

**工作量**: 0.5天

---

#### 任务2.14: 编写Phase 2测试报告

**任务描述**: 记录Phase 2的测试结果

**涉及文件**:
- `docs/spec/MDS-i18n-Phase2-Test-Report.md` (新建)

**验收标准**:
- [ ] 测试报告完整
- [ ] 所有问题已解决

**工作量**: 0.5天

---

#### 任务2.15: Phase 2总结与评审

**任务描述**: 总结Phase 2工作,进行代码评审

**验收标准**:
- [ ] 代码质量合格
- [ ] 翻译键规范统一
- [ ] 评审通过

**工作量**: 0.5天

---

#### 任务2.16: 提交Phase 2代码

**任务描述**: 提交Phase 2的代码变更

**具体工作**:
- 检查代码变更
- 编写提交信息
- 提交代码

**验收标准**:
- [ ] 代码提交成功
- [ ] 提交信息清晰

**工作量**: 0.5天

---

## 四、Phase 3任务清单(错误与表格,6天)

### 4.1 错误消息处理(Day 10-11)

#### 任务3.1: 设计错误码映射表

**任务描述**: 设计后端错误码到翻译键的映射表

**涉及文件**:
- `static/mds/js/common.js` (新增ERROR_CODE_MAP)

**具体工作**:
- 定义错误码常量
- 创建错误码到翻译键的映射
- 定义参数化错误模板

**预期产出**:
```javascript
// 错误码常量
const ERROR_CODES = {
    DUPLICATE_KEY: 'DUPLICATE_KEY',
    INVALID_FORMAT: 'INVALID_FORMAT',
    FOREIGN_KEY_VIOLATION: 'FOREIGN_KEY_VIOLATION',
    VALIDATION_FAILED: 'VALIDATION_FAILED'
};

// 错误码到翻译键的映射
const ERROR_CODE_MAP = {
    DUPLICATE_KEY: 'mds.error.DUPLICATE_KEY',
    INVALID_FORMAT: 'mds.error.INVALID_FORMAT',
    FOREIGN_KEY_VIOLATION: 'mds.error.FOREIGN_KEY_VIOLATION',
    VALIDATION_FAILED: 'mds.error.VALIDATION_FAILED'
};
```

**验收标准**:
- [ ] 错误码定义完整
- [ ] 映射关系正确
- [ ] 命名规范统一

**工作量**: 0.5天

---

#### 任务3.2: 实现错误翻译函数

**任务描述**: 实现后端错误消息的统一翻译函数

**涉及文件**:
- `static/mds/js/common.js` (新增translateError函数)

**具体工作**:
- 实现translateError函数
- 处理错误码和参数
- 支持参数化翻译
- 提供回退机制

**关键代码**:
```javascript
function translateError(response) {
    // 检查是否有错误对象
    if (!response.error) {
        return response.message || 'Unknown error';
    }
    
    const { code, params = {} } = response.error;
    const errorKey = ERROR_CODE_MAP[code] || `mds.error.${code}`;
    
    // 使用i18n翻译
    if (typeof i18n !== 'undefined') {
        const translated = i18n.t(errorKey, params);
        // 如果翻译键不存在,返回错误码
        if (translated !== errorKey) {
            return translated;
        }
    }
    
    // 回退:返回错误码
    return `Error: ${code}`;
}
```

**验收标准**:
- [ ] 函数正确处理错误码
- [ ] 支持参数化翻译
- [ ] 回退机制有效

**工作量**: 1天

---

#### 任务3.3: 改造API错误处理

**任务描述**: 改造所有API调用的错误处理

**涉及文件**:
- `static/mds/js/mds-page-controller.js`
- `static/mds/js/data-table.js`
- `static/mds/js/global-ops-controller.js`

**具体工作**:
- 查找所有API调用
- 改造错误处理逻辑
- 使用translateError函数

**改造示例**:
```javascript
// 改造前
async function handleResponse(response) {
    if (!response.success) {
        showError(response.message);
    }
}

// 改造后
async function handleResponse(response) {
    if (!response.success) {
        const errorMsg = translateError(response);
        showError(errorMsg);
    }
}
```

**验收标准**:
- [ ] 所有API错误都使用translateError
- [ ] 错误消息支持三语言
- [ ] 功能正常

**工作量**: 1天

---

#### 任务3.4: 提取P4级翻译键

**任务描述**: 提取错误消息相关的翻译键(约85处)

**涉及文件**:
- `static/lib/i18n/zh-CN.js`
- `static/lib/i18n/en-US.js`
- `static/lib/i18n/de-DE.js`

**具体工作**:
- 提取所有错误消息文本
- 编写三语言翻译
- 支持参数化翻译

**预期产出**:
```javascript
// zh-CN.js
'mds.error.DUPLICATE_KEY': '数据重复: {field}={value} 已存在',
'mds.error.INVALID_FORMAT': '格式错误: {field} 格式不正确',
'mds.error.FOREIGN_KEY_VIOLATION': '外键约束违反: {field} 引用不存在',
'mds.error.VALIDATION_FAILED': '校验失败: {reason}',
'mds.error.queryFailed': '查询失败',
'mds.error.uploadFailed': '上传失败',
'mds.error.timeout': '请求超时',
// ... 共约85条
```

**验收标准**:
- [ ] 翻译键数量正确(约85处)
- [ ] 三语言翻译准确
- [ ] 参数化翻译正确

**工作量**: 1天

---

#### 任务3.5: 测试错误消息翻译

**任务描述**: 测试各种错误消息的翻译效果

**具体工作**:
- 模拟各种错误响应
- 测试三语言错误提示
- 测试参数化翻译

**验收标准**:
- [ ] 所有错误消息翻译正确
- [ ] 参数化翻译正确
- [ ] 回退机制有效

**工作量**: 0.5天

---

### 4.2 表格组件改造(Day 12-15)

#### 任务3.6: 改造data-table.js基础函数

**任务描述**: 改造数据表格组件的基础函数

**涉及文件**:
- `static/mds/js/data-table.js`

**具体工作**:
- 改造表格列标题翻译
- 改造空状态提示
- 改造加载状态提示
- 添加语言切换事件监听

**验收标准**:
- [ ] 表格列标题支持翻译
- [ ] 空状态提示支持翻译
- [ ] 加载状态提示支持翻译

**工作量**: 1天

---

#### 任务3.7: 改造分页控件

**任务描述**: 改造表格分页控件的翻译

**涉及文件**:
- `static/mds/js/data-table.js`

**具体工作**:
- 改造"条/页"文本
- 改造"共X条"文本
- 改造"上一页"、"下一页"文本
- 改造页码显示

**预期产出**:
```javascript
// 翻译键
'mds.table.perPage': '条/页',
'mds.table.total': '共 {count} 条',
'mds.table.prevPage': '上一页',
'mds.table.nextPage': '下一页',
```

**验收标准**:
- [ ] 分页控件文本翻译正确
- [ ] 三语言显示正确
- [ ] 功能正常

**工作量**: 1天

---

#### 任务3.8: 改造表格操作按钮

**任务描述**: 改造表格中的操作按钮(编辑、删除等)

**涉及文件**:
- `static/mds/js/data-table.js`

**具体工作**:
- 改造"编辑"按钮
- 改造"删除"按钮
- 改造"导出"按钮
- 使用data-i18n属性

**验收标准**:
- [ ] 操作按钮文本翻译正确
- [ ] 三语言显示正确

**工作量**: 0.5天

---

#### 任务3.9: 改造空状态提示

**任务描述**: 改造表格无数据时的提示文本

**涉及文件**:
- `static/mds/js/data-table.js`

**具体工作**:
- 改造"暂无数据"文本
- 改造"加载中..."文本
- 支持动态翻译

**预期产出**:
```javascript
// 翻译键
'mds.table.noData': '暂无数据',
'mds.table.loading': '加载中...',
```

**验收标准**:
- [ ] 空状态提示翻译正确
- [ ] 三语言显示正确

**工作量**: 0.5天

---

#### 任务3.10: 改造全选控件

**任务描述**: 改造表格全选复选框的文本

**涉及文件**:
- `static/mds/js/data-table.js`

**具体工作**:
- 改造"全选"文本
- 支持动态翻译

**验收标准**:
- [ ] 全选文本翻译正确
- [ ] 三语言显示正确

**工作量**: 0.5天

---

#### 任务3.11: 提取P5级翻译键

**任务描述**: 提取表格相关文本的翻译键(约150处)

**涉及文件**:
- `static/lib/i18n/zh-CN.js`
- `static/lib/i18n/en-US.js`
- `static/lib/i18n/de-DE.js`

**具体工作**:
- 提取所有表格文本
- 编写三语言翻译
- 支持参数化翻译

**验收标准**:
- [ ] 翻译键数量正确(约150处)
- [ ] 三语言翻译准确

**工作量**: 1天

---

#### 任务3.12: 实现表格语言切换监听

**任务描述**: 实现表格在语言切换时的刷新

**涉及文件**:
- `static/mds/js/data-table.js`

**具体工作**:
- 监听languageChanged事件
- 实现refresh方法
- 重新渲染表格

**关键代码**:
```javascript
class DataTable {
    refresh() {
        // 重新渲染列标题
        this.renderHeaders();
        // 重新渲染分页控件
        this.renderPagination();
        // 重新渲染空状态
        if (this.data.length === 0) {
            this.renderEmptyState();
        }
    }
}

// 监听语言切换
window.addEventListener('languageChanged', () => {
    if (window.dataTableInstance) {
        window.dataTableInstance.refresh();
    }
});
```

**验收标准**:
- [ ] 语言切换后表格刷新
- [ ] 数据不丢失
- [ ] 分页状态保持

**工作量**: 0.5天

---

#### 任务3.13: 测试表格翻译

**任务描述**: 测试表格组件的翻译效果

**具体工作**:
- 测试表格列标题翻译
- 测试分页控件翻译
- 测试空状态提示翻译
- 测试操作按钮翻译

**验收标准**:
- [ ] 所有表格文本翻译正确
- [ ] 语言切换后表格更新
- [ ] 功能正常

**工作量**: 0.5天

---

#### 任务3.14: 测试德语表格布局

**任务描述**: 测试德语环境下表格的布局

**具体工作**:
- 检查列宽是否足够
- 检查按钮是否溢出
- 必要时调整CSS样式

**验收标准**:
- [ ] 无文本溢出
- [ ] 无布局错乱
- [ ] 表格美观

**工作量**: 0.5天

---

#### 任务3.15: 编写Phase 3测试报告

**任务描述**: 记录Phase 3的测试结果

**涉及文件**:
- `docs/spec/MDS-i18n-Phase3-Test-Report.md` (新建)

**验收标准**:
- [ ] 测试报告完整
- [ ] 所有问题已解决

**工作量**: 0.5天

---

#### 任务3.16: Phase 3总结与评审

**任务描述**: 总结Phase 3工作,进行代码评审

**验收标准**:
- [ ] 代码质量合格
- [ ] 翻译键规范统一
- [ ] 评审通过

**工作量**: 0.5天

---

#### 任务3.17: 提交Phase 3代码

**任务描述**: 提交Phase 3的代码变更

**验收标准**:
- [ ] 代码提交成功
- [ ] 提交信息清晰

**工作量**: 0.5天

---

#### 任务3.18: 改造表格筛选控件

**任务描述**: 改造表格筛选区域的文本翻译

**涉及文件**:
- `static/mds/js/data-table.js`
- `static/mds/pages/template.html`

**具体工作**:
- 改造筛选按钮文本
- 改造筛选条件显示
- 改造重置按钮文本

**验收标准**:
- [ ] 筛选控件文本翻译正确
- [ ] 三语言显示正确

**工作量**: 0.5天

---

## 五、Phase 4任务清单(完成与测试,4天)

### 5.1 完成剩余翻译(Day 16-17)

#### 任务4.1: 改造mds-page-controller.js

**任务描述**: 完成页面控制器的剩余翻译

**涉及文件**:
- `static/mds/js/mds-page-controller.js`

**具体工作**:
- 查找所有硬编码中文文本
- 替换为i18n.t()调用
- 确保所有文本都支持翻译

**验收标准**:
- [ ] 无硬编码中文文本
- [ ] 所有文本支持翻译
- [ ] 功能正常

**工作量**: 1天

---

#### 任务4.2: 改造global-ops-controller.js

**任务描述**: 完成全局操作控制器的翻译

**涉及文件**:
- `static/mds/js/global-ops-controller.js`

**具体工作**:
- 改造全局操作按钮
- 改造操作提示消息
- 改造确认对话框

**验收标准**:
- [ ] 所有文本支持翻译
- [ ] 功能正常

**工作量**: 0.5天

---

#### 任务4.3: 提取P6级翻译键

**任务描述**: 提取剩余文本的翻译键(约304处)

**涉及文件**:
- `static/lib/i18n/zh-CN.js`
- `static/lib/i18n/en-US.js`
- `static/lib/i18n/de-DE.js`

**具体工作**:
- 提取所有剩余文本
- 编写三语言翻译
- 检查翻译键完整性

**验收标准**:
- [ ] 翻译键数量正确(约304处)
- [ ] 三语言翻译准确
- [ ] 无遗漏文本

**工作量**: 1天

---

#### 任务4.4: 检查翻译键完整性

**任务描述**: 检查所有文件中使用的翻译键是否都存在

**具体工作**:
- 扫描所有JS文件中的i18n.t()调用
- 提取所有翻译键
- 对比语言包中的键
- 补充缺失的翻译键

**验收标准**:
- [ ] 无缺失的翻译键
- [ ] 三语言包键数量一致
- [ ] 无未使用的翻译键

**工作量**: 0.5天

---

#### 任务4.5: 清理调试代码

**任务描述**: 清理临时添加的调试代码和注释

**涉及文件**:
- 所有修改过的文件

**具体工作**:
- 删除console.log调试语句
- 删除临时注释
- 整理代码格式

**验收标准**:
- [ ] 无调试代码
- [ ] 代码整洁
- [ ] 注释清晰

**工作量**: 0.5天

---

### 5.2 全面测试(Day 18-19)

#### 任务4.6: 功能测试-所有页面

**任务描述**: 测试所有页面的翻译功能

**具体工作**:
- 测试index.html所有文本翻译
- 测试template.html所有文本翻译
- 测试user-guide.html所有文本翻译
- 测试所有弹窗文本翻译

**验收标准**:
- [ ] 所有页面文本正确翻译
- [ ] 三语言显示正确
- [ ] 功能正常

**工作量**: 1天

---

#### 任务4.7: 功能测试-三语言切换

**任务描述**: 测试三语言之间的切换功能

**具体工作**:
- 测试中文切换到英文
- 测试英文切换到德语
- 测试德语切换到中文
- 测试语言选择的持久化

**验收标准**:
- [ ] 切换流畅,无白屏
- [ ] 状态保持
- [ ] 语言持久化到localStorage

**工作量**: 0.5天

---

#### 任务4.8: 功能测试-无刷新切换

**任务描述**: 测试无刷新语言切换的所有场景

**具体工作**:
- 测试表格筛选状态下切换
- 测试分页状态下切换
- 测试表单输入状态下切换
- 测试弹窗打开状态下切换
- 测试滚动位置保持

**验收标准**:
- [ ] 筛选条件不丢失
- [ ] 分页状态保持
- [ ] 表单输入保持
- [ ] 弹窗不关闭
- [ ] 滚动位置保持

**工作量**: 0.5天

---

#### 任务4.9: 性能测试

**任务描述**: 测试国际化功能对性能的影响

**具体工作**:
- 测试语言包加载时间
- 测试语言切换响应时间
- 测试内存占用
- 对比改造前后的性能

**验收标准**:
- [ ] 语言包加载时间 < 300ms
- [ ] 语言切换响应时间 < 100ms
- [ ] 内存占用增加 < 8MB

**工作量**: 0.5天

---

#### 任务4.10: 浏览器兼容性测试

**任务描述**: 测试不同浏览器的兼容性

**具体工作**:
- Chrome浏览器测试
- Firefox浏览器测试
- Edge浏览器测试
- Safari浏览器测试(如有条件)

**验收标准**:
- [ ] 所有浏览器正常运行
- [ ] 德语特殊字符正确显示
- [ ] 无布局错乱

**工作量**: 0.5天

---

#### 任务4.11: 德语专项测试

**任务描述**: 德语环境的专项测试

**具体工作**:
- 测试德语所有文本显示
- 测试德语特殊字符
- 测试德语长文本布局
- 测试德语文本换行

**验收标准**:
- [ ] 德语所有文本正确显示
- [ ] 特殊字符无乱码
- [ ] 长文本布局合理

**工作量**: 0.5天

---

#### 任务4.12: 回归测试

**任务描述**: 确保国际化改造不影响现有功能

**具体工作**:
- 测试数据导入功能
- 测试数据校验功能
- 测试数据推送功能
- 测试数据查询功能
- 测试所有业务流程

**验收标准**:
- [ ] 所有业务功能正常
- [ ] 无功能退化
- [ ] 无新增bug

**工作量**: 1天

---

#### 任务4.13: 编写最终测试报告

**任务描述**: 编写完整的测试报告

**涉及文件**:
- `docs/spec/MDS-i18n-Final-Test-Report.md` (新建)

**具体工作**:
- 记录所有测试用例
- 记录所有测试结果
- 记录性能数据
- 记录浏览器兼容性结果

**验收标准**:
- [ ] 测试报告完整
- [ ] 数据准确
- [ ] 问题已解决

**工作量**: 0.5天

---

#### 任务4.14: 编写实施文档

**任务描述**: 编写完整的实施文档

**涉及文件**:
- `docs/spec/MDS-i18n-Implementation-Summary.md` (新建)

**具体工作**:
- 记录实施过程
- 记录技术方案
- 记录关键决策
- 记录维护指南

**验收标准**:
- [ ] 文档完整
- [ ] 内容清晰
- [ ] 可维护性强

**工作量**: 0.5天

---

## 六、任务依赖关系图

### 6.1 Phase内部依赖

```
Phase 1:
任务1.1 → 任务1.2 → 任务1.3 (语言包创建,串行)
任务1.4 → 任务1.5 → 任务1.6 (状态枚举改造,串行)
任务1.7 → 任务1.8 (UI实现,串行)
任务1.9, 1.10, 1.11, 1.12 (测试,并行,依赖1.1-1.8)
任务1.13 → 任务1.14 (文档与评审,串行)

Phase 2:
任务2.1, 2.2, 2.3 (HTML改造,并行)
任务2.4 (翻译键提取,依赖2.1-2.3)
任务2.6 → 任务2.7 → 任务2.8 → 任务2.9 (弹窗改造,串行)
任务2.10 (翻译键提取,依赖2.6-2.9)
任务2.11 (语言切换监听,依赖2.6)
任务2.12, 2.13 (测试,并行,依赖2.1-2.11)
任务2.14 → 任务2.15 → 任务2.16 (文档与提交,串行)

Phase 3:
任务3.1 → 任务3.2 → 任务3.3 (错误处理,串行)
任务3.4 (翻译键提取,依赖3.1-3.3)
任务3.5 (测试,依赖3.1-3.4)
任务3.6 → 任务3.7 → 任务3.8 → 任务3.9 → 任务3.10 (表格改造,串行)
任务3.11 (翻译键提取,依赖3.6-3.10)
任务3.12 (语言切换监听,依赖3.6)
任务3.13, 3.14, 3.18 (测试,并行,依赖3.6-3.12)
任务3.15 → 任务3.16 → 任务3.17 (文档与提交,串行)

Phase 4:
任务4.1, 4.2 (代码改造,并行)
任务4.3 (翻译键提取,依赖4.1-4.2)
任务4.4 → 任务4.5 (检查与清理,串行)
任务4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12 (全面测试,并行)
任务4.13 → 任务4.14 (文档编写,串行)
```

### 6.2 Phase间依赖

```
Phase 1完成 → Phase 2开始
Phase 2完成 → Phase 3开始
Phase 3完成 → Phase 4开始
```

### 6.3 关键路径

```
任务1.1 → 任务1.4 → 任务1.8 → 任务2.6 → 任务3.1 → 任务3.6 → 任务4.1 → 任务4.6 → 任务4.12
```

关键路径上的任务不可延误,否则会影响整体进度。

---

## 七、风险应对预案

### 7.1 技术风险

#### 风险1: i18n框架兼容性问题

**风险描述**: Monitor模块的i18n框架可能不兼容MDS模块

**应对措施**:
- Phase 1先测试框架复用可行性
- 如不兼容,独立实现轻量级i18n
- 预留1天应急时间

**触发条件**: Phase 1任务1.8测试失败

**应急方案**: 创建独立的MDS-i18n实例

---

#### 风险2: 状态枚举改造复杂度超预期

**风险描述**: 状态枚举在多处使用,改造难度超预期

**应对措施**:
- 先梳理所有使用场景
- 采用渐进式改造
- 预留0.5天应急时间

**触发条件**: 任务1.4-1.6耗时超过1.5天

**应急方案**: 分批改造,优先P0级

---

#### 风险3: 后端错误码改造复杂

**风险描述**: 后端返回错误码格式不统一

**应对措施**:
- 先调研现有错误格式
- 设计兼容多种格式的translateError
- 与后端协调统一错误格式

**触发条件**: 任务3.2发现错误格式不统一

**应急方案**: 前端增加错误格式适配逻辑

---

### 7.2 进度风险

#### 风险4: 翻译工作量超预期

**风险描述**: 翻译文本数量超出预估(746处)

**应对措施**:
- 使用脚本批量提取中文文本
- 使用翻译工具辅助翻译
- 分优先级,P0-P3优先

**触发条件**: Phase 2结束时翻译完成度<80%

**应急方案**: 延长Phase 3时间,压缩Phase 4测试时间

---

#### 风险5: 测试发现大量问题

**风险描述**: Phase 4测试发现大量翻译错误或功能bug

**应对措施**:
- 每个Phase完成后立即测试
- 及时修复发现的问题
- 避免问题积累到Phase 4

**触发条件**: Phase 4测试发现严重问题>5个

**应急方案**: 回退到上一个Phase,修复后重新测试

---

### 7.3 质量风险

#### 风险6: 德语翻译质量差

**风险描述**: 德语翻译不准确或不符合德语习惯

**应对措施**:
- 使用专业翻译工具(DeepL)
- 德语文本专项测试
- 必要时人工校对

**触发条件**: 德语专项测试发现翻译错误>10处

**应急方案**: 重新翻译德语文本,人工校对

---

#### 风险7: 德语文本布局问题

**风险描述**: 德语文本过长导致布局错乱

**应对措施**:
- Phase 1即开始布局测试
- 使用CSS自适应样式
- 必要时调整组件宽度

**触发条件**: 德语布局测试发现溢出>5处

**应急方案**: 调整CSS样式,增加德语专项布局适配

---

### 7.4 协作风险

#### 风险8: 与Monitor模块冲突

**风险描述**: MDS的i18n改造影响Monitor模块

**应对措施**:
- 使用命名空间隔离(monitor., mds.)
- 测试Monitor模块功能
- 确保向后兼容

**触发条件**: Monitor模块功能异常

**应急方案**: 回退MDS改造,检查命名空间冲突

---

#### 风险9: 浏览器兼容性问题

**风险描述**: 某些浏览器显示异常

**应对措施**:
- 早期进行浏览器测试
- 使用标准API,避免浏览器特定特性
- 提供降级方案

**触发条件**: 浏览器测试发现兼容性问题

**应急方案**: 针对特定浏览器提供降级方案

---

### 7.5 风险监控

**监控频率**: 每日检查

**监控指标**:
- 当前进度vs计划进度
- 测试通过率
- 发现问题数量
- 代码质量指标

**预警阈值**:
- 进度偏差 > 20%
- 测试通过率 < 80%
- 严重问题 > 3个

**应对流程**:
1. 发现风险 → 评估影响 → 制定应对方案 → 执行应对 → 跟踪效果

---

## 八、附录

### 8.1 翻译键命名规范

**命名规则**: `{module}.{category}.{item}`

**示例**:
- `mds.status.pending` - MDS模块的状态文本
- `mds.action.validate` - MDS模块的操作按钮
- `mds.error.DUPLICATE_KEY` - MDS模块的错误消息
- `mds.modal.confirm` - MDS模块的弹窗文本
- `mds.table.noData` - MDS模块的表格文本

**分类**:
- `status` - 状态标签
- `action` - 操作按钮
- `nav` - 导航菜单
- `modal` - 弹窗文本
- `error` - 错误消息
- `table` - 表格文本
- `upload` - 上传相关
- `validation` - 校验相关
- `sync` - 推送相关

---

### 8.2 相关文档

- [MDS-i18n实施方案](./MDS-i18n-Implementation-Proposal.md)
- [Monitor-i18n实施计划](./Monitor-i18n-Implementation-Plan.md)
- [AGENTS.md开发指南](../../AGENTS.md)

---

### 8.3 变更历史

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-05-24 | 初版创建,基于实施方案生成详细任务清单 | CodeArts |

---

**文档状态**: 待执行  
**下一步**: 开始Phase 1任务1.1 - 扩展zh-CN.js语言包
