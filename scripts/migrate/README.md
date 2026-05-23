# Monitor Models 迁移工具

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `migrate_all_in_one.bat` / `.sh` | ✨ **唯一需要运行的脚本** |
| `auto_migrate.py` | 自动迁移脚本 |
| `migrate_with_tortoise.py` | Tortoise 表创建脚本 |
| `add_log_query_indexes.py` | 日志查询索引优化脚本 |
| `monitor_orm_config.py` | ORM 配置 |
| `README.md` | 本说明文件 |

---

## 🚀 使用方法

**只需要运行一个文件：**

**Windows:**
```
scripts\migrate\migrate_all_in_one.bat
```

**Linux:**
```
./scripts/migrate/migrate_all_in_one.sh
```

---

## 📋 菜单选项

| 选项 | 功能 | 推荐使用场景 |
|------|------|--------------|
| **[1]** | Auto Migration（自动迁移） | ✅ **日常新增/更新模型（推荐）** |
| **[2]** | Create tables with Tortoise | 仅创建新表 |
| **[3]** | Reset migrations | 重置所有迁移 |
| **[4]** | Add log query indexes | ✅ **优化日志查询性能** |
| **[5]** | Backup only | 仅备份数据库 |
| **[Q]** | 退出 | - |

---

## 🎯 日常流程

### 新增/更新模型
1. 在 `apps/common/monitor/models.py` 中添加/修改模型
2. 运行迁移脚本
3. 选择 **[1]**
4. 完成！✅

### 优化日志查询性能
1. 运行迁移脚本
2. 选择 **[4]**
3. 自动创建索引（client_ip, method, timestamp, level 等）
4. 完成！✅

---

## 💡 推荐

**日常开发请优先使用 [1] Auto Migration** - 自动备份、更简单、更可靠！
