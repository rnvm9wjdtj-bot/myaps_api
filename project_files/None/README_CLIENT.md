# 客户代码拉取指南

## 概述

本项目使用Git sparse-checkout功能，确保每个客户只能拉取到公共代码和自己专属的文件夹。以下是详细的配置和使用步骤。

## 准备工作

1. 确保安装了Git 2.25.0或更高版本（推荐2.40.0+）
2. 获得Git仓库的访问权限

## 配置步骤

### 1. 初始化仓库

```bash
# 创建项目目录
mkdir myaps_project
cd myaps_project

# 初始化空仓库
git init

# 添加远程仓库
git remote add origin https://gitee.com/sit_and_look_at_the_wind_and_clouds/myaps_api.git

# 启用sparse-checkout
git config core.sparseCheckout true
git sparse-checkout init --no-cone
```

**说明**：
- `--no-cone`: 使用非cone模式，可以更精确地控制要检出的文件


### 2. 配置sparse-checkout（关键步骤）

根据您的客户名称，修改以下配置：

**对于CHANGDE客户：**
```bash
# 写入sparse-checkout配置
echo "apps/" >> .git/info/sparse-checkout
echo "config/" >> .git/info/sparse-checkout
echo "globalobjects/" >> .git/info/sparse-checkout
echo "migrations/" >> .git/info/sparse-checkout
echo "static/" >> .git/info/sparse-checkout
echo "main.py" >> .git/info/sparse-checkout
echo "pyproject.toml" >> .git/info/sparse-checkout
echo "requirements.txt" >> .git/info/sparse-checkout
echo "run.bat" >> .git/info/sparse-checkout
echo "README.md" >> .git/info/sparse-checkout
echo "project_files/CHANGDE/" >> .git/info/sparse-checkout
```

**对于HACYXS客户：**
```bash
# 写入sparse-checkout配置
echo "apps/" >> .git/info/sparse-checkout
echo "config/" >> .git/info/sparse-checkout
echo "globalobjects/" >> .git/info/sparse-checkout
echo "migrations/" >> .git/info/sparse-checkout
echo "static/" >> .git/info/sparse-checkout
echo "main.py" >> .git/info/sparse-checkout
echo "pyproject.toml" >> .git/info/sparse-checkout
echo "requirements.txt" >> .git/info/sparse-checkout
echo "run.bat" >> .git/info/sparse-checkout
echo "README.md" >> .git/info/sparse-checkout
echo "project_files/HACYXS/" >> .git/info/sparse-checkout
```

**对于JYHDXS客户：**
```bash
# 写入sparse-checkout配置
echo "apps/" >> .git/info/sparse-checkout
echo "config/" >> .git/info/sparse-checkout
echo "globalobjects/" >> .git/info/sparse-checkout
echo "migrations/" >> .git/info/sparse-checkout
echo "static/" >> .git/info/sparse-checkout
echo "main.py" >> .git/info/sparse-checkout
echo "pyproject.toml" >> .git/info/sparse-checkout
echo "requirements.txt" >> .git/info/sparse-checkout
echo "run.bat" >> .git/info/sparse-checkout
echo "README.md" >> .git/info/sparse-checkout
echo "project_files/JYHDXS/" >> .git/info/sparse-checkout
```

### 3. 拉取代码

```bash
# 拉取master分支
git pull origin master
```

## 后续操作

### 更新代码

当需要更新代码时，只需执行：

```bash
git pull origin master
```

### 查看当前配置

```bash
# 查看sparse-checkout配置
cat .git/info/sparse-checkout

# 查看当前状态
git status
```

## 注意事项

1. 确保只修改自己专属文件夹内的文件
2. 如需添加新文件到自己的专属文件夹，直接创建并提交即可
3. 公共代码的修改请联系项目维护者
4. 不要尝试修改其他客户的专属文件夹，您的配置会阻止您看到这些文件夹

## 故障排除

### 问题：拉取代码后看不到自己的专属文件夹

**解决方案：**
1. 检查sparse-checkout配置是否正确
2. 确保客户名称拼写正确（区分大小写）
3. 重新执行拉取操作：

```bash
git pull origin master
```

### 问题：修改文件后无法提交

**解决方案：**
1. 确保只修改了自己有权限的文件
2. 检查Git配置是否正确
3. 联系项目维护者获取帮助

## 联系信息

如果遇到任何问题，请联系项目维护者获取帮助。