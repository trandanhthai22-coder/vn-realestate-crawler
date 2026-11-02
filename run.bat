@echo off
REM ============================================================
REM  Nhap dup: hien menu chon job.
REM  Hoac goi kem tham so nhu bdscrawl, vd:
REM     run.bat run configs\apartment\vhsc_sapphire.toml --pages 3
REM ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
    echo Chua cai dat - dang chay setup.bat ...
    call setup.bat || exit /b 1
)

if "%~1"=="" (
    ".venv\Scripts\python.exe" -m bdscrawler menu
) else (
    ".venv\Scripts\python.exe" -m bdscrawler %*
)
set CODE=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %CODE%
