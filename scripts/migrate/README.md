# Monitor Models 迁移工具

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `migrate_all_in_one.bat` | ✨ **唯一需要运行的脚本** |
| `migrate_with_tortoise.py` | Python 脚本（被 bat 调用） |
| `monitor_orm_config.py` | ORM 配置 |
| `README.md` | 本说明文件 |

---

## 🚀 使用方法

**只需要运行一个文件：**
```
scripts/migrate/migrate_all_in_one.bat
```

---

## 📋 菜单选项

| 选项 | 功能 | 推荐使用场景 |
|------|------|--------------|
| **[1]** | 使用 Tortoise 直接生成表 | ✅ **日常新增/更新模型（最可靠）** |
| **[2]** | 使用 Aerich 迁移系统 | 需要版本回滚时 |
| **[3]** | 重置所有迁移 | aerich 出问题时 |
| **[Q]** | 退出 | - |

---

## 🎯 日常流程

### 新增/更新模型
1. 在 `apps/common/monitor/models.py` 中添加/修改模型
2. 运行 `migrate_all_in_one.bat`
3. 选择 **[1]**
4. 完成！✅

---

## 💡 推荐

**日常开发请优先使用 [1] Tortoise 方案** - 更简单、更可靠！
