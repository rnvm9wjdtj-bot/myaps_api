# Linux 离线迁移工具

本目录包含将 MyAPS API 项目迁移到无外网访问的 Linux 环境所需的所有工具和文档。

## 目录结构

```
to_linux/
├── README.md              # 本文件
├── docs/                  # 文档（待补充）
├── scripts/               # 脚本工具
│   ├── download_packages.sh    # 外网机器下载脚本
│   ├── install_packages.sh     # 内网安装脚本
│   └── setup_env.sh           # 环境配置向导
├── gui/                   # 可视化工具
│   ├── __init__.py
│   ├── main.py            # GUI 主程序
│   └── run_gui.sh         # 启动脚本
├── tools/                 # Linux 工具软件（需自行准备）
│   ├── python-3.12.x.tar.xz     # Python 源码包
│   ├── postgresql-*.tar.gz      # PostgreSQL
│   ├── redis-*.tar.gz           # Redis
│   └── ...
└── packages/              # Python 离线依赖包
    ├── *.whl              # Linux wheel 包
    ├── *.tar.gz           # 源码包
    └── MANIFEST.txt       # 包清单
```

## 使用流程

### 第一阶段：外网机器准备

1. **下载依赖包**（在外网机器执行）：
   ```bash
   # Linux/macOS
   bash scripts/download_packages.sh
   
   # 使用国内镜像加速
   INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ bash scripts/download_packages.sh
   ```

2. **启动 GUI 工具**（可选）：
   ```bash
   bash gui/run_gui.sh
   ```

### 第二阶段：内网 Linux 部署

1. **安装 Python**（如未安装）：
   ```bash
   # 解压并编译安装
   tar -xJf tools/Python-3.12.x.tar.xz
   cd Python-3.12.x
   ./configure --prefix=/usr/local/python3.12
   make && sudo make install
   ```

2. **安装依赖**：
   ```bash
   bash scripts/install_packages.sh
   ```

3. **配置环境**：
   ```bash
   bash scripts/setup_env.sh
   ```

4. **启动服务**：
   ```bash
   # 开发模式
   source venv/bin/activate
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   
   # 或使用项目脚本
   ./scripts/dev_server.sh start
   ```

## 与 Windows 版本的主要差异

| 项目 | Windows | Linux |
|------|---------|-------|
| 目标平台 | `win_amd64` | `manylinux2014_x86_64` |
| 安装脚本 | `install_packages.bat` | `install_packages.sh` |
| 配置脚本 | `setup_env.bat` | `setup_env.sh` |
| 虚拟环境路径 | `venv\Scripts\python.exe` | `venv/bin/python` |
| 工具软件 | `.exe`, `.msi` | `.tar.gz`, `.tar.xz` |

## 常见问题

### 1. 编译依赖缺失

某些 Python 包需要编译环境：

```bash
# CentOS/RHEL
sudo yum install gcc make python3-devel postgresql-devel

# Ubuntu/Debian
sudo apt-get install build-essential python3-dev libpq-dev
```

### 2. 权限问题

```bash
# 确保目录可写
chmod -R 755 logs/ storage/
```

### 3. 服务无法启动

检查端口占用：
```bash
lsof -i :8000
netstat -tunlp | grep 8000
```

## 详细文档

- 完整迁移手册：`docs/README.md`（待补充）
- 检查清单：`docs/CHECKLIST.md`（待补充）