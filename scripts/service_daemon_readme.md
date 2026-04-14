# 服务守护脚本使用指南

## 概述
服务守护脚本为 MyAPS_API 服务提供自动化监控和通知功能。

## 创建的文件
- `service_daemon.ps1` - 主守护脚本

## 配置

### 方法 1：.env 文件（推荐）
脚本会自动从位于 `d:\myaps_api\myaps_api\.env` 的 `.env` 文件读取配置。

编辑 `.env` 文件来配置服务守护：

```env
# 服务守护配置
# 服务名称
SERVICE_DAEMON_NAME=MyAPS_API
# 日志目录
SERVICE_DAEMON_LOG_DIR=d:\myaps_api\myaps_api\logs
# 启用邮件通知
SERVICE_DAEMON_EMAIL_ENABLED=false
# 邮件接收地址
SERVICE_DAEMON_EMAIL_TO=
# 邮件发送地址
SERVICE_DAEMON_EMAIL_FROM=
# SMTP服务器
SERVICE_DAEMON_SMTP_SERVER=
# SMTP端口
SERVICE_DAEMON_SMTP_PORT=587
# SMTP用户名
SERVICE_DAEMON_SMTP_USER=
# SMTP密码
SERVICE_DAEMON_SMTP_PASSWORD=
# 启用系统通知
SERVICE_DAEMON_SYSTEM_NOTIFICATION=true
# 启用自动重启
SERVICE_DAEMON_AUTO_RESTART=true
```

### 方法 2：命令行参数
使用参数运行脚本：
```powershell
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "d:\myaps_api\myaps_api\scripts\service_daemon.ps1" -ServiceName "MyAPS_API" -EmailEnabled "true" -EmailTo "admin@example.com" -EmailFrom "monitor@example.com" -SmtpServer "smtp.example.com" -SmtpPort 587 -SmtpUser "your_email@example.com" -SmtpPassword "your_password" -SystemNotification $true -AutoRestart $true
```



## 参数

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| ServiceName | 字符串 | MyAPS_API | 要监控的服务名称 |
| LogDir | 字符串 | d:\myaps_api\myaps_api\logs | 日志文件目录 |
| EmailEnabled | 字符串 | false | 启用邮件通知（true/false） |
| EmailTo | 字符串 | "" | 收件人电子邮件地址 |
| EmailFrom | 字符串 | "" | 发件人电子邮件地址 |
| SmtpServer | 字符串 | "" | SMTP 服务器地址 |
| SmtpPort | 整数 | 587 | SMTP 服务器端口 |
| SmtpUser | 字符串 | "" | SMTP 用户名 |
| SmtpPassword | 字符串 | "" | SMTP 密码 |
| SystemNotification | 布尔值 | true | 启用 Windows 系统通知 |
| AutoRestart | 布尔值 | true | 自动重启失败的服务 |
| EnvFile | 字符串 | 自动计算 | 环境配置文件路径 |

## 设置计划任务

### 使用任务计划程序 GUI：
1. 打开任务计划程序（taskschd.msc）
2. 右键单击 "任务计划程序库" > "创建任务"
3. 常规选项卡：
   - 名称："MyAPS_API 服务守护"
   - 安全选项："不管用户是否登录都要运行"
   - 勾选 "使用最高权限运行"
4. 触发器选项卡：
   - 点击 "新建"
   - 开始任务："按计划"
   - 设置："每天" 或 "重复任务间隔：5分钟"
   - 点击确定
5. 操作选项卡：
   - 点击 "新建"
   - 操作："启动程序"
   - 程序/脚本：`powershell.exe`
   - 添加参数：`-ExecutionPolicy Bypass -NoProfile -File "d:\myaps_api\myaps_api\scripts\service_daemon.ps1" `
   - 点击确定
6. 条件选项卡：
   - 取消勾选 "只有在计算机使用交流电源时才启动任务"（如适用）
7. 设置选项卡：
   - 勾选 "允许按需运行任务"
   - 勾选 "如果错过计划开始时间，立即运行任务"
8. 点击确定创建任务

### 使用 PowerShell 命令：
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -NoProfile -File 'd:\myaps_api\myaps_api\scripts\service_daemon.ps1' -ServiceName 'MyAPS_API' -SystemNotification `$true -AutoRestart `$true"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "MyAPS_API Service Daemon" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
```

## 监控功能

### 1. 服务状态检查
- 监控服务是否运行
- 检查服务是否存在
- 检测服务状态变化

### 2. 自动重启
- 尝试重启失败的服务
- 等待 5 秒后检查重启状态
- 记录重启尝试和结果

### 3. 邮件通知
- 服务停止时发送警报
- 服务成功重启时通知
- 报告重启失败
- 服务未找到时发送警报

### 4. 系统通知
- 显示 Windows 系统托盘通知
- 显示服务状态变化
- 提供视觉警报以便立即关注

### 5. 健康检查
- 监控错误日志文件
- 检查最近的错误（最后 5 分钟）
- 如果检测到日志中的错误则发出警报

## 日志文件

### service_daemon.log
- 包含所有守护活动
- 包括时间戳和状态信息
- 跟踪成功的操作

### service_daemon_errors.log
- 仅包含错误消息
- 用于故障排除
- 帮助识别重复出现的问题

## 测试守护脚本

### 手动测试：
```powershell
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "d:\myaps_api\myaps_api\scripts\service_daemon.ps1" -ServiceName "MyAPS_API" -SystemNotification $true -AutoRestart $false
```

### 测试场景：
1. 手动停止服务并运行守护脚本
2. 验证收到邮件通知
3. 检查系统通知是否出现
4. 测试自动重启功能
5. 查看日志文件以确保正确记录

## 故障排除

### 脚本未运行：
- 检查 PowerShell 执行策略
- 验证文件路径是否正确
- 确保具有适当的权限

### 邮件未发送：
- 验证 SMTP 服务器设置
- 检查网络连接
- 确认电子邮件凭据正确
- 检查防火墙设置

### 系统通知未出现：
- 确保 Windows 通知已启用
- 检查脚本是否以适当的权限运行
- 验证 Windows 中的通知设置

### 服务未重启：
- 检查服务是否具有适当的权限
- 验证服务依赖项是否正在运行
- 查看服务事件日志

## 安全考虑

1. **电子邮件凭据**：安全存储 SMTP 密码
2. **文件权限**：限制对配置文件的访问
3. **服务账户**：使用适当的服务账户权限
4. **日志文件**：定期查看和清理日志文件

## 维护

### 定期任务：
- 每周查看日志文件
- 根据需要更新电子邮件配置
- 每月测试守护脚本功能
- 清理旧日志文件

### 日志轮转：
考虑设置日志轮转以防止日志文件变得过大。您可以使用 log_rotate.ps1 脚本进行此操作。

## 支持

对于问题或疑问：
1. 检查日志文件中的错误消息
2. 验证所有配置参数
3. 在调度前手动测试脚本
4. 查看 Windows 事件日志以了解服务问题