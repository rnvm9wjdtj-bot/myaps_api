#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyAPS API - 离线迁移可视化工具 (Linux版本)
提供依赖下载、安装、环境配置、服务管理等功能
"""

import os
import sys
import subprocess
import threading
import queue

# macOS specific: suppress IMK CFRunLoop warning
if sys.platform == "darwin":
    os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path


class OfflineMigrationTool:
    """离线迁移工具主类"""

    def __init__(self, root):
        self.root = root
        self.root.title("MyAPS API 离线迁移工具 (Linux)")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        self.project_root = Path(__file__).parent.parent.parent.parent
        self.log_queue = queue.Queue()

        self.setup_ui()
        self.check_python()

    def setup_ui(self):
        """设置界面"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_download = tk.Frame(self.notebook)
        self.tab_install = tk.Frame(self.notebook)
        self.tab_config = tk.Frame(self.notebook)
        self.tab_service = tk.Frame(self.notebook)

        self.notebook.add(self.tab_download, text="1. 下载依赖包")
        self.notebook.add(self.tab_install, text="2. 安装依赖包")
        self.notebook.add(self.tab_config, text="3. 环境配置")
        self.notebook.add(self.tab_service, text="4. 服务管理")

        self.setup_download_tab()
        self.setup_install_tab()
        self.setup_config_tab()
        self.setup_service_tab()

        self.log_text = scrolledtext.ScrolledText(self.root, height=10, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("warning", foreground="orange")

        self.log("欢迎使用 MyAPS API 离线迁移工具 (Linux版)！")
        self.log("请根据您的网络环境选择相应的标签页：")
        self.log("- 有外网环境：使用 '1. 下载依赖包'")
        self.log("- 无外网环境：使用 '2-4' 标签页")

    def log(self, message, level="info"):
        """输出日志"""
        self.log_text.insert(tk.END, message + "\n", level)
        self.log_text.see(tk.END)
        self.root.update()

    def check_python(self):
        """检查Python环境"""
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            self.log(f"Python 版本: {result.stdout.strip()}", "success")
        except Exception as e:
            self.log(f"Python 检查失败: {e}", "error")

    def setup_download_tab(self):
        """设置下载依赖标签页"""
        frame = tk.Frame(self.tab_download)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(frame, text="依赖包下载（有外网环境）", font=("Arial", 14, "bold")).pack(pady=(0, 20))

        form_frame = tk.Frame(frame)
        form_frame.pack(fill=tk.X, pady=10)

        tk.Label(form_frame, text="项目根目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_project_root = tk.Entry(form_frame, width=50)
        self.entry_project_root.insert(0, str(self.project_root))
        self.entry_project_root.grid(row=0, column=1, sticky=tk.EW, pady=5)
        tk.Button(form_frame, text="浏览...", command=self.browse_project_root).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(form_frame, text="Python 版本:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.combo_python_version = ttk.Combobox(form_frame, values=["3.11", "3.12"], state="readonly", width=47)
        self.combo_python_version.set("3.12")
        self.combo_python_version.grid(row=1, column=1, sticky=tk.EW, pady=5)

        tk.Label(form_frame, text="目标平台:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.combo_platform = ttk.Combobox(form_frame, values=["manylinux2014_x86_64", "manylinux_2_17_x86_64", "linux_x86_64"], state="readonly", width=47)
        self.combo_platform.set("manylinux2014_x86_64")
        self.combo_platform.grid(row=2, column=1, sticky=tk.EW, pady=5)

        tk.Label(form_frame, text="下载源:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.combo_mirror = ttk.Combobox(form_frame, values=["PyPI官方", "阿里云镜像", "清华镜像"], state="readonly", width=47)
        self.combo_mirror.set("PyPI官方")
        self.combo_mirror.grid(row=3, column=1, sticky=tk.EW, pady=5)

        tk.Label(form_frame, text="输出目录:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.entry_output_dir = tk.Entry(form_frame, width=50)
        self.entry_output_dir.insert(0, str(self.project_root / ".offline_dev" / "to_linux" / "packages"))
        self.entry_output_dir.grid(row=4, column=1, sticky=tk.EW, pady=5)
        tk.Button(form_frame, text="浏览...", command=self.browse_output_dir).grid(row=4, column=2, padx=5, pady=5)

        form_frame.columnconfigure(1, weight=1)

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=20)
        self.btn_download = tk.Button(btn_frame, text="开始下载", command=self.start_download, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), padx=30, pady=10)
        self.btn_download.pack()

        tk.Label(frame, text="说明：此功能需要外网访问。如果遇到SSL证书错误，请选择国内镜像源。下载完成后，请将整个项目目录传输到内网。", fg="gray").pack(pady=10)

    def browse_project_root(self):
        dir_path = filedialog.askdirectory(initialdir=self.entry_project_root.get())
        if dir_path:
            self.entry_project_root.delete(0, tk.END)
            self.entry_project_root.insert(0, dir_path)

    def browse_output_dir(self):
        dir_path = filedialog.askdirectory(initialdir=self.entry_output_dir.get())
        if dir_path:
            self.entry_output_dir.delete(0, tk.END)
            self.entry_output_dir.insert(0, dir_path)

    def start_download(self):
        """开始下载"""
        self.btn_download.config(state=tk.DISABLED, text="下载中...")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        """下载工作线程"""
        try:
            project_root = Path(self.entry_project_root.get())
            output_dir = Path(self.entry_output_dir.get())
            python_version = self.combo_python_version.get()
            platform = self.combo_platform.get()
            mirror = self.combo_mirror.get()

            self.log("=" * 50)
            self.log("开始下载依赖包...")
            self.log(f"项目根目录: {project_root}")
            self.log(f"输出目录: {output_dir}")
            self.log(f"Python 版本: {python_version}")
            self.log(f"目标平台: {platform}")
            self.log(f"下载源: {mirror}")

            # 配置镜像源
            index_url = None
            trusted_host = None
            
            if mirror == "阿里云镜像":
                index_url = "https://mirrors.aliyun.com/pypi/simple/"
                trusted_host = "mirrors.aliyun.com"
                self.log("使用阿里云镜像加速下载", "success")
            elif mirror == "清华镜像":
                index_url = "https://pypi.tuna.tsinghua.edu.cn/simple"
                trusted_host = "pypi.tuna.tsinghua.edu.cn"
                self.log("使用清华镜像加速下载", "success")
            else:
                self.log("使用 PyPI 官方源下载", "info")

            output_dir.mkdir(parents=True, exist_ok=True)

            req_file = project_root / "requirements.txt"
            if not req_file.exists():
                self.log(f"错误: 找不到 requirements.txt 文件: {req_file}", "error")
                return

            self.log("第一步: 下载预编译包 (wheel)", "info")
            cmd1 = [
                sys.executable, "-m", "pip", "download",
                "--requirement", str(req_file),
                "--dest", str(output_dir),
                "--only-binary", ":all:",
                "--python-version", python_version,
                "--platform", platform,
                "--no-deps"
            ]
            
            # 添加镜像源参数
            if index_url:
                cmd1.extend(["--index-url", index_url, "--trusted-host", trusted_host])
            
            self._run_command(cmd1, output_dir)

            self.log("\n第二步: 下载源码包 (source)", "info")
            cmd2 = [
                sys.executable, "-m", "pip", "download",
                "--requirement", str(req_file),
                "--dest", str(output_dir),
                "--no-binary", ":all:"
            ]
            
            # 添加镜像源参数
            if index_url:
                cmd2.extend(["--index-url", index_url, "--trusted-host", trusted_host])
            
            self._run_command(cmd2, output_dir)

            manifest_file = output_dir / "MANIFEST.txt"
            with open(manifest_file, "w", encoding="utf-8") as f:
                f.write(f"# MyAPS API 离线依赖包清单 (Linux)\n")
                f.write(f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Python 版本: {python_version}\n")
                f.write(f"# 目标平台: {platform}\n\n")
                for fpath in sorted(output_dir.iterdir()):
                    if fpath.suffix in [".whl", ".tar.gz", ".zip"]:
                        f.write(f"{fpath.name}\n")

            pkg_count = len(list(output_dir.glob("*.whl"))) + len(list(output_dir.glob("*.tar.gz"))) + len(list(output_dir.glob("*.zip")))
            self.log("=" * 50)
            self.log(f"下载完成！共下载 {pkg_count} 个包", "success")
            self.log(f"输出目录: {output_dir}", "success")
            self.log(f"清单文件: {manifest_file}", "success")

        except Exception as e:
            self.log(f"下载过程出错: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "error")
        finally:
            self.btn_download.config(state=tk.NORMAL, text="开始下载")

    def _run_command(self, cmd, cwd=None):
        """运行命令并输出日志"""
        self.log(f"执行命令: {' '.join(str(x) for x in cmd)}", "info")
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if result.stdout:
                self.log(result.stdout.strip())
            if result.stderr:
                self.log(result.stderr.strip(), "warning")
            self.log(f"返回码: {result.returncode}")
        except Exception as e:
            self.log(f"命令执行失败: {e}", "error")

    def setup_install_tab(self):
        """设置安装依赖标签页"""
        frame = tk.Frame(self.tab_install)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(frame, text="依赖包安装（无外网环境）", font=("Arial", 14, "bold")).pack(pady=(0, 20))

        form_frame = tk.Frame(frame)
        form_frame.pack(fill=tk.X, pady=10)

        tk.Label(form_frame, text="项目根目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_install_project_root = tk.Entry(form_frame, width=50)
        self.entry_install_project_root.insert(0, str(self.project_root))
        self.entry_install_project_root.grid(row=0, column=1, sticky=tk.EW, pady=5)
        tk.Button(form_frame, text="浏览...", command=self.browse_install_project_root).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(form_frame, text="离线包目录:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.entry_packages_dir = tk.Entry(form_frame, width=50)
        self.entry_packages_dir.insert(0, str(self.project_root / ".offline_dev" / "to_linux" / "packages"))
        self.entry_packages_dir.grid(row=1, column=1, sticky=tk.EW, pady=5)
        tk.Button(form_frame, text="浏览...", command=self.browse_packages_dir).grid(row=1, column=2, padx=5, pady=5)

        tk.Label(form_frame, text="虚拟环境名称:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.entry_venv_name = tk.Entry(form_frame, width=50)
        self.entry_venv_name.insert(0, "venv")
        self.entry_venv_name.grid(row=2, column=1, sticky=tk.EW, pady=5)

        form_frame.columnconfigure(1, weight=1)

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=20)
        self.btn_install = tk.Button(btn_frame, text="开始安装", command=self.start_install, bg="#2196F3", fg="white", font=("Arial", 12, "bold"), padx=30, pady=10)
        self.btn_install.pack()

        tk.Label(frame, text="说明：请确保已将 .offline_dev/to_linux/packages/ 目录复制到内网。", fg="gray").pack(pady=10)

    def browse_install_project_root(self):
        dir_path = filedialog.askdirectory(initialdir=self.entry_install_project_root.get())
        if dir_path:
            self.entry_install_project_root.delete(0, tk.END)
            self.entry_install_project_root.insert(0, dir_path)

    def browse_packages_dir(self):
        dir_path = filedialog.askdirectory(initialdir=self.entry_packages_dir.get())
        if dir_path:
            self.entry_packages_dir.delete(0, tk.END)
            self.entry_packages_dir.insert(0, dir_path)

    def start_install(self):
        """开始安装"""
        self.btn_install.config(state=tk.DISABLED, text="安装中...")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        """安装工作线程"""
        try:
            project_root = Path(self.entry_install_project_root.get())
            packages_dir = Path(self.entry_packages_dir.get())
            venv_name = self.entry_venv_name.get()
            venv_dir = project_root / venv_name

            self.log("=" * 50)
            self.log("开始安装依赖包...")
            self.log(f"项目根目录: {project_root}")
            self.log(f"离线包目录: {packages_dir}")
            self.log(f"虚拟环境: {venv_dir}")

            req_file = project_root / "requirements.txt"
            if not req_file.exists():
                self.log(f"错误: 找不到 requirements.txt 文件: {req_file}", "error")
                return

            if not packages_dir.exists():
                self.log(f"错误: 找不到离线包目录: {packages_dir}", "error")
                self.log("请确认已将 .offline_dev/to_linux/packages/ 目录复制到内网！", "error")
                return

            self.log("第一步: 创建虚拟环境", "info")
            if venv_dir.exists():
                self.log(f"虚拟环境已存在: {venv_dir}", "warning")
                self.log("正在删除旧虚拟环境...", "warning")
                import shutil
                shutil.rmtree(venv_dir)

            cmd_create = [sys.executable, "-m", "venv", str(venv_dir)]
            self._run_command(cmd_create, project_root)

            pip_path = venv_dir / "bin" / "pip"
            python_path = venv_dir / "bin" / "python"

            self.log("\n第二步: 升级 pip", "info")
            cmd_upgrade = [
                str(pip_path), "install", "--upgrade", "pip",
                "--no-index", f"--find-links={packages_dir}"
            ]
            self._run_command(cmd_upgrade, project_root)

            self.log("\n第三步: 安装所有依赖", "info")
            cmd_install = [
                str(pip_path), "install",
                "--no-index", f"--find-links={packages_dir}",
                "--requirement", str(req_file)
            ]
            self._run_command(cmd_install, project_root)

            self.log("\n第四步: 验证关键包", "info")
            key_pkgs = ["fastapi", "uvicorn", "tortoise-orm", "pydantic", "pandas", "redis"]
            for pkg in key_pkgs:
                try:
                    result = subprocess.run(
                        [str(python_path), "-c", f"import {pkg.replace('-', '_')}; print(f'{pkg} OK')"],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        self.log(f"  ✓ {pkg}", "success")
                    else:
                        self.log(f"  ✗ {pkg}", "error")
                except:
                    self.log(f"  ✗ {pkg}", "error")

            (project_root / "logs").mkdir(exist_ok=True)
            (project_root / "storage").mkdir(exist_ok=True)

            self.log("=" * 50)
            self.log("安装完成！", "success")
            self.log(f"虚拟环境位置: {venv_dir}", "success")
            self.log("下一步: 请前往 '3. 环境配置' 标签页配置 .env 文件", "info")

        except Exception as e:
            self.log(f"安装过程出错: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "error")
        finally:
            self.btn_install.config(state=tk.NORMAL, text="开始安装")

    def setup_config_tab(self):
        """设置环境配置标签页"""
        frame = tk.Frame(self.tab_config)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(frame, text="环境变量配置 (.env)", font=("Arial", 14, "bold")).pack(pady=(0, 20))

        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.config_entries = {}

        self._add_config_section(scrollable_frame, "应用配置", [
            ("PORT", "应用端口", "8000"),
            ("HOST", "监听地址", "0.0.0.0"),
        ])

        self._add_config_section(scrollable_frame, "项目配置", [
            ("PROJECT_DIR", "租户目录", "HACYXS"),
            ("PROJECT_JSON", "配置文件", "dev"),
        ])

        self._add_config_section(scrollable_frame, "MySQL 配置", [
            ("MYAPS_DB_HOST", "主机地址", "localhost"),
            ("MYAPS_DB_PORT", "端口", "3306"),
            ("MYAPS_DB_USER", "用户名", "root"),
            ("MYAPS_DB_PASSWORD", "密码", ""),
            ("MYAPS_DB_SET", "数据库列表", "db1,db2"),
            ("MYAPS_MAIN_DB", "主数据库", "db1"),
        ])

        self._add_config_section(scrollable_frame, "PostgreSQL 配置（可选）", [
            ("THIS_DB_HOST", "主机地址", "localhost"),
            ("THIS_DB_PORT", "端口", "5432"),
            ("THIS_DB_USER", "用户名", "postgres"),
            ("THIS_DB_PASSWORD", "密码", ""),
            ("THIS_DB_NAME", "数据库名", "appsmith"),
        ])

        self._add_config_section(scrollable_frame, "Redis 配置", [
            ("REDIS_HOST", "主机地址", "127.0.0.1"),
            ("REDIS_PORT", "端口", "6379"),
            ("REDIS_DB", "数据库", "0"),
            ("REDIS_PASSWORD", "密码", ""),
        ])

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=20, padx=20)

        tk.Button(btn_frame, text="从 .env.example 加载默认值", command=self.load_env_example, bg="#9E9E9E", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="从现有 .env 加载", command=self.load_existing_env, bg="#9E9E9E", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="保存到 .env", command=self.save_env, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), padx=20).pack(side=tk.LEFT, padx=5)

    def _add_config_section(self, parent, title, fields):
        """添加配置节"""
        section_frame = tk.LabelFrame(parent, text=title, padx=10, pady=10)
        section_frame.pack(fill=tk.X, padx=10, pady=10)

        for i, (key, label, default) in enumerate(fields):
            tk.Label(section_frame, text=label + ":").grid(row=i, column=0, sticky=tk.W, pady=3, padx=5)
            entry = tk.Entry(section_frame, width=50)
            entry.insert(0, default)
            entry.grid(row=i, column=1, sticky=tk.EW, pady=3, padx=5)
            self.config_entries[key] = entry

        section_frame.columnconfigure(1, weight=1)

    def load_env_example(self):
        """从 .env.example 加载"""
        env_example = self.project_root / ".env.example"
        if not env_example.exists():
            messagebox.showerror("错误", "找不到 .env.example 文件")
            return

        with open(env_example, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key in self.config_entries:
                        self.config_entries[key].delete(0, tk.END)
                        self.config_entries[key].insert(0, value)
        self.log("已从 .env.example 加载默认值", "success")

    def load_existing_env(self):
        """从现有 .env 加载"""
        env_file = self.project_root / ".env"
        if not env_file.exists():
            messagebox.showerror("错误", "找不到 .env 文件")
            return

        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key in self.config_entries:
                        self.config_entries[key].delete(0, tk.END)
                        self.config_entries[key].insert(0, value)
        self.log("已从现有 .env 文件加载配置", "success")

    def save_env(self):
        """保存到 .env"""
        env_file = self.project_root / ".env"

        if env_file.exists():
            if not messagebox.askyesno("确认", ".env 文件已存在，是否覆盖？"):
                return

        with open(env_file, "w", encoding="utf-8") as f:
            f.write("# MyAPS API 环境变量配置\n")
            f.write(f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            sections = {
                "应用配置": ["PORT", "HOST"],
                "项目配置": ["PROJECT_DIR", "PROJECT_JSON"],
                "MySQL 配置": ["MYAPS_DB_HOST", "MYAPS_DB_PORT", "MYAPS_DB_USER", "MYAPS_DB_PASSWORD", "MYAPS_DB_SET", "MYAPS_MAIN_DB"],
                "PostgreSQL 配置": ["THIS_DB_HOST", "THIS_DB_PORT", "THIS_DB_USER", "THIS_DB_PASSWORD", "THIS_DB_NAME"],
                "Redis 配置": ["REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD"],
            }

            for section, keys in sections.items():
                f.write(f"# {section}\n")
                for key in keys:
                    if key in self.config_entries:
                        value = self.config_entries[key].get()
                        f.write(f"{key}={value}\n")
                f.write("\n")

            f.write("# 功能开关\n")
            f.write("TURNON_BINLOG_LISTENER=false\n")
            f.write("TRUNON_SCHEDULER=false\n\n")
            f.write("# 日志配置\n")
            f.write("LOG_LEVEL=INFO\n")
            f.write("LOG_DIR=logs\n")
            f.write("TO_CONSOLE=true\n")
            f.write("TO_FILE=true\n")
            f.write("TO_DATABASE=true\n")
            f.write("TO_WEBSOCKET=true\n")

        self.log(f"配置已保存到: {env_file}", "success")
        messagebox.showinfo("成功", "配置已保存！请前往 '4. 服务管理' 标签页启动服务。")

    def setup_service_tab(self):
        """设置服务管理标签页"""
        frame = tk.Frame(self.tab_service)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(frame, text="服务管理 (Linux)", font=("Arial", 14, "bold")).pack(pady=(0, 20))

        form_frame = tk.Frame(frame)
        form_frame.pack(fill=tk.X, pady=10)

        tk.Label(form_frame, text="项目根目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_service_project_root = tk.Entry(form_frame, width=50)
        self.entry_service_project_root.insert(0, str(self.project_root))
        self.entry_service_project_root.grid(row=0, column=1, sticky=tk.EW, pady=5)
        tk.Button(form_frame, text="浏览...", command=self.browse_service_project_root).grid(row=0, column=2, padx=5, pady=5)

        form_frame.columnconfigure(1, weight=1)

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="启动服务", command=self.start_service, bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), padx=20, pady=8).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="停止服务", command=self.stop_service, bg="#F44336", fg="white", font=("Arial", 11, "bold"), padx=20, pady=8).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="查看状态", command=self.check_status, bg="#2196F3", fg="white", font=("Arial", 11, "bold"), padx=20, pady=8).pack(side=tk.LEFT, padx=10)

        tk.Label(frame, text="说明：服务启动后，可访问 http://localhost:8000/docs 查看API文档", fg="gray").pack(pady=10)

    def browse_service_project_root(self):
        dir_path = filedialog.askdirectory(initialdir=self.entry_service_project_root.get())
        if dir_path:
            self.entry_service_project_root.delete(0, tk.END)
            self.entry_service_project_root.insert(0, dir_path)

    def start_service(self):
        """启动服务"""
        project_root = Path(self.entry_service_project_root.get())
        venv_python = project_root / "venv" / "bin" / "python"
        
        if not venv_python.exists():
            self.log(f"错误: 找不到虚拟环境 Python: {venv_python}", "error")
            self.log("请先在 '2. 安装依赖包' 标签页安装依赖", "error")
            return

        self.log("启动服务...", "info")
        cmd = [
            str(venv_python), "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", "8000", "--reload"
        ]
        
        try:
            subprocess.Popen(cmd, cwd=project_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log("服务已启动: http://localhost:8000", "success")
            self.log("API 文档: http://localhost:8000/docs", "success")
        except Exception as e:
            self.log(f"启动失败: {e}", "error")

    def stop_service(self):
        """停止服务"""
        self.log("正在停止服务...", "info")
        try:
            subprocess.run(["pkill", "-f", "uvicorn.*main:app"], capture_output=True)
            self.log("服务已停止", "success")
        except Exception as e:
            self.log(f"停止失败: {e}", "error")

    def check_status(self):
        """检查服务状态"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "uvicorn.*main:app"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self.log("服务正在运行", "success")
                self.log(f"进程ID: {result.stdout.strip()}", "info")
            else:
                self.log("服务未运行", "warning")
        except Exception as e:
            self.log(f"检查失败: {e}", "error")


def main():
    """主函数"""
    root = tk.Tk()
    app = OfflineMigrationTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()