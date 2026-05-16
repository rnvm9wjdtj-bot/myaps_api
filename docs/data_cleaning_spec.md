# 数据清洗模块开发规范

## 一、字段命名规范

### 1.1 三层命名对应关系

| 层级 | 命名格式 | 示例 | 说明 |
|------|----------|------|------|
| **API层** | 小写 | `materialno`, `description` | POST/GET接口使用 |
| **Python层** | 小写 | `materialno`, `description` | 模型属性名 |
| **数据库层** | 大驼峰 | `MaterialNo`, `Description` | PostgreSQL字段名 |

### 1.2 字段映射机制

通过 `source_field` 参数实现Python字段名到数据库字段名的映射：

```python
# protomodels.py 示例
class ProtoMaterial(TortoiseBaseModel):
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)
    # Python属性名: materialno (小写)
    # 数据库字段名: MaterialNo (大驼峰)
```

---

## 二、API接口规范

### 2.1 请求格式

**POST接口接收数据：**
- 字段名：**小写格式**
- Content-Type: `application/json`

```json
// 示例：POST /api/mds/t_material
[
    {
        "materialno": "MAT001",
        "description": "螺丝M4x10",
        "plant": "chaoyue",
        "type": "F",
        "leadday": 10,
        "unit": "PCS"
    }
]
```

### 2.2 响应格式

**GET接口返回数据：**
- 字段名：**小写格式**
- 已屏蔽内部字段

```json
{
    "status_code": 200,
    "success": 1,
    "message": "查询成功",
    "data": {
        "total": 10,
        "records": [
            {
                "_staging_id": 1,
                "materialno": "MAT001",
                "description": "螺丝M4x10",
                "plant": "chaoyue"
            }
        ]
    }
}
```

### 2.3 数据库连接规范

**校验/同步API必须使用正确的数据库连接：**

```python
# staging_routers.py
@rt.post("/validate/{table_name}")
async def validate_staging(
    request: Request,
    table_name: str,
    batch_size: int = Query(100),
    db_name: str = Query(THIS_DB_NAME, description="账套")  # 使用 THIS_DB_NAME，不是 MYAPS_MAIN_DB
):
    processor = StagingProcessor(db_name)
    stats = await processor.process_staging(table_name, batch_size)
    return standard_response(success=1, message="校验完成", data=stats)
```

### 2.4 时区处理规范

**数据库连接配置：**

```python
# core/database.py
connections[THIS_DB_NAME] = {
    "engine": "tortoise.backends.asyncpg",
    "credentials": {
        "host": THIS_DB_HOST,
        "port": THIS_DB_PORT,
        "user": THIS_DB_USER,
        "password": THIS_DB_PASSWORD,
        "database": THIS_DB_NAME,
        "server_settings": {"TimeZone": TIMEZONE_NAME},
    },
    "min_size": 3,
    "max_size": 10,
    "use_tz": True,  # 启用时区支持
}
```

**模型字段时区配置：**

```python
# staging_models.py
from datetime import datetime, timezone

class StagingBaseModel(TortoiseBaseModel):
    _createtime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc))
    _updatetime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc))
```

**校验逻辑使用原生SQL避免ORM时区问题：**

```python
# staging_cleaner.py
async def process_staging(self, table_name: str, batch_size: int = 100) -> Dict[str, int]:
    from tortoise import Tortoise
    
    conn = Tortoise.get_connection(self.db_name)
    table_name_staging = f"{table_name}_staging"
    
    for record in pending_records:
        # 使用原生SQL更新，避免ORM时区问题
        if is_valid:
            update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1 WHERE "_staging_id" = $2'
            await conn.execute_query(update_query, ("validated", record._staging_id))
```

---

## 三、内部字段屏蔽规则

### 3.1 屏蔽字段列表

以下字段为APS系统内部使用，**不对外暴露**：

| 字段名 | 说明 | 屏蔽原因 |
|--------|------|----------|
| `memo` | 备注 | 系统内部备注 |
| `sys_user` | 系统用户 | 审计字段 |
| `sys_date` | 系统日期 | 审计字段 |
| `sys_stamp` | 系统时间戳 | 审计字段 |

### 3.2 实现位置

在 `staging_routers.py` 中定义：

```python
INTERNAL_FIELDS = {'memo', 'sys_user', 'sys_date', 'sys_stamp'}

def convert_record_to_lowercase(record_dict: Dict, model_class) -> Dict:
    reverse_field_map = {}
    for field in model_class._meta.fields_map.values():
        db_col_name = field.source_field if field.source_field else field.model_field_name
        reverse_field_map[db_col_name] = field.model_field_name
    
    result = {}
    for key, value in record_dict.items():
        python_field = reverse_field_map.get(key, key)
        if python_field in INTERNAL_FIELDS:
            continue
        result[python_field] = value
    return result
```

---

## 四、前端开发规范

### 4.1 页面HTML结构

**标准页面模板：**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[表名]数据清洗管理</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/mds/css/custom.css">
</head>
<body>
    <!-- 导航栏：校验全部/同步全部按钮放右侧 -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-2">
        <div class="container-fluid">
            <a class="navbar-brand" href="/mds">数据清洗管理系统</a>
            <div class="collapse navbar-collapse">
                <ul class="navbar-nav me-auto">
                    <!-- 各表链接 -->
                </ul>
                <div class="d-flex gap-2">
                    <button class="btn btn-outline-light btn-sm" style="width:100px" id="validateAllBtn">校验全部</button>
                    <button class="btn btn-outline-light btn-sm" style="width:100px" id="syncAllBtn">同步全部</button>
                </div>
            </div>
        </div>
    </nav>

    <div class="container-fluid py-2">
        <!-- 状态卡片：全部→已同步→可同步→待处理→校验通过→校验失败 -->
        <div class="row mb-2">
            <div class="col-12" id="statusCardContainer"></div>
        </div>

        <!-- 操作按钮：所有按钮宽度100px -->
        <div class="filter-bar mb-2">
            <div class="row g-2 align-items-center">
                <div class="col-auto">
                    <button class="btn btn-primary btn-sm" style="width:100px" data-bs-toggle="modal" data-bs-target="#uploadModal">导入</button>
                    <button class="btn btn-success btn-sm" style="width:100px" id="validateBtn">校验</button>
                    <button class="btn btn-info btn-sm" style="width:100px" id="syncBtn">同步</button>
                    <button class="btn btn-outline-primary btn-sm" style="width:100px" onclick="downloadTemplate('t_material')">模板</button>
                </div>
                <!-- 筛选控件 -->
            </div>
        </div>

        <!-- 数据列表 -->
        <div class="data-table-container" id="tableContainer"></div>
    </div>

    <!-- 弹窗：精准筛选、批量编辑、上传、编辑 -->
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/mds/js/common.js"></script>
    <script src="/static/mds/js/data-table.js"></script>
    <script src="/static/mds/js/status-card.js"></script>
    <script src="/static/mds/js/[表名].js"></script>
</body>
</html>
```

### 4.2 状态卡片规范

**6个状态卡片顺序：**

```javascript
// status-card.js
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
}
```

**"可同步"计算逻辑：**

```javascript
updateDisplay() {
    // 可同步数 = 校验通过数
    const readySyncCount = (this.stats.validated || 0);
    if (readySync) readySync.textContent = readySyncCount;
}
```

### 4.3 列表配置规范

**列定义：**

```javascript
// [表名].js
const TABLE_COLUMNS = [
    { field: '_status', title: '状态', width: '80px' },        // 状态列最左侧
    { field: '_createtime', title: '创建时间', width: '180px', sortable: true },  // 时间列180px
    { field: 'materialno', title: '物料号', width: '100px', sortable: true },
    // ... 其他业务字段
    { field: '_source_system', title: '来源', width: '80px' }
    // 注意：不包含 _staging_id（隐藏）
];
```

**字段标签映射（用于详情弹窗显示中文）：**

```javascript
const FIELD_LABELS = {};
TABLE_COLUMNS.forEach(col => {
    FIELD_LABELS[col.field] = col.title;
});
```

### 4.4 枚举字段配置

**必须与schemas.py一致：**

```javascript
// [表名].js
const ENUM_OPTIONS = {
    // 文本枚举
    fifo: [
        { value: '0', label: '最近原则' },
        { value: '1', label: 'FIFO' }
    ],
    abc: [
        { value: 'A', label: 'A类' },
        { value: 'B', label: 'B类' },
        { value: 'C', label: 'C类' }
    ],
    type: [
        { value: 'E', label: '自制件(E)' },
        { value: 'F', label: '采购件(F)' }
    ],
    phantom: [
        { value: 'N', label: '否' },
        { value: 'Y', label: '是' }
    ],
    candelay: [
        { value: 'N', label: '否' },
        { value: 'Y', label: '是' }
    ],
    lotsize: [
        { value: 'EX', label: 'EX-一对一' },
        { value: 'FX', label: 'FX-固定批' },
        { value: 'VB', label: 'VB-重订货点' },
        { value: 'D1', label: 'D1-按1天合并' },
        { value: 'D2', label: 'D2-按2天合并' },
        { value: 'D3', label: 'D3-按3天合并' },
        { value: 'D4', label: 'D4-按4天合并' },
        { value: 'D5', label: 'D5-按5天合并' },
        { value: 'D6', label: 'D6-按6天合并' },
        { value: 'W1', label: 'W1-按1周合并' },
        { value: 'W2', label: 'W2-按2周合并' },
        { value: 'W3', label: 'W3-按3周合并' },
        { value: 'W4', label: 'W4-按4周合并' },
        { value: 'M1', label: 'M1-按1月合并' },
        { value: 'M2', label: 'M2-按2月合并' },
        { value: 'M3', label: 'M3-按3月合并' }
    ]
};
```

### 4.5 NULL字段显示规范

**列表中NULL字段：**

```javascript
// data-table.js
renderCell(col, row) {
    let value = row[col.field];
    
    if (value === null || value === undefined) {
        // 自定义字段(free*)不高亮
        const isFreeField = col.field.startsWith('free');
        return isFreeField 
            ? '<span class="text-muted">-</span>' 
            : '<span class="null-cell">-</span>';  // 浅橙高亮
    }
    // ...
}
```

**详情弹窗隐藏系统字段：**

```javascript
function showDetailModal(row) {
    // 过滤掉 _ 开头的系统字段
    const businessFields = Object.entries(row).filter(([key]) => !key.startsWith('_'));
    
    detailContent.innerHTML = `
        <table class="table table-sm table-bordered">
            <tbody>
                ${businessFields.map(([key, value]) => `
                    <tr>
                        <th style="width: 120px">${FIELD_LABELS[key] || key}</th>
                        <td>${formatDetailValue(key, value)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}
```

### 4.6 编辑弹窗规范

**两列布局，modal-xl宽度：**

```html
<div class="modal fade" id="editModal" tabindex="-1">
    <div class="modal-dialog modal-xl">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">编辑记录</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <form id="editForm"></form>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                <button class="btn btn-primary" id="saveBtn">保存</button>
            </div>
        </div>
    </div>
</div>
```

**字段生成逻辑：**

```javascript
function generateEditField(col, row) {
    const fieldName = col.field;
    const fieldValue = row[fieldName] !== null && row[fieldName] !== undefined ? row[fieldName] : '';
    
    const labelHtml = `<label class="form-label mb-1">${col.title}</label>`;
    
    if (ENUM_OPTIONS[fieldName]) {
        // 枚举字段：下拉选择
        const options = ENUM_OPTIONS[fieldName];
        return `
            <div class="mb-2">
                ${labelHtml}
                <select class="form-select font-mono" name="${fieldName}" 
                        style="height: 31px; padding: 0.25rem 0.5rem; font-size: 0.8rem;">
                    <option value="">-- 请选择 --</option>
                    ${options.map(opt => `
                        <option value="${opt.value}" ${String(fieldValue) === String(opt.value) ? 'selected' : ''}>
                            ${opt.label}
                        </option>
                    `).join('')}
                </select>
            </div>
        `;
    }
    
    // 普通字段：文本输入
    return `
        <div class="mb-2">
            ${labelHtml}
            <input type="text" class="form-control font-mono" name="${fieldName}" 
                   value="${escapeHtml(String(fieldValue))}"
                   style="height: 31px; padding: 0.25rem 0.5rem; font-size: 0.8rem;">
        </div>
    `;
}
```

### 4.7 精准筛选规范

**字段分类：**

```javascript
function bindAdvancedFilterEvents() {
    const stringFields = [
        { value: 'MaterialNo', label: '物料号' },
        { value: 'Description', label: '物料描述' },
        { value: 'Plant', label: '工厂' },
        { value: 'Planner', label: '计划员' },
        { value: 'Unit', label: '单位' }
    ];
    
    const numberFields = [
        { value: 'LeadDay', label: '提前期' },
        { value: 'ExpDay', label: '保质期' },
        { value: 'GRDay', label: '质检期' },
        { value: 'Price', label: '价格' },
        // ...
    ];
    
    const enumFields = [
        { value: 'ABC', label: 'ABC分类', options: ENUM_OPTIONS.abc },
        { value: 'Type', label: '类型', options: ENUM_OPTIONS.type },
        { value: 'Phantom', label: '虚拟件', options: ENUM_OPTIONS.phantom },
        { value: 'CanDelay', label: '可延迟', options: ENUM_OPTIONS.candelay },
        { value: 'LotSize', label: '批量策略', options: ENUM_OPTIONS.lotsize },
        { value: 'FIFO', label: 'FIFO', options: ENUM_OPTIONS.fifo }
    ];
}
```

**匹配模式：**

| 字段类型 | 匹配模式 |
|----------|----------|
| 文本字段 | 等于、不等于、包含、不包含、开头是、结尾是、为空、不为空 |
| 数值字段 | =、>、>=、<、<=、为空、不为空 |
| 枚举字段 | 等于、包含、不包含、为空、不为空（用下拉选项代替输入） |

### 4.8 批量编辑规范

**核心实现：**

```javascript
function bindBatchEditEvents() {
    let fieldValues = {};      // 保存已输入的值
    let nullFields = new Set(); // 标记需要清空的字段
    
    function renderBatchEditFields() {
        const selectedFields = [...]; // 从checkbox获取
        
        batchEditFields.innerHTML = selectedFields.map(field => {
            const col = editableFields.find(c => c.field === field);
            const enumOptions = ENUM_OPTIONS[field];
            const isNull = nullFields.has(field);
            const savedValue = fieldValues[field] || '';
            
            let inputHtml;
            if (enumOptions) {
                inputHtml = `<select ...>${options}</select>`;
            } else {
                inputHtml = `<input type="text" value="${savedValue}" ...>`;
            }
            
            const clearBtnClass = isNull ? 'btn-danger' : 'btn-outline-danger';
            const clearBtnText = isNull ? '已清空(点击恢复)' : '清空';
            
            return `...${inputHtml}...<button class="btn ${clearBtnClass}">${clearBtnText}</button>...`;
        }).join('');
    }
    
    // 提交时将nullFields中的字段设置为null
    if (applyBatchEditBtn) {
        applyBatchEditBtn.addEventListener('click', async () => {
            const updates = {};
            // 收集非空值
            batchEditFields.querySelectorAll('.batch-edit-value').forEach(input => {
                if (input.value.trim()) updates[input.dataset.field] = input.value.trim();
            });
            // 添加null值
            nullFields.forEach(field => updates[field] = null);
            // 提交
            const response = await callApi(`/batch_update/${TABLE_NAME}`, 'POST', { ids, updates });
        });
    }
}
```

### 4.9 表格布局规范

**冻结表头表尾：**

```javascript
// data-table.js
render() {
    this.container.innerHTML = `
        <div class="table-wrapper" style="display: flex; flex-direction: column; height: calc(100vh - 280px);">
            <div class="table-responsive flex-grow-1" style="overflow-y: auto; overflow-x: auto;">
                <table class="table table-hover table-nowrap mb-0">
                    <thead class="table-header-fixed">
                        <!-- 表头 -->
                    </thead>
                    <tbody id="tableBody">
                        <!-- 数据行 -->
                    </tbody>
                </table>
            </div>
        </div>
        <div class="table-footer-fixed d-flex justify-content-between align-items-center px-2 py-2 bg-white border-top">
            <!-- 分页栏固定底部 -->
        </div>
    `;
}
```

```css
/* custom.css */
.table-header-fixed {
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: #f8f9fa;
}

.table-footer-fixed {
    position: sticky;
    bottom: 0;
    z-index: 10;
}
```

### 4.10 全选按钮规范

**按钮位置：批量编辑按钮左侧**

```javascript
// data-table.js render()方法
<div class="d-flex align-items-center gap-2">
    <span id="totalInfo">共 0 条</span>
    <select class="form-select form-select-sm" id="pageSizeSelect">...</select>
    <span>条/页</span>
    
    <!-- 全选按钮 -->
    <button class="btn btn-sm btn-outline-success" id="selectAllPagesBtn">
        全选(<span id="totalCount">0</span>)
    </button>
    
    <!-- 批量操作按钮 -->
    <button class="btn btn-sm btn-outline-primary ms-2" id="batchEditBtn" disabled>
        编辑(<span id="selectedCount">0</span>)
    </button>
    <button class="btn btn-sm btn-outline-danger" id="batchDeleteBtn" disabled>
        删除(<span id="selectedCountDup">0</span>)
    </button>
</div>
```

**功能实现：**

```javascript
// data-table.js

// 1. 更新总记录数显示
updateTotalCount() {
    const totalCount = document.getElementById('totalCount');
    if (totalCount) {
        totalCount.textContent = this.total;
    }
}

// 2. 全选所有分页记录
async selectAllPages() {
    if (this.total === 0) {
        showMessage('没有可选择的记录', 'warning');
        return;
    }
    
    if (!confirm(`确定选中全部 ${this.total} 条记录吗？\n\n注意：这将获取所有分页的记录ID，可能需要较长时间。`)) {
        return;
    }
    
    showLoading();
    
    // 获取所有分页的记录ID（page_size=10000）
    const queryParams = new URLSearchParams({
        page: 1,
        page_size: 10000,
        sort_field: this.sortField,
        sort_order: this.sortOrder,
        ...this.filters
    });
    
    if (this.advancedFilters && this.advancedFilters.length > 0) {
        queryParams.set('advanced_filters', JSON.stringify(this.advancedFilters));
    }
    
    const response = await callApi(`/list/${this.tableName}?${queryParams}`);
    
    hideLoading();
    
    handleResponse(response, (data) => {
        const allRecords = data.data.records || [];
        this.selectedIds.clear();
        allRecords.forEach(row => {
            this.selectedIds.add(row._staging_id);
        });
        
        // 更新UI
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = true;
        
        document.querySelectorAll('.row-checkbox').forEach(cb => {
            cb.checked = true;
        });
        
        this.updateSelectedCount();
        showMessage(`已选中 ${this.selectedIds.size} 条记录`, 'success');
    });
}

// 3. 绑定事件
bindEvents() {
    const selectAllPagesBtn = document.getElementById('selectAllPagesBtn');
    if (selectAllPagesBtn) {
        selectAllPagesBtn.addEventListener('click', () => this.selectAllPages());
    }
    // ...
}
```

**按钮布局（从左到右）：**

```
共 1250 条 | 100 条/页 | 全选(1250) | 编辑(0) | 删除(0)
```

### 4.12 Checkbox状态管理

**所有数据重载操作必须清除选中状态：**

```javascript
// data-table.js

// 1. setFilter方法
setFilter(key, value) {
    // ...
    this.selectedIds.clear();
    const selectAll = document.getElementById('selectAll');
    if (selectAll) selectAll.checked = false;
    this.updateSelectedCount();
    this.loadData();
}

// 2. loadData方法
async loadData(params = {}) {
    if (Object.keys(params).length > 0 || this.advancedFilters) {
        this.selectedIds.clear();
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        this.updateSelectedCount();
    }
    // ...
}

// 3. 翻页
pagination.querySelectorAll('.page-link').forEach(link => {
    link.addEventListener('click', (e) => {
        // ...
        this.selectedIds.clear();
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        this.updateSelectedCount();
        this.loadData();
    });
});

// 4. 精准筛选
if (applyBtn) {
    applyBtn.addEventListener('click', () => {
        // ...
        dataTable.selectedIds.clear();
        const selectAll = document.getElementById('selectAll');
        if (selectAll) selectAll.checked = false;
        dataTable.updateSelectedCount();
        dataTable.loadData();
    });
}
```

### 4.13 时间格式化规范

**显示格式：yyyy-mm-dd hh:mm:ss**

```javascript
// common.js
function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    const second = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}
```

### 4.14 等宽字体规范

**所有数据内容使用等宽字体：**

```css
/* custom.css */
:root {
    --mono-font: 'JetBrains Mono', 'Menlo', 'Source Code Pro', 'Consolas', monospace;
}

.font-mono {
    font-family: var(--mono-font);
}
```

```javascript
// data-table.js
renderCell(col, row) {
    // ...
    return `<span class="font-mono">${escapeHtml(value)}</span>`;
}
```

---

## 五、后端开发规范

### 5.1 校验阶段默认值填充

**校验时自动填充schemas.py中定义的默认值：**

```python
# staging_cleaner.py

# 1. 从schemas.py提取各表默认值配置
SCHEMA_DEFAULTS = {
    "t_material": {
        "plant": AcceptMaterial.model_fields["plant"].default,
        "planner": AcceptMaterial.model_fields["planner"].default,
        "fifo": AcceptMaterial.model_fields["fifo"].default,
        "expday": AcceptMaterial.model_fields["expday"].default,
        "phantom": AcceptMaterial.model_fields["phantom"].default,
        # ... 其他有默认值的字段
    },
    "t_workcenter": {
        "pri_wc": AcceptWorkcenter.model_fields["pri_wc"].default,
        "bottleneck": AcceptWorkcenter.model_fields["bottleneck"].default,
        # ...
    },
    # ... 其他表
}

# 2. 默认值填充函数
NONE_AND_EMPTY = {None, ""}

def fill_defaults(table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    对于NULL或空字符串的字段，使用schemas.py中定义的默认值填充
    
    Args:
        table_name: 表名
        data: 原始数据字典
        
    Returns:
        填充后的数据字典
    """
    defaults = SCHEMA_DEFAULTS.get(table_name, {})
    if not defaults:
        return data
    
    result = data.copy()
    for field_name, default_value in defaults.items():
        if default_value is None:
            continue
        if result.get(field_name) in NONE_AND_EMPTY:
            result[field_name] = default_value
    
    return result

# 3. 校验流程中调用
async def process_staging(self, table_name: str, batch_size: int = 100):
    for record in pending_records:
        data = self._record_to_dict(record)
        
        # 先填充默认值
        filled_data = fill_defaults(table_name, data)
        
        # 更新缓冲表（将填充的值写入数据库）
        if filled_fields:
            update_query = f'UPDATE "{table_name_staging}" SET ...'
            await conn.execute_query(update_query, ...)
            stats["filled"] += 1
        
        # 再校验
        is_valid, errors = await self._validate(table_name, record._staging_id, filled_data)
```

**各表默认值字段清单：**

| 表名 | 有默认值的字段 |
|------|---------------|
| t_material | plant, planner, fifo, expday, phantom, phantommin, firmday, daygap, candelay, lotsize, lotfix, lotmin, lotmax, lotround, lotss, lotpoint, lottop, preday, subday |
| t_workcenter | pri_wc, bottleneck, plant, finite, type |
| t_mat_ver | lotfrom, lotto, priority, active |
| t_mat_wc | fixqty, fixsec, sf, offsetsec, rate |
| t_mat_wc_bom | offsethour |
| t_mold | (无) |
| t_mat_wc_mold | moldno, fixsec |

**校验返回统计：**

```python
stats = {
    "filled": 2,      # 填充了默认值的记录数
    "validated": 10,
    "rejected": 1
}
```

### 5.2 查询字段大小写映射

**精准筛选字段名必须使用数据库实际字段名：**

```python
# staging_routers.py
if advanced_filters:
    filters = json.loads(advanced_filters)
    for f in filters:
        field = f.get('field')  # 这里field必须是数据库字段名（如MaterialNo）
        operator = f.get('operator')
        value = f.get('value')
        
        if operator == 'eq' and value:
            conditions.append(f'"{field}" = ${param_idx}')
            params.append(value)
```

**排序字段映射：**

```python
sort_field_mapping = {
    '_createtime': '_createtime',  # 系统字段保持小写
    '_updatetime': '_updatetime',
    'materialno': 'MaterialNo'     # 业务字段映射为大驼峰
}
db_sort_field = sort_field_mapping.get(sort_field, sort_field)
```

**查询字段映射：**

```python
if keyword:
    # 搜索物料号和描述
    conditions.append(f'("MaterialNo" LIKE ${param_idx} OR "Description" LIKE ${param_idx})')
    params.append(f"%{keyword}%")
```

### 5.2 批量更新API

**支持NULL值：**

```python
@rt.post("/batch_update/{table_name}")
async def batch_update_staging(request: Request, table_name: str, data: dict = Body(...)):
    ids = data.get('ids', [])
    updates = data.get('updates', {})
    
    set_clauses = []
    params = []
    param_idx = 1
    
    for python_field, value in updates.items():
        db_field = field_mapping.get(python_field, python_field)
        if value is None:
            # NULL值直接设置
            set_clauses.append(f'"{db_field}" = NULL')
        else:
            set_clauses.append(f'"{db_field}" = ${param_idx}')
            params.append(value)
            param_idx += 1
    
    params.append(ids)
    update_query = f'''
        UPDATE "{table_name_staging}"
        SET {', '.join(set_clauses)}, "_updatetime" = NOW()
        WHERE "_staging_id" = ANY(${param_idx})
    '''
    await conn.execute_query(update_query, tuple(params))
```

---

## 六、业务字段完整列表

### 6.1 物料表 (t_material)

| 字段名 | 说明 | 必填 | 枚举值 |
|--------|------|------|--------|
| materialno | 物料号 | ✓ | - |
| description | 物料描述 | ✓ | - |
| size | 规格 | - | - |
| plant | 工厂 | ✓ | - |
| planner | 计划员 | - | - |
| fifo | FIFO标识 | - | 0/1 |
| leadday | 提前期(天) | ✓ | - |
| expday | 保质期(天) | - | - |
| grday | 收货质检(天) | ✓ | - |
| abc | ABC分类 | - | A/B/C |
| unit | 单位 | - | - |
| price | 价格 | - | - |
| groupno | 型号/分组 | - | - |
| type | 物料类型 | - | E/F |
| phantom | 虚拟件 | - | Y/N |
| phantommin | 虚拟时间(分) | - | - |
| firmday | 固定天数 | - | - |
| daygap | MTO拆分天数 | - | - |
| candelay | 可否延迟 | - | Y/N |
| lotsize | 批量策略 | - | EX/FX/VB/D1-D6/W1-W4/M1-M3 |
| lotfix | 固定批量 | - | - |
| lotmin | 最小批量 | - | - |
| lotmax | 最大批量 | - | - |
| lotround | 取整值 | - | - |
| lotss | 安全库存 | - | - |
| lotpoint | 重订货点 | - | - |
| lottop | 最大库存点 | - | - |
| planitem | 产品组 | - | - |
| preday | 向前冲销(天) | - | - |
| subday | 向后冲销(天) | - | - |
| free1 | 自定义1 | - | - |
| free2 | 自定义2 | - | - |
| free3 | 自定义3 | - | - |

---

## 七、开发检查清单

### 7.1 前端开发检查

- [ ] 页面HTML结构符合模板
- [ ] 状态卡片顺序正确（6个）
- [ ] 列配置包含所有业务字段
- [ ] 枚举配置与schemas.py一致
- [ ] 编辑弹窗两列布局
- [ ] 精准筛选字段分类正确
- [ ] 批量编辑支持NULL设置
- [ ] 时间格式yyyy-mm-dd hh:mm:ss
- [ ] 等宽字体应用正确
- [ ] 所有按钮宽度100px
- [ ] Checkbox状态管理完整
- [ ] 全选按钮功能正常

### 7.2 后端开发检查

- [ ] 数据库连接使用THIS_DB_NAME
- [ ] 时区配置正确（use_tz: True）
- [ ] 字段映射正确（小写→大驼峰）
- [ ] 查询字段大小写正确
- [ ] 批量更新支持NULL值
- [ ] 校验逻辑使用原生SQL
- [ ] 内部字段已屏蔽
- [ ] 默认值配置正确（从schemas.py提取）
- [ ] 校验流程包含默认值填充步骤

**v3.0 配置驱动校验检查（新增）**：

- [ ] Schema定义完整（包含所有校验约束：必填、枚举、范围、长度）
- [ ] `STAGING_TABLE_CONFIG` 配置正确（schema、model、proto_model、foreign_keys）
- [ ] 特殊业务规则已单独编写（无法通过Schema表达的规则）
- [ ] `business_keys` 从proto_model自动提取
- [ ] 外键约束已在配置中声明

---

## 八、更新日志

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-05-12 | v1.0 | 初始版本 |
| 2026-05-12 | v2.0 | 完整前后端开发规范，可作为其他表的实施范式 |
| 2026-05-12 | v2.1 | 新增：校验阶段自动填充默认值、前端全选按钮功能 |
| 2026-05-12 | v2.2 | 修复：单条编辑空字符串处理、必填字段清空校验、校验循环处理、枚举校验完善、编辑后状态重置 |
| 2026-05-12 | v2.3 | 优化：校验错误详情展示、datetime时区修复、枚举标签样式、校验进度条动画 |
| 2026-05-12 | v2.4 | 优化：双击编辑、错误呼吸动画、同步模式选择、数据类型转换、UPSERT机制 |
| 2026-05-13 | v2.5 | 重大更新：多账套同步支持、前端内存泄漏修复、None值累加全面修复、错误信息格式统一、刷新同步逻辑优化 |
| 2026-05-14 | v3.0 | **架构级重构**：校验逻辑从硬编码转为配置驱动，通过Pydantic Schema自动提取校验规则，大幅提升可维护性和扩展性 |
| 2026-05-15 | v3.1 | **两阶段校验增强**：新增合规性校验、关联校验分阶段处理，新增校验规则文档化API，完善前端通用组件库 |
| 2026-05-15 | v3.2 | **前端架构重构**：通用控制器 + 配置驱动，所有表共用同一套代码，新增表只需编写配置文件 |
| 2026-05-15 | v3.3 | **配置自动生成 + Excel导入**：从后端 Schema 自动生成前端配置文件，新增表"零配置"，新增 Bootstrap 图标库，增强 Excel 导入功能，完成架构清理 |

---

## 九、v2.5版本更新详情

### 9.1 多账套同步支持

**新增功能**：支持将数据同步到多个账套（数据库）。

**前端实现**：
- 同步模式对话框增加账套选择
- 默认全选所有账套，可取消勾选排除

**后端实现**：
- `sync_to_production` 新增 `update_status` 参数
- 多账套同步策略：
  - 先同步所有账套（`update_status=False`）
  - 最后统一更新缓冲表状态

**代码示例**：

```python
# staging_routers.py
if len(target_db_list) > 1:
    # 第一步：同步到所有账套（不更新状态）
    for target_db in target_db_list:
        stats = await processor.sync_to_production(
            table_name=table_name,
            target_db=target_db,
            update_status=False  # 不更新状态
        )
    
    # 第二步：统一更新缓冲表状态
    update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1 WHERE "_status" = $2'
    await conn.execute_query(update_query, ("synced", "validated"))
```

### 9.2 前端内存泄漏修复

**问题1：Blob URL未释放**

```javascript
// 修复前
link.href = URL.createObjectURL(blob);
link.click();
// Blob URL泄漏！

// 修复后
const blobUrl = URL.createObjectURL(blob);
link.href = blobUrl;
link.click();
setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
```

**问题2：Tooltip DOM未删除**

```javascript
// 修复前
cell.addEventListener('mouseleave', (e) => {
    e.target._tooltip.style.display = 'none';  // 只隐藏
});

// 修复后
cell.addEventListener('mouseleave', (e) => {
    e.target._tooltip.remove();  // 删除DOM
    e.target._tooltip = null;
});
```

### 9.3 None值累加全面修复

**问题根源**：Python的 `dict.get("key", 0)` 在值为 `None` 时返回 `None` 而非默认值。

**错误写法**：
```python
value = dict.get("key", 0) + 1  # 如果值是None → TypeError!
```

**正确写法**：
```python
value = (dict.get("key") or 0) + 1  # 先取值，再处理None
```

**修复位置**：

| 文件 | 修复内容 |
|------|----------|
| `db_operation.py` | 批次累加、账套累加、affected_rows计算 |
| `db_manager.py` | `total_inserted`、`total_updated` |
| `staging_cleaner.py` | `stats["failed"]`、`retry_count` |
| `staging_routers.py` | `total_synced`、`total_failed` |
| `event_aggregator.py` | `low_queue_count` |

### 9.4 错误信息格式统一

**问题**：`_error_msg` 字段格式不统一，前端解析失败。

**统一格式**：

```json
[
  {
    "staging_id": 123,
    "error_type": "schema_error",
    "error_field": "groupno",
    "error_value": null,
    "error_message": "Input should be a valid string"
  }
]
```

**前端容错**：

```javascript
// data-table.js
parseErrorFields(row) {
    try {
        let errorData = row._error_msg;
        if (typeof errorData === 'string') {
            errorData = JSON.parse(errorData);
        }
        if (!Array.isArray(errorData)) {
            errorData = [errorData];
        }
        // ...
    } catch (e) {
        errorMap['_error'] = { type: 'parse_error', message: '错误信息格式异常' };
    }
}
```

### 9.5 刷新同步逻辑优化

**问题**：前端循环调用同步API，每次都执行TRUNCATE，导致数据被清空。

**修复方案**：

| 模式 | 前端调用策略 |
|------|-------------|
| 增量模式 | 循环调用直到没有数据 |
| 刷新模式 | 只调用一次 |

**代码示例**：

```javascript
// material.js
if (mode === 'refresh') {
    // 刷新模式：一次性同步
    const syncResponse = await callApi(`/sync/${TABLE_NAME}?mode=${mode}...`);
    // 直接显示结果
} else {
    // 增量模式：循环调用
    while (true) {
        const syncResponse = await callApi(`/sync/${TABLE_NAME}?mode=${mode}...`);
        if (batchSynced === 0 && batchFailed === 0) break;
    }
}
```

### 9.6 默认值填充增强

**问题**：Schema中部分字段默认值为 `None`，填充函数未处理。

**修复**：`fill_defaults` 函数增强：

```python
def fill_defaults(table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    # 遍历所有字段
    for field_name, field_info in schema_class.model_fields.items():
        current_value = result.get(field_name)
        
        if current_value in NONE_AND_EMPTY:
            # 优先使用 SCHEMA_DEFAULTS
            if field_name in defaults and defaults[field_name] is not None:
                result[field_name] = defaults[field_name]
            else:
                # 从 Field.default 获取
                field_default = field_info.default
                if field_default is not None:
                    result[field_name] = field_default
                # 特殊处理：可选字符串 → ""
                elif field_name in ['size', 'planitem', 'memo']:
                    result[field_name] = ""
                # 特殊处理：可选数值 → 0.0
                elif field_name in ['lotmin', 'lotmax']:
                    result[field_name] = 0.0
```

---

## 十、v2.4版本更新详情

### 9.1 双击编辑触发

**修改内容**：单击改双击打开编辑弹窗。

```javascript
// data-table.js
tbody.querySelectorAll('.table-row').forEach(tr => {
    tr.addEventListener('dblclick', (e) => {  // click → dblclick
        // 打开编辑弹窗
    });
    tr.style.cursor = 'pointer';
    tr.title = '双击编辑';
});
```

### 9.2 错误字段呼吸动画

**动画参数**：

| 元素 | 周期 | 效果 |
|------|------|------|
| 枚举错误标签 | 3s | 背景色 + 外发光 |
| 错误单元格 | 3s | 背景色 + 边框 + 外发光 |
| 校验失败行 | 4s | 背景色渐变 |

**CSS动画**：

```css
@keyframes error-cell-breathe {
    0%, 100% {
        background-color: #ffe6e6;
        border-color: #dc3545;
        box-shadow: 0 0 0 rgba(220, 53, 69, 0);
    }
    50% {
        background-color: #ffcccc;
        border-color: #ff6666;
        box-shadow: 0 0 6px rgba(220, 53, 69, 0.4);
    }
}

@keyframes row-rejected-breathe {
    0%, 100% { background-color: #fff8f8; }
    50% { background-color: #fff0f0; }
}
```

### 9.3 同步模式选择

**两种模式**：

| 模式 | 说明 | 数据范围 |
|------|------|----------|
| 增量同步 | 仅同步校验通过的新数据 | validated 状态 |
| 刷新同步 | 清空正式表后重新同步 | validated 状态 |

**前端对话框**：

```javascript
function showSyncModeDialog(validatedCount) {
    // 显示两种模式选项
    // 增量同步：保留正式表现有数据
    // 刷新同步：删除正式表所有数据
}
```

**后端实现**：

```python
async def sync_to_production(..., mode: str = "incremental"):
    if mode == "refresh":
        # 清空正式表
        await mysql_conn.execute_query(f'TRUNCATE TABLE `{target_table_name}`')
    
    # 无论哪种模式，都只同步 validated 状态
    query = f'SELECT * FROM "{staging_table_name}" WHERE "_status" = $1'
```

### 9.4 数据类型自动转换

**问题**：前端表单提交都是字符串，数据库需要正确类型。

**修复**：后端根据字段类型自动转换。

```python
field_types = {}
for field in model_class._meta.fields_map.values():
    field_types[field.model_field_name] = type(field).__name__

for key, value in data.items():
    field_type = field_types.get(key, '')
    if field_type == 'IntField':
        value = int(value)
    elif field_type == 'FloatField':
        value = float(value)
    elif field_type == 'DecimalField':
        value = Decimal(str(value))
```

**影响范围**：
- POST接收数据（insert_to_staging_table）
- 单条编辑（update_staging）
- 批量编辑（batch_update_staging）

### 9.5 UPSERT机制

**问题**：POST接收数据时，已存在记录会主键冲突报错。

**修复**：改为 INSERT ON CONFLICT UPDATE。

```python
query = f'''
    INSERT INTO "{table_name}" ({column_list}) VALUES ({placeholders})
    ON CONFLICT ({conflict_target}) DO UPDATE SET {update_clause}
'''
```

**各表主键**：

| 表名 | 主键字段 |
|------|----------|
| t_material | materialno |
| t_workcenter | workcenter |
| t_mat_ver | materialno, matver |
| t_mat_wc | materialno, matver, itemno |
| t_mat_wc_bom | productno, matver, itemno, materialno |
| t_mold | moldno |
| t_mat_wc_mold | materialno, workcenter, itemno, moldno |

**行为变化**：

| 场景 | 之前 | 现在 |
|------|------|------|
| 新记录 | INSERT，状态 pending | INSERT，状态 pending |
| 已存在记录 | ❌ 主键冲突 | UPDATE，状态 pending |
| 已校验记录被覆盖 | 不可能 | 状态重置为 pending |

**UPDATE字段**：
- 所有业务字段
- `_source_system`
- `_status` → 'pending'
- `_updatetime` → NOW()

**不更新**：
- `_staging_id`
- `_createtime`

### 9.6 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `staging_routers.py` | UPSERT、类型转换 |
| `staging_cleaner.py` | 同步模式参数、原生SQL |
| `data-table.js` | 双击编辑、enumFields |
| `material.js` | 同步模式对话框、进度条 |
| `custom.css` | 呼吸动画 |

---

## 十、v3.0版本更新详情

### 10.1 架构重构概述

**核心变更**：后端校验逻辑从**硬编码模式**重构为**配置驱动模式**。

**设计理念**：Schema即规则，一次定义处处复用。

**收益对比**：

| 维度 | v2.5及之前 | v3.0 | 提升幅度 |
|------|------------|------|----------|
| 代码复用 | 每个表重复编码 | 配置驱动，自动提取 | **~50%代码量减少** |
| 新增表成本 | 100+行代码 | 仅需配置Schema | **从小时级降为分钟级** |
| 规则一致性 | 人工保证 | 自动从Schema提取 | **消除人工差异** |
| 扩展性 | 修改规则需改多处 | 只需修改Schema | **变更成本大幅降低** |

### 10.2 配置驱动校验机制

**新增核心方法**：`validate_from_config()`

```python
# staging_cleaner.py - DataCleaner 类
async def validate_from_config(self, table_key, data, staging_id):
    errors = []
    config = STAGING_TABLE_CONFIG.get(table_key)
    schema_class = config["schema"]
    
    # 1. 从Schema自动提取并校验所有必填字段
    self.validate_required_from_schema(errors, staging_id, data, schema_class)
    
    # 2. 从Schema自动提取并校验所有枚举字段
    self.validate_enums_from_schema(errors, staging_id, data, schema_class)
    
    # 3. 从Schema自动提取并校验所有范围约束字段
    self.validate_ranges_from_schema(errors, staging_id, data, schema_class)
    
    # 4. 从Schema自动提取并校验所有字符串长度约束
    self.validate_max_lengths_from_schema(errors, staging_id, data, schema_class)
    
    # 5. 从配置自动提取并校验所有外键约束
    await self.validate_foreign_keys_from_config(errors, staging_id, data, table_key)
    
    # 6. 重复检查
    is_unique, dup_errors = await self.check_duplicate(table_key, data, staging_id)
    errors.extend(dup_errors)
    
    return errors
```

### 10.3 自动提取函数

| 函数 | 功能 | 提取来源 |
|------|------|----------|
| `extract_defaults_from_schema()` | 提取默认值配置 | `model_fields[field].default` |
| `extract_required_fields()` | 提取必填字段列表 | `model_fields[field].is_required()` |
| `extract_enum_fields()` | 提取枚举字段及允许值 | `Annotated` + `Field(description=...)` |
| `extract_range_fields()` | 提取数值范围约束 | `gt`, `ge`, `lt`, `le` 参数 |
| `extract_max_length_fields()` | 提取字符串长度约束 | `max_length` 参数 |
| `get_field_map()` | 统一获取模型字段映射 | 模型元数据 |

### 10.4 校验方法简化对比

**v2.5及之前（硬编码）**：

```python
async def validate_material(self, data, staging_id):
    errors = []
    # 硬编码1：必填字段检查
    if not data.get("materialno"):
        errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "materialno", None, "物料号不能为空"))
    if not data.get("description"):
        errors.append(self._create_error(staging_id, ErrorType.REQUIRED_FIELD, "description", None, "物料描述不能为空"))
    # 硬编码2：枚举值检查
    abc_value = data.get("abc")
    if abc_value and str(abc_value) not in self.ABC_ENUM:
        errors.append(self._create_error(staging_id, ErrorType.INVALID_ENUM, "abc", abc_value, "ABC分类必须为: A, B, C"))
    # ... 大量重复代码
    # 硬编码3：重复检查
    is_unique, dup_errors = await self.check_duplicate("t_material", data, staging_id)
    errors.extend(dup_errors)
    return len(errors) == 0, errors
```

**v3.0（配置驱动）**：

```python
async def validate_material(self, data, staging_id):
    # 自动从配置提取规则
    errors = await self.validate_from_config("t_material", data, staging_id)
    
    # 仅保留特殊业务规则（无法通过Schema表达的）
    lotmin = data.get("lotmin")
    lotmax = data.get("lotmax")
    if lotmin is not None and lotmax is not None and lotmin > lotmax:
        errors.append(self._create_error(staging_id, ErrorType.BUSINESS_RULE, "lotmin/lotmax",
            f"{lotmin}/{lotmax}", "最小批量不能大于最大批量"))
    
    return len(errors) == 0, errors
```

### 10.5 配置结构增强

`STAGING_TABLE_CONFIG` 现在会**自动填充**以下配置项：

```python
# 自动生成的配置项
config["table_name"] = config["model"]._meta.table
config["display_name"] = extract_display_name_from_model(config["model"])
config["defaults"] = extract_defaults_from_schema(config["schema"])
config["business_keys"] = extract_business_keys_from_model(config["proto_model"])
```

### 10.6 新开发流程

**新增数据表步骤**（从100+行代码降为3步）：

```
1. 定义Schema（schemas.py）
   ↓
2. 配置STAGING_TABLE_CONFIG（staging_cleaner.py）
   ↓
3. 编写特殊业务规则（如需要）
```

**示例**：新增设备表 `t_equipment`

```python
# 步骤1：定义Schema
class AcceptEquipment(BaseModel):
    equipno: str = Field(..., description="设备编号")
    description: str = Field(..., description="设备描述")
    plant: str = Field(default="chaoyue", description="工厂")
    status: Literal['A', 'I'] = Field(default='A', description="状态")
    capacity: float = Field(gt=0, description="产能", default=0.0)

# 步骤2：配置表映射
STAGING_TABLE_CONFIG["t_equipment"] = {
    "schema": AcceptEquipment,
    "model": TEquipmentStaging,
    "proto_model": ProtoEquipment,
    "foreign_keys": [],
}

# 步骤3：编写业务规则（如不需要可省略）
async def validate_equipment(self, data, staging_id):
    errors = await self.validate_from_config("t_equipment", data, staging_id)
    # 特殊规则...
    return len(errors) == 0, errors
```

### 10.7 修改文件清单

| 文件 | 变更类型 | 核心改动 |
|------|----------|----------|
| `staging_cleaner.py` | **重构** | 新增 `validate_from_config()` 及自动提取函数，简化各表 `validate_xxx()` 方法 |
| `staging_models.py` | 简化 | 移除冗余定义，复用通用配置 |
| `staging_routers.py` | 简化 | 移除重复代码，复用统一配置 |
| `utils/duplicate_checker.py` | 优化 | 复用 `get_field_map()` 函数 |

### 10.8 后端开发检查清单更新

**v3.0新增检查项**：

- [ ] Schema定义完整（包含所有校验约束）
- [ ] `STAGING_TABLE_CONFIG` 配置正确
- [ ] 特殊业务规则已单独编写（如需要）
- [ ] `business_keys` 从proto_model自动提取
- [ ] 外键约束已在配置中声明

---

## 十一、v3.1版本更新详情

### 11.1 两阶段校验架构

**核心设计**：将校验分为两个独立阶段，提高用户体验和问题定位能力。

**阶段划分**：

| 阶段 | 校验内容 | 状态更新 | 说明 |
|------|----------|----------|------|
| **阶段1** | 合规性校验 | `compliance_pass` / `compliance_error` | 必填、枚举、范围、长度等不依赖外部数据的校验 |
| **阶段2** | 关联校验 | `relation_pass` / `relation_error` | 外键、重复检查等依赖外部数据的校验 |

**实现代码**：

```python
# staging_cleaner.py - StagingProcessor
async def process_staging(self, table_name: str, batch_size: int = 100, max_batches: int = 100):
    # 阶段1：合规性校验
    await self._validate_compliance(table_name, batch_size, max_batches)
    
    # 阶段2：关联校验（仅处理合规性通过的记录）
    await self._validate_relations(table_name, batch_size, max_batches)

# 阶段1实现
async def _validate_compliance(self, table_name, batch_size, max_batches):
    while batch_count < max_batches:
        query = f'SELECT * FROM "{table_name_staging}" WHERE "_status" = $1 LIMIT $2'
        result = await conn.execute_query(query, ("pending", batch_size))
        # 仅做合规性校验
        for record in pending_records:
            errors = await cleaner.validate_compliance(table_key, data, staging_id)
            status = StagingStatus.COMPLIANCE_PASS if not errors else StagingStatus.COMPLIANCE_ERROR
            # 更新状态和错误信息

# 阶段2实现
async def _validate_relations(self, table_name, batch_size, max_batches):
    while batch_count < max_batches:
        query = f'SELECT * FROM "{table_name_staging}" WHERE "_status" = $1 LIMIT $2'
        result = await conn.execute_query(query, ("compliance_pass", batch_size))
        # 仅做关联校验
        for record in pending_records:
            errors = await cleaner.validate_relations(table_key, data, staging_id)
            status = StagingStatus.RELATION_PASS if not errors else StagingStatus.RELATION_ERROR
            # 更新状态和错误信息
```

**DataCleaner接口新增**：

```python
# staging_cleaner.py
async def validate_compliance(self, table_key, data, staging_id):
    """阶段1：合规性校验（不依赖外部数据）"""
    errors = []
    config = STAGING_TABLE_CONFIG.get(table_key)
    schema_class = config["schema"]
    
    self.validate_required_from_schema(errors, staging_id, data, schema_class)
    self.validate_enums_from_schema(errors, staging_id, data, schema_class)
    self.validate_ranges_from_schema(errors, staging_id, data, schema_class)
    self.validate_max_lengths_from_schema(errors, staging_id, data, schema_class)
    
    return errors

async def validate_relations(self, table_key, data, staging_id):
    """阶段2：关联校验（依赖外部数据）"""
    errors = []
    
    await self.validate_foreign_keys_from_config(errors, staging_id, data, table_key)
    is_unique, dup_errors = await self.check_duplicate(table_key, data, staging_id)
    errors.extend(dup_errors)
    
    return errors
```

### 11.2 状态枚举扩展

**新增状态**：

```python
# _base.py
class StagingStatus(str, Enum):
    """缓冲表数据状态"""
    PENDING = "pending"
    COMPLIANCE_PASS = "compliance_pass"
    COMPLIANCE_ERROR = "compliance_error"
    RELATION_PASS = "relation_pass"
    RELATION_ERROR = "relation_error"
    APPROVED = "approved"
    SYNCED = "synced"
```

**状态流转图**：

```
pending
    ├─→ compliance_pass → relation_pass → approved → synced
    │                  └─→ relation_error
    └─→ compliance_error
```

### 11.3 校验规则文档化API

**新增API端点**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/mds/rules/{table_key}` | GET | 获取指定表的完整校验规则文档 |
| `/mds/rules/list` | GET | 获取所有表的校验规则列表 |

**API实现**：

```python
# staging_routers.py
@rt.get("/rules/{table_key}", summary="获取指定表的校验规则文档")
async def get_validation_rules(table_key: str):
    if table_key not in STAGING_TABLE_CONFIG:
        raise HTTPException(status_code=404, detail=f"Table {table_key} not found")
    
    config = STAGING_TABLE_CONFIG[table_key]
    rules_doc = generate_validation_rules_doc(table_key, config)
    return standard_response(data=rules_doc)

@rt.get("/rules/list", summary="获取所有表的校验规则列表")
async def list_validation_rules():
    rules_list = []
    for table_key, config in STAGING_TABLE_CONFIG.items():
        rules_doc = generate_validation_rules_doc(table_key, config)
        rules_list.append({
            "table_key": table_key,
            "display_name": config["display_name"],
            "rules": rules_doc
        })
    return standard_response(data=rules_list)
```

**规则文档结构**：

```python
# 返回数据结构示例
{
    "table_key": "t_material",
    "display_name": "物料表",
    "required_fields": [
        {"field": "materialno", "description": "物料号"},
        {"field": "description", "description": "物料描述"}
    ],
    "enum_fields": [
        {"field": "abc", "description": "ABC分类", "values": ["A", "B", "C"]}
    ],
    "range_fields": [
        {"field": "lotmin", "description": "最小批量", "ge": 0}
    ],
    "max_length_fields": [
        {"field": "materialno", "description": "物料号", "max_length": 20}
    ],
    "foreign_keys": [],
    "business_rules": [],
    "business_keys": ["materialno", "plant"]
}
```

### 11.4 前端通用组件库完善

**新增JS文件**：

| 文件 | 功能 |
|------|------|
| `common.js` | 通用工具函数、状态映射、API调用封装 |
| `form-renderer.js` | 表单渲染器 |
| `modal-manager.js` | 弹窗管理器 |

**状态映射（common.js）**：

```javascript
const STATUS_LABELS = {
    'pending': '待处理',
    'compliance_pass': '合规通过',
    'compliance_error': '合规错误',
    'relation_pass': '外键通过',
    'relation_error': '外键错误',
    'approved': '已审批',
    'synced': '已同步'
};

const STATUS_CLASSES = {
    'pending': 'bg-secondary',
    'compliance_pass': 'bg-info',
    'compliance_error': 'bg-danger',
    'relation_pass': 'bg-success',
    'relation_error': 'bg-warning',
    'approved': 'bg-primary',
    'synced': 'bg-secondary'
};
```

### 11.5 向后兼容性处理

**统计字段兼容**：

```python
# staging_routers.py
# 为响应添加兼容字段
stats["validated"] = stats.get("compliance_pass", 0) + stats.get("relation_pass", 0)
stats["rejected"] = stats.get("compliance_error", 0) + stats.get("relation_error", 0)
```

### 11.6 修改文件清单

| 文件 | 变更类型 | 核心改动 |
|------|----------|----------|
| `_base.py` | **新增** | 新增 `generate_validation_rules_doc()` 函数，状态枚举扩展 |
| `staging_cleaner.py` | **重构** | 两阶段校验实现，`validate_compliance()` 和 `validate_relations()` 拆分 |
| `staging_routers.py` | **新增** | 新增校验规则文档化API端点，向后兼容性处理 |
| `common.js` | **新增** | 通用工具函数、状态映射 |
| `form-renderer.js` | **新增** | 表单渲染器 |
| `modal-manager.js` | **新增** | 弹窗管理器 |
| `data-table.js` | 优化 | 数据表格组件 |
| `status-card.js` | 优化 | 状态卡片组件 |
| `custom.css` | 优化 | 自定义样式 |
| 各业务页HTML | 优化 | 统一更新，复用通用组件 |

---

## 十二、v3.2版本更新详情

### 12.1 前端架构重构概览

**核心设计理念**：所有表共用同一套代码，新增表只需编写配置文件。

**架构演进**：

| 阶段 | 实现方式 | 新增表成本 |
|------|----------|------------|
| v2.5- | 每个表单独编写JS + HTML | 数百行代码 |
| v3.0 | 配置驱动后端校验 | 数行配置 |
| v3.2 | 配置驱动前后端 | 仅需配置文件 |

### 12.2 配置文件设计

**新增配置目录**：`static/mds/configs/`

**配置文件结构**：

```javascript
// material.config.js
const MDS_PAGE_CONFIG = {
    tableKey: 't_material',
    tableDisplayName: '物料',
    
    display: {
        columns: [
            { field: '_status', title: '状态', width: '80px' },
            { field: '_createtime', title: '创建时间', width: '180px', sortable: true },
            { field: 'materialno', title: '物料号', width: '100px', sortable: true },
            { field: 'description', title: '物料描述', width: '150px' },
            // ... 更多字段
        ],
        defaultSortField: '_createtime',
        defaultSortDir: 'desc',
        
        advancedFilterCategories: {
            stringFields: [...],
            enumFields: [...],
            dateFields: [...]
        }
    },
    
    edit: {
        fields: [...]
    }
};
```

**配置文件清单**：

| 配置文件 | 对应表 |
|----------|--------|
| `material.config.js` | t_material |
| `workcenter.config.js` | t_workcenter |
| `mat-ver.config.js` | t_mat_ver |
| `mat-wc.config.js` | t_mat_wc |
| `mat-wc-bom.config.js` | t_mat_wc_bom |
| `mold.config.js` | t_mold |
| `mat-wc-mold.config.js` | t_mat_wc_mold |

### 12.3 通用页面控制器

**新增核心文件**：`mds-page-controller.js`（1219行）

**控制器架构**：

```javascript
class MDSPageController {
    constructor(config) {
        this.config = config;
        this.tableKey = config.tableKey;
        this.tableDisplayName = config.tableDisplayName;
        
        this.tableMeta = null;
        this.dataTable = null;
        this.statusCard = null;
        
        this.fieldValues = {};
        this.nullFields = new Set();
        
        this.init();
    }
    
    async init() {
        await this.loadTableMeta();
        this.initStatusCard();
        this.initDataTable();
        this.bindEvents();
    }
    
    // 从 /rules/{tableKey} API 加载校验规则元数据
    async loadTableMeta() {
        const response = await callApi(`/rules/${this.tableKey}`);
        if (response.success === 1) {
            this.tableMeta = response.data;
        }
    }
    
    // 动态获取字段信息（从API元数据或配置文件）
    getFieldLabel(fieldName) { ... }
    getFieldType(fieldName) { ... }
    getEnumOptions(fieldName) { ... }
    isRequiredField(fieldName) { ... }
    
    // 核心功能
    loadData() { ... }
    validateData() { ... }
    approveData() { ... }
    syncToProduction() { ... }
}
```

**核心特性**：

1. **元数据驱动**：从 `/rules/{tableKey}` API 动态加载字段信息、枚举选项、必填字段
2. **配置驱动**：表特定配置（列定义、排序、筛选等）完全外部化
3. **完整功能**：数据加载、校验、审批、同步、编辑、删除等所有功能通用化
4. **模板页面**：`template.html` 作为所有表的统一入口

### 12.4 页面模板化

**文件变更**：

| 变更 | 说明 |
|------|------|
| 重命名 | `material.html` → `template.html` |
| 删除 | mat-ver.html、mat-wc-bom.html、mat-wc-mold.html、mat-wc.html、mold.html、workcenter.html |

**模板页面使用**：

```html
<!-- template.html -->
<!DOCTYPE html>
<html>
<head>
    <title>MDS - {{config.tableDisplayName}}</title>
    <!-- 通用资源引用 -->
    <script src="../configs/{{tableKey}}.config.js"></script>
    <script src="../js/mds-page-controller.js"></script>
</head>
<body>
    <!-- 通用模板结构 -->
</body>
</html>
```

### 12.5 后端配合更新

**新增路由**：

```python
# routes_register.py
# 新增表的API路由注册
```

**全局常量更新**：

```python
# globalconst.py
# 表配置更新
```

### 12.6 新增表开发流程（v3.2版本）

**新增表只需3步**：

```
1. 后端：定义Schema + 配置 STAGING_TABLE_CONFIG
   ↓
2. 前端：编写 {tableKey}.config.js 配置文件
   ↓
3. 完成！
```

**对比v2.5版本**：

| 阶段 | v2.5及之前 | v3.2 |
|------|------------|------|
| 后端 | 100+行代码 | Schema + 配置 |
| 前端 | 500+行代码 | 仅配置文件 |
| 总计 | >600行代码 | <100行配置 |

### 12.7 修改文件清单

| 文件 | 变更类型 | 核心改动 |
|------|----------|----------|
| `_base.py` | 优化 | 配合前端重构 |
| `routes_register.py` | 优化 | 新增路由注册 |
| `globalconst.py` | 优化 | 全局常量更新 |
| `mds-page-controller.js` | **新增** | 通用页面控制器（1219行） |
| `material.config.js` | **新增** | 物料表配置 |
| `workcenter.config.js` | **新增** | 工作中心表配置 |
| `mat-ver.config.js` | **新增** | 产线版本表配置 |
| `mat-wc.config.js` | **新增** | 工艺路线表配置 |
| `mat-wc-bom.config.js` | **新增** | 物料清单表配置 |
| `mold.config.js` | **新增** | 模具表配置 |
| `mat-wc-mold.config.js` | **新增** | 机台模具关联表配置 |
| `material.js` | 优化 | 简化为配置驱动 |
| `template.html` | **重命名** | `material.html` → `template.html` |
| 5个旧页面文件 | **删除** | 不再需要单独的页面文件 |

---

## 十三、v3.3版本更新详情

### 13.1 配置自动生成器

**新增核心文件**：`config_generator.py`（396行）

**核心功能**：从后端 Schema 自动生成前端配置文件，实现"零配置"新增表。

**生成器架构**：

```python
# config_generator.py
def auto_generate_columns(schema_class) -> List[Dict[str, Any]]:
    """从 Schema 自动生成 columns 配置"""
    pass

def auto_generate_enum_fields(schema_class) -> List[Dict[str, Any]]:
    """从 Schema 自动生成 enumFields 配置"""
    pass

def auto_generate_string_fields(schema_class) -> List[Dict[str, str]]:
    """从 Schema 自动生成 stringFields 配置"""
    pass

def auto_generate_number_fields(schema_class) -> List[Dict[str, str]]:
    """从 Schema 自动生成 numberFields 配置"""
    pass

def auto_generate_date_fields(schema_class) -> List[Dict[str, str]]:
    """从 Schema 自动生成 dateFields 配置"""
    pass

def auto_generate_edit_fields(schema_class, staging_model) -> List[Dict[str, Any]]:
    """从 Schema 和模型自动生成 edit.fields 配置"""
    pass

def generate_full_config(table_key: str, schema_class, staging_model) -> Dict[str, Any]:
    """生成完整的配置对象"""
    return {
        'tableKey': table_key,
        'tableDisplayName': extract_display_name_from_model(staging_model),
        'display': {
            'columns': auto_generate_columns(schema_class),
            'defaultSortField': '_createtime',
            'defaultSortDir': 'desc',
            'advancedFilterCategories': {
                'stringFields': auto_generate_string_fields(schema_class),
                'enumFields': auto_generate_enum_fields(schema_class),
                'numberFields': auto_generate_number_fields(schema_class),
                'dateFields': auto_generate_date_fields(schema_class)
            }
        },
        'edit': {
            'fields': auto_generate_edit_fields(schema_class, staging_model)
        }
    }
```

**枚举选项智能提取**：

```python
def get_enum_options_from_schema(schema_class, field_name: str):
    """
    从 Schema 字段中获取枚举选项
    优先使用 Enum 类的 get_options() 方法
    """
    # 1. 尝试从 Enum.get_options() 获取
    # 2. fallback 到手动映射（用于 fifo 等特殊字段）
    pass

MANUAL_LABEL_MAPS = {
    "fifo": {
        "0": "最近原则",
        "1": "FIFO"
    }
}
```

### 13.2 架构演进对比

| 版本 | 新增表方式 | 工作量 |
|------|----------|--------|
| v2.5- | 手写后端 + 手写前端 | >600行代码 |
| v3.0-3.2 | Schema + 手写配置 | ~100行配置 |
| **v3.3** | Schema + 运行 `generate_config()` | **零配置** |

### 13.3 新增 Bootstrap 图标库

**新增资源**：

| 文件 | 说明 |
|------|------|
| `bootstrap-icons.css` | Bootstrap 图标样式（2078行） |
| `fonts/bootstrap-icons.woff` | 图标字体文件（176KB） |
| `fonts/bootstrap-icons.woff2` | 图标字体文件（130KB） |

**使用示例**：

```html
<i class="bi bi-search"></i>
<i class="bi bi-check-circle"></i>
<i class="bi bi-x-circle"></i>
```

### 13.4 配置文件删除

**变更**：删除7个手动编写的配置文件

| 删除文件 | 说明 |
|----------|------|
| `material.config.js` | 物料表配置（现在自动生成） |
| `workcenter.config.js` | 工作中心表配置（现在自动生成） |
| `mat-ver.config.js` | 产线版本表配置（现在自动生成） |
| `mat-wc.config.js` | 工艺路线表配置（现在自动生成） |
| `mat-wc-bom.config.js` | 物料清单表配置（现在自动生成） |
| `mold.config.js` | 模具表配置（现在自动生成） |
| `mat-wc-mold.config.js` | 机台模具关联表配置（现在自动生成） |

**原因**：配置现在从 Schema 自动生成，不再需要手动维护。

### 13.5 新增表开发流程（v3.3最终版）

**新增表只需2步**：

```
1. 后端：定义 Schema + 配置 STAGING_TABLE_CONFIG
   ↓
2. 运行：调用 generate_full_config() 自动生成前端配置
   ↓
3. 完成！
```

### 13.6 Excel 导入功能增强

**新增资源**：

| 文件 | 说明 |
|------|------|
| `xlsx.full.min.js` | SheetJS 库（用于前端 Excel 解析） |

**后端配合**：

| 文件 | 变更 | 说明 |
|------|------|------|
| `excel_parser.py` | ±159行 | Excel 解析器优化 |
| `duplicate_checker.py` | ±14行 | 重复检查器优化 |

**新增 API**：

```python
@rt.get("/dblist", summary="获取账套列表")
async def get_db_list():
    """获取可用的账套列表"""
    return standard_response(
        success=1,
        message="查询成功",
        data=MYAPS_DBSET_LIST
    )
```

### 13.7 架构清理完成

**重要里程碑**：删除 `material.js`（1217行）

**变更**：

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `material.js` | **删除** | 不再需要单个表脚本 |

**意义**：完全采用通用控制器架构，所有表共用同一套代码。

### 13.8 组件优化

**大幅优化的文件**：

| 文件 | 变更 | 说明 |
|------|------|------|
| `data-table.js` | +293行 | 数据表格组件大幅优化 |
| `mds-page-controller.js` | ±98行 | 通用控制器完善 |
| `common.js` | ±63行 | 通用工具函数优化 |
| `custom.css` | +35行 | 自定义样式新增 |
| `status-card.js` | ±8行 | 状态卡片组件优化 |
| `template.html` | ±30行 | 模板页面优化 |

### 13.9 修改文件清单（完整版）

**第一波（v3.3初始）**：

| 文件 | 变更类型 | 核心改动 |
|------|----------|----------|
| `config_generator.py` | **新增** | 配置自动生成器（396行） |
| `routes_register.py` | 优化 | 路由更新 |
| 7个配置文件 | **删除** | 不再需要手动配置 |
| `bootstrap-icons.css` | **新增** | Bootstrap 图标样式 |
| `fonts/bootstrap-icons.woff` | **新增** | 图标字体 |
| `fonts/bootstrap-icons.woff2` | **新增** | 图标字体 |
| `data-table.js` | 优化 | 配合图标库 |
| `mds-page-controller.js` | 优化 | 配合配置自动生成 |
| `template.html` | 优化 | 图标库集成 |

**第二波（v3.3完善）**：

| 文件 | 变更类型 | 核心改动 |
|------|----------|----------|
| `staging_routers.py` | 优化 | 新增 /dblist API |
| `config_generator.py` | 优化 | 配置生成器优化 |
| `duplicate_checker.py` | 优化 | 重复检查器优化 |
| `excel_parser.py` | 优化 | Excel 解析器优化 |
| `dev_server.bat/sh` | 优化 | 开发服务器脚本更新 |
| `xlsx.full.min.js` | **新增** | Excel 解析库 |
| `data-table.js` | **优化** | +293行大幅改进 |
| `mds-page-controller.js` | 优化 | 通用控制器完善 |
| `common.js` | 优化 | 通用工具函数优化 |
| `custom.css` | 优化 | 自定义样式新增 |
| `status-card.js` | 优化 | 状态卡片组件优化 |
| `template.html` | 优化 | 模板页面优化 |
| `material.js` | **删除** | 完全转向通用控制器（1217行） |

---

## 十四、v2.3版本更新详情

### 9.1 校验错误详情展示

**列表中错误字段高亮**：

```javascript
// data-table.js - renderCell方法
const errorInfo = errorMap[col.field];
if (errorInfo) {
    return `<span class="error-cell" data-error-type="${errorInfo.type}" 
                 data-error-msg="${errorInfo.message}">${value}</span>`;
}
```

**悬停显示错误信息**：

```javascript
bindTooltip() {
    document.querySelectorAll('.error-cell').forEach(cell => {
        cell.addEventListener('mouseenter', (e) => {
            // 显示错误类型和错误信息
        });
    });
}
```

**状态单元格显示完整错误JSON**：

- 悬停"校验失败"状态
- 显示所有错误（包括无法指向具体字段的错误）
- 支持多条错误分隔显示

### 9.2 datetime时区问题修复

**问题1：ValidationError.createtime**

```python
# 之前
createtime = fields.DatetimeField(auto_now_add=True)

# 现在
createtime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc))
```

**问题2：check_duplicate使用ORM查询**

```python
# 之前（ORM查询，有时区问题）
query = staging_model.filter(**conditions)
count = await query.count()

# 现在（原生SQL）
query = f'SELECT COUNT(*) as cnt FROM "{table_name_staging}" WHERE ...'
result = await conn.execute_query(query, tuple(params))
count = result[1][0]["cnt"]
```

**问题3：读取记录时datetime无时区**

```python
for python_field, db_field in field_map.items():
    value = record_dict.get(db_field)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
```

### 9.3 枚举字段标签样式

**实现效果**：枚举字段值以圆边矩形标签显示。

**前端配置**：

```javascript
// material.js
dataTable = new DataTable({
    enumFields: Object.keys(ENUM_OPTIONS)  // ['abc', 'fifo', 'type', 'phantom', ...]
});
```

**样式定义**：

```css
.enum-tag {
    display: inline-block;
    background-color: #c9e6fc;
    border-radius: 4px;
    padding: 0.1rem 0.4rem;
    color: #0066cc;
}

.enum-tag-error {
    background-color: #ffcccc;
    color: #cc0000;
}
```

### 9.4 校验进度条动画

**实现效果**：
- 实时显示校验进度
- 平滑动画过渡
- API等待时流动动画

**进度条函数**：

```javascript
// common.js
function showProgress(title, total)      // 显示进度条
function updateProgress(current, total)  // 更新进度
function setProgressIndeterminate(bool)  // 设置流动动画
function hideProgress()                  // 隐藏进度条
```

**校验逻辑优化**：

```javascript
// material.js
async function validateData() {
    while (true) {
        setProgressIndeterminate(true);  // API请求时流动动画
        const response = await callApi(`/validate/${TABLE_NAME}?batch_size=200`, 'POST');
        setProgressIndeterminate(false);
        
        // 平滑动画过渡（10步，每步30ms）
        await animateProgress(processed, processed + batchProcessed, pendingCount);
        processed += batchProcessed;
        
        await sleep(50);  // 批次间延迟
    }
}

async function animateProgress(from, to, total) {
    const steps = 10;
    const stepSize = (to - from) / steps;
    for (let i = 1; i <= steps; i++) {
        updateProgress(Math.round(from + stepSize * i), total);
        await sleep(30);
    }
}
```

**流动动画CSS**：

```css
.progress-bar-indeterminate {
    background: linear-gradient(90deg, transparent 0%, #0d6efd 20%, #0dcaf0 40%, #0d6efd 60%, transparent 100%);
    background-size: 200% 100%;
    animation: progress-indeterminate 1.5s linear infinite;
}

@keyframes progress-indeterminate {
    0% { background-position: 100% 0; }
    100% { background-position: -100% 0; }
}
```

### 9.5 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `apps/data_opt/staging_models.py` | ValidationError.createtime时区修复 |
| `apps/data_opt/staging_cleaner.py` | check_duplicate改原生SQL、异常捕获增强、日志输出 |
| `static/mds/js/data-table.js` | 错误字段高亮、枚举标签、悬停提示、parseErrorFields方法 |
| `static/mds/js/material.js` | 进度条动画、enumFields配置、animateProgress方法 |
| `static/mds/js/common.js` | 进度条函数、不确定进度模式 |
| `static/mds/css/custom.css` | 枚举标签样式、错误单元格样式、进度条动画样式 |

---

## 九、v2.2版本更新详情

### 9.1 单条编辑空字符串处理

**问题**：前端传空字符串，后端未处理，导致整型字段解析失败。

**修复**：后端 `update_staging` 方法，空字符串自动转为NULL。

```python
# staging_routers.py
for key, value in data.items():
    if key not in exclude_fields:
        db_col = field_map.get(key, key)
        if value is None or value == '':
            set_parts.append(f'"{db_col}" = NULL')
        else:
            set_parts.append(f'"{db_col}" = ${param_idx}')
            values.append(value)
```

### 9.2 必填字段清空校验

**问题**：批量编辑时可清空必填字段，导致违反NOT NULL约束。

**修复**：前端增加 `REQUIRED_FIELDS` 配置，清空前校验。

```javascript
// material.js
const REQUIRED_FIELDS = ['materialno', 'description', 'plant', 'leadday', 'grday', 'abc', 'unit', 'groupno'];

// 清空前校验
if (REQUIRED_FIELDS.includes(field)) {
    showMessage('该字段是必填字段，不能清空', 'warning');
    return;
}
```

**编辑弹窗必填标记**：

```javascript
function generateEditField(col, row) {
    const isRequired = REQUIRED_FIELDS.includes(fieldName);
    const labelHtml = `<label>${col.title}${isRequired ? '<span class="text-danger">*</span>' : ''}</label>`;
    // ...
}
```

### 9.3 校验循环处理所有记录

**问题**：`batch_size` 限制，每次只处理100条，剩余pending记录不处理。

**修复**：改为while循环 + 原生SQL查询，直到没有pending记录。

```python
async def process_staging(self, table_name: str, batch_size: int = 100, max_batches: int = 100):
    batch_count = 0
    while batch_count < max_batches:
        # 原生SQL查询（避免ORM缓存问题）
        query = f'SELECT * FROM "{table_name_staging}" WHERE "_status" = $1 LIMIT $2'
        result = await conn.execute_query(query, ("pending", batch_size))
        pending_records = result[1] if result[1] else []
        
        if not pending_records:
            break
        
        batch_count += 1
        
        for raw_record in pending_records:
            # 处理单条记录...
```

**新增参数**：
- `max_batches`：最大批次数（默认100），防止无限循环

### 9.4 枚举校验完善

**问题**：部分枚举字段未校验，如 `abc`、`fifo`。

**修复**：补充完整枚举校验。

```python
class DataCleaner:
    ABC_ENUM = {"A", "B", "C"}
    FIFO_ENUM = {0, 1, "0", "1"}
    MATERIAL_TYPE_ENUM = {"E", "P", "F", "M", "B"}
    YES_NO_ENUM = {"Y", "N"}
    LOT_SIZE_ENUM = {"EX", "FX", "D1", "D2", "D3", "D4", "D5", "D6", "W1", "W2", "W3", "W4", "M1", "M2", "VB"}

async def validate_material(self, data, staging_id):
    # ABC分类校验
    if data.get("abc") and str(data["abc"]) not in self.ABC_ENUM:
        errors.append(...)
    
    # FIFO校验
    if data.get("fifo") is not None and str(data["fifo"]) not in {"0", "1"}:
        errors.append(...)
```

**物料表完整枚举校验清单**：

| 字段 | 枚举值 | 说明 |
|------|--------|------|
| abc | A, B, C | ABC分类 |
| fifo | 0, 1 | FIFO标识 |
| type | E, P, F, M, B | 物料类型 |
| phantom | Y, N | 虚拟件标识 |
| candelay | Y, N | 可否延迟 |
| lotsize | EX, FX, VB, D1-D6, W1-W4, M1-M2 | 批量策略 |

### 9.5 编辑后状态重置

**问题**：编辑validated记录后状态仍为validated，可跳过校验直接同步。

**修复**：编辑后状态重置为pending，清空错误信息。

**单条更新**：

```python
# staging_routers.py - update_staging
set_parts.append('"_status" = $' + str(param_idx))
values.append('pending')
set_parts.append('"_error_msg" = NULL')
```

**批量更新**：

```python
# staging_routers.py - batch_update_staging
UPDATE "{table_name_staging}"
SET ..., "_updatetime" = NOW(), "_status" = 'pending', "_error_msg" = NULL
WHERE "_staging_id" = ANY(${param_idx})
```

**编辑后行为**：

| 原状态 | 编辑后状态 | 说明 |
|--------|-----------|------|
| pending | pending | 无变化 |
| validated | pending | 需重新校验 |
| rejected | pending | 清空错误，重新校验 |
| synced | pending | 需重新校验 |

### 9.6 校验异常捕获

**修复**：单条记录处理异常时，标记为rejected并记录错误信息，继续处理其他记录。

```python
for raw_record in pending_records:
    try:
        # 处理单条记录...
    except Exception as e:
        logger.error(f"处理记录失败: {str(e)}")
        error_json = json.dumps([{
            "error_type": "process_error",
            "error_message": f"处理异常: {str(e)}"
        }])
        # 标记为rejected
        await conn.execute_query(update_query, ("rejected", error_json, staging_id))
        stats["rejected"] += 1
```

### 9.7 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `apps/data_opt/staging_routers.py` | 空字符串转NULL、状态重置 |
| `apps/data_opt/staging_cleaner.py` | 循环处理、枚举校验、异常捕获、日志输出 |
| `static/mds/js/material.js` | REQUIRED_FIELDS、必填标记、清空校验 |
