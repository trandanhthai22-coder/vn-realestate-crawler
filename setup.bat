@echo off
REM ============================================================
REM  Cai dat 1 lan: tao moi truong .venv va cai thu vien.
REM  Nhap dup file nay sau khi git clone.
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY="
for %%V in (3.13 3.12 3.11 3) do (
    if not defined PY (
        py -%%V -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [LOI] Khong tim thay Python 3.11 tro len.
    echo       Tai tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) roi chay lai file nay.
    pause
    exit /b 1
)

echo Dung Python: %PY%
if not exist ".venv\Scripts\python.exe" (
    echo Tao moi truong ao .venv ...
    %PY% -m venv .venv || goto :fail
)

echo Cai thu vien (lan dau mat 1-3 phut) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -e ".[browser]" -q || goto :fail

echo.
echo ============================================================
echo  CAI DAT XONG. Nhap dup run.bat de bat dau crawl.
echo  Can co Chrome hoac Edge tren may (de vuot Cloudflare).
echo ============================================================
pause
exit /b 0

:fail
echo [LOI] Cai dat that bai - xem thong bao phia tren.
pause
exit /b 1
