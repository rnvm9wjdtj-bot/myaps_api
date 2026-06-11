# Windows 离线迁移工具

本目录包含将 MyAPS API 项目迁移到无外网访问的 Windows 环境所需的所有工具和文档。

## 目录结构

```
to_windows/
├── README.md              # 本文件
├── docs/                  # 文档
│   ├── README.md          # 完整迁移手册
│   ├── CHECKLIST.md       # 迁移检查清单
│   ├── GUI_README.md      # GUI 工具说明
│   └── QUICKSTART.md      # 快速开始指南
├── scripts/               # 脚本工具
│   ├── download_packages.sh    # Linux/macOS 下载脚本
│   ├── download_packages.ps1   # Windows PowerShell 下载脚本
│   ├── install_packages.bat    # 内网安装脚本
│   └── setup_env.bat           # 环境配置向导
├── gui/                   # 可视化工具
│   ├── __init__.py
│   ├── main.py            # GUI 主程序
│   ├── run_gui.bat        # Windows 启动脚本
│   └── run_gui.sh         # Linux/macOS 启动脚本
├── tools/                 # Windows 工具软件
│   ├── _python-3.12.2.exe           # Python 安装包
│   ├── postgresql-18.3-3-windows-x64.exe  # PostgreSQL
│   ├── Redis-x64-5.0.14.1.msi       # Redis
│   ├── dbeaver-ce-26.1.0-windows-x86_64.exe  # DBeaver 数据库工具
│   ├── SQLark_V3.10_Win_x86_64.zip  # SQLark 数据库工具
│   ├── npp.8.9.6.4.Installer.exe    # Notepad++ 编辑器
│   └── Trae_CN-Setup-x64.exe        # Trae 编辑器
└── packages/              # Python 离线依赖包
    ├── *.whl              # Windows wheel 包
    ├── *.tar.gz           # 源码包
    └── MANIFEST.txt       # 包清单
```

## 使用流程

### 第一阶段：外网机器准备

1. **下载依赖包**（在外网机器执行）：
   ```bash
   # Linux/macOS
   bash scripts/download_packages.sh
   
   # Windows PowerShell
   .\scripts\download_packages.ps1
   ```

2. **启动 GUI 工具**（可选）：
   ```bash
   # Linux/macOS
   bash gui/run_gui.sh
   
   # Windows
   gui\run_gui.bat
   ```

### 第二阶段：内网 Windows 部署

1. **安装 Python**：
   运行 `tools/_python-3.12.2.exe`

2. **安装依赖**：
   ```cmd
   scripts\install_packages.bat
   ```

3. **配置环境**：
   ```cmd
   scripts\setup_env.bat
   ```

## 详细文档

- 完整迁移手册：`docs/README.md`
- GUI 工具说明：`docs/GUI_README.md`
- 快速开始：`docs/QUICKSTART.md`
- 检查清单：`docs/CHECKLIST.md`