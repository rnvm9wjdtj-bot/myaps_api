@echo off
chcp 65001 >nul
REM ============================================================
REM MyAPS API - 大文件分片合并脚本 (内网 Windows 机器执行)
REM ============================================================
REM 用途: 自动扫描同目录下所有 .partN 分片并合并还原
REM ============================================================

setlocal

set "TOOLS_DIR=%~dp0"

echo.
echo ========================================
echo   大文件分片合并工具
echo   自动扫描并合并所有分片文件
echo ========================================
echo.

set "MERGE_COUNT=0"

for /f "delims=" %%f in ('dir /b "%TOOLS_DIR%*.part1" 2^>nul') do (
    call :merge_file "%%f"
)

echo.
echo ========================================
if "%MERGE_COUNT%"=="0" (
    echo   未找到需要合并的分片文件
) else (
    echo   合并完成! 共处理 %MERGE_COUNT% 个文件
)
echo ========================================
echo.
echo 文件位于: %TOOLS_DIR%
echo.
pause
goto :eof

:merge_file
set "basename=%~1"
set "basename=%basename:~0,-6%"

cd /d "%TOOLS_DIR%"

set "parts="
set "count=0"

:find_parts
set /a next=%count%+1
if not exist "%basename%.part%next%" goto :do_merge
if "%count%"=="0" (
    set "parts=%basename%.part%next%"
) else (
    set "parts=%parts%+%basename%.part%next%"
)
set "count=%next%"
goto :find_parts

:do_merge
if "%count%"=="0" goto :eof

set /a MERGE_COUNT+=1
echo [%MERGE_COUNT%] 合并 %basename% (%count% 个分片)...
copy /b %parts% "%basename%" >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] %basename% 合并失败
    goto :eof
)

echo   [OK] %basename%
for /l %%i in (1,1,%count%) do (
    if exist "%basename%.part%%i" del "%basename%.part%%i" 2>nul
)
goto :eof
