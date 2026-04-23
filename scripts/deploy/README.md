# 部署脚本使用说明

## 1. 环境准备

1. **安装 Python 3.9+**
2. **安装依赖**：
   ```bash
   # 安装 gunicorn
   pip install gunicorn
   
   # 安装项目依赖
   pip install -r requirements.txt
   ```
3. **安装 Nginx**：
   - 下载 Nginx for Windows
   - 解压到合适位置（如 `C:\nginx`）

## 2. 配置文件

### 2.1 Gunicorn 配置
- `gunicorn.conf.py`：Gunicorn 进程管理器配置

### 2.2 Binlog 监听器
- `binlog_listener_service.py`：Binlog 监听器单进程控制

### 2.3 环境变量
- `.env.example`：环境变量配置示例
  - 复制为 `.env` 并填写实际配置

## 3. 启动脚本

### 3.1 启动监听器
```bash
# 运行监听器
start_listener.bat
```

### 3.2 启动应用
```bash
# 运行应用
start_app.bat
```

### 3.3 启动所有服务
```bash
# 运行所有服务
start_all.bat
```

## 4. 部署流程

### 4.1 首次部署
1. 准备环境（安装 Python、Nginx、依赖）
2. 配置 `.env` 文件
3. 启动 Nginx 服务
4. 运行 `start_all.bat` 脚本
5. 访问 `http://localhost` 验证部署

### 4.2 升级部署
1. 停止 Nginx 服务
2. 停止应用进程和 binlog 监听器
3. 更新代码
4. 运行 `start_all.bat` 脚本
5. 启动 Nginx 服务
6. 验证升级

## 5. 注意事项

- 确保脚本以管理员权限运行
- 生产环境中修改默认密码
- 根据服务器配置调整 `gunicorn.conf.py` 中的 `workers` 参数
- 定期检查日志文件

## 6. 故障排查

- 检查端口占用：`netstat -ano | findstr :8000`
- 查看进程：`tasklist | findstr python`
- 终止进程：`taskkill /PID <进程ID> /F`
- 查看日志：`logs/access.log` 和 `logs/error.log`