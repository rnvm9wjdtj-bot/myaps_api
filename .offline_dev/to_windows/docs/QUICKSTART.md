# MyAPS API - 离线迁移快速开始

> 本文档为快速参考，详细步骤请参见 [README.md](README.md)

---

## 外网机器（5分钟）

```bash
# 1. 进入项目目录
cd /path/to/myaps_api

# 2. 下载离线依赖包
bash .offline_dev/scripts/download_packages.sh

# 3. 打包整个项目
tar -czf myaps_api_offline.tar.gz myaps_api/

# 4. 传输到内网（U盘/光盘/网闸）
```

---

## 内网 Windows 机器（10分钟）

```cmd
:: 1. 解压项目到 D:\myaps_api

:: 2. 安装依赖（自动）
cd D:\myaps_api
.offline_dev\scripts\install_packages.bat

:: 3. 配置环境变量
copy .env.example .env
:: 编辑 .env，修改数据库连接信息

:: 4. 启动服务
scripts\dev_server.bat start

:: 5. 验证
:: 浏览器访问 http://localhost:8000/docs
```

---

## 一键命令汇总

### 外网 - 下载依赖

```bash
bash ..offline_dev/scripts/download_packages.sh
```

### 内网 - 完整部署

```cmd
.offline_dev\scripts\install_packages.bat && copy .env.example .env && scripts\dev_server.bat start
```

### 内网 - 手动部署

```cmd
:: 创建虚拟环境
python -m venv venv

:: 激活环境
venv\Scripts\activate.bat

:: 安装依赖
pip install --no-index --find-links=.offline_dev/packages -r requirements.txt

:: 启动服务
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 常见问题速查

| 问题 | 解决 |
|------|------|
| 端口占用 | `netstat -ano \| findstr :8000` 然后 `taskkill /F /PID <PID>` |
| 依赖缺失 | 确认 Python 版本与打包时一致 |
| 数据库连不上 | 检查 `.env` 配置和防火墙 |
| 中文乱码 | `chcp 65001` |
| 服务起不来 | 查看 `logs/` 目录错误日志 |

---

**详细文档**: [README.md](README.md)  
**检查清单**: [CHECKLIST.md](CHECKLIST.md)
