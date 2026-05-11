# 开发环境服务管理脚本

## 脚本说明

| 脚本 | 适用系统 | 说明 |
|------|---------|------|
| `dev_server.sh` | Linux/macOS | Bash脚本 |
| `dev_server.bat` | Windows | 批处理脚本 |

## 使用方法

### Linux/macOS

```bash
# 进入项目目录
cd /opt/myaps_api/myaps_api

# 添加执行权限（首次使用）
chmod +x scripts/dev_server.sh

# 启动服务
./scripts/dev_server.sh start

# 查看状态
./scripts/dev_server.sh status

# 查看日志
./scripts/dev_server.sh logs

# 实时查看日志
./scripts/dev_server.sh logs -f

# 重启服务
./scripts/dev_server.sh restart

# 停止服务
./scripts/dev_server.sh stop
```

### Windows

```cmd
# 进入项目目录
cd D:\myaps_api\myaps_api

# 启动服务
scripts\dev_server.bat start

# 查看状态
scripts\dev_server.bat status

# 重启服务
scripts\dev_server.bat restart

# 停止服务
scripts\dev_server.bat stop
```

## 访问地址

启动成功后访问：

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | 服务首页 |
| http://localhost:8000/docs | Swagger API文档 |
| http://localhost:8000/redoc | ReDoc API文档 |

## 测试MDS路由

在Swagger文档中测试数据清洗API：

1. **接收物料数据到缓冲表**
   ```
   POST /api/mds/material
   ```
   
2. **查询缓冲表状态**
   ```
   GET /api/mds/status/t_material
   ```

3. **校验缓冲表数据**
   ```
   POST /api/mds/validate/t_material
   ```

4. **同步到正式表**
   ```
   POST /api/mds/sync/t_material
   ```

## 日志位置

- Linux/macOS: `logs/dev_server.log`
- Windows: 控制台窗口输出
