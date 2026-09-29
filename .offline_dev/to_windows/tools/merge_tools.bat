@echo off
chcp 65001 >nul
REM ============================================================
REM MyAPS API - 大文件分片合并脚本 (内网 Windows 机器执行)
REM ============================================================
REM 用途: 将超过200M上传限制而拆分的工具安装包重新合并
REM 前置条件: 已将 tools 目录完整复制到本机
REM 说明: 本脚本与分片文件在同一目录(tools/)下
REM ============================================================

setlocal EnableDelayedExpansion

set "TOOLS_DIR=%~dp0"

REM 颜色定义
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

echo.
echo %GREEN%========================================%NC%
echo %GREEN%  大文件分片合并工具%NC%
echo %GREEN%========================================%NC%
echo.

REM 定义需要合并的文件列表
REM 格式: 原文件名|分片数
set "FILE_COUNT=0"

REM --- PostgreSQL (356M = 199M + 157M) ---
set /a FILE_COUNT+=1
echo %BLUE%[%FILE_COUNT%] 合并 PostgreSQL 安装包...%NC%
if exist "%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe.part1" (
    if exist "%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe.part2" (
        copy /b "%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe.part1"+"%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe.part2" "%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe" >nul
        if !errorLevel! equ 0 (
            echo   %GREEN%[OK] postgresql-18.3-3-windows-x64.exe%NC%
            del "%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe.part1" "%TOOLS_DIR%postgresql-18.3-3-windows-x64.exe.part2"
        ) else (
            echo   %RED%[FAIL] PostgreSQL 合并失败%NC%
        )
    ) else (
        echo   %YELLOW%[SKIP] 缺少分片文件 part2%NC%
    )
) else (
    echo   %YELLOW%[SKIP] 已合并或缺少分片文件%NC%
)

REM --- SQLark (369M = 199M + 170M) ---
set /a FILE_COUNT+=1
echo %BLUE%[%FILE_COUNT%] 合并 SQLark 数据库工具...%NC%
if exist "%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip.part1" (
    if exist "%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip.part2" (
        copy /b "%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip.part1"+"%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip.part2" "%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip" >nul
        if !errorLevel! equ 0 (
            echo   %GREEN%[OK] SQLark_V3.10_Win_x86_64.zip%NC%
            del "%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip.part1" "%TOOLS_DIR%SQLark_V3.10_Win_x86_64.zip.part2"
        ) else (
            echo   %RED%[FAIL] SQLark 合并失败%NC%
        )
    ) else (
        echo   %YELLOW%[SKIP] 缺少分片文件 part2%NC%
    )
) else (
    echo   %YELLOW%[SKIP] 已合并或缺少分片文件%NC%
)

REM --- Trae (290M = 199M + 91M) ---
set /a FILE_COUNT+=1
echo %BLUE%[%FILE_COUNT%] 合并 Trae 编辑器...%NC%
if exist "%TOOLS_DIR%Trae_CN-Setup-x64.exe.part1" (
    if exist "%TOOLS_DIR%Trae_CN-Setup-x64.exe.part2" (
        copy /b "%TOOLS_DIR%Trae_CN-Setup-x64.exe.part1"+"%TOOLS_DIR%Trae_CN-Setup-x64.exe.part2" "%TOOLS_DIR%Trae_CN-Setup-x64.exe" >nul
        if !errorLevel! equ 0 (
            echo   %GREEN%[OK] Trae_CN-Setup-x64.exe%NC%
            del "%TOOLS_DIR%Trae_CN-Setup-x64.exe.part1" "%TOOLS_DIR%Trae_CN-Setup-x64.exe.part2"
        ) else (
            echo   %RED%[FAIL] Trae 合并失败%NC%
        )
    ) else (
        echo   %YELLOW%[SKIP] 缺少分片文件 part2%NC%
    )
) else (
    echo   %YELLOW%[SKIP] 已合并或缺少分片文件%NC%
)

echo.
echo %GREEN%========================================%NC%
echo %GREEN%  合并完成!%NC%
echo %GREEN%========================================%NC%
echo.
echo 合并后的文件位于: %TOOLS_DIR%
echo.
echo 下一步:
echo   1. 运行 postgresql-18.3-3-windows-x64.exe 安装 PostgreSQL
echo   2. 解压 SQLark_V3.10_Win_x86_64.zip 使用 SQLark
echo   3. 运行 Trae_CN-Setup-x64.exe 安装 Trae 编辑器
echo.
pause