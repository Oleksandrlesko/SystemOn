@echo off
REM Збірка portable Windows .exe (Nuitka)
REM Перед збіркою: pip install -r requirements.txt
REM Потрібні: ICON.ico, style.css, systemon.png у цій папці

cd /d "%~dp0"

if not exist "systemon.py" (
    echo ERROR: systemon.py not found in %CD%
    pause
    exit /b 1
)

if not exist "ICON.ico" (
    echo ERROR: ICON.ico not found in %CD%
    echo Place your application icon file as ICON.ico next to systemon.py
    pause
    exit /b 1
)

where nuitka >nul 2>&1
if errorlevel 1 (
    echo ERROR: nuitka not found. Run: pip install -r requirements.txt
    pause
    exit /b 1
)

echo Building SystemOn.exe ...
echo Icon: ICON.ico
echo Output: dist\

set "NUITKA_OPTS=--onefile --standalone --enable-plugin=pyqt5 --remove-output"
set "NUITKA_OPTS=%NUITKA_OPTS% --windows-console-mode=disable"
set "NUITKA_OPTS=%NUITKA_OPTS% --windows-icon-from-ico=ICON.ico"
set "NUITKA_OPTS=%NUITKA_OPTS% --output-dir=dist"
set "NUITKA_OPTS=%NUITKA_OPTS% --include-data-files=style.css=style.css"
set "NUITKA_OPTS=%NUITKA_OPTS% --include-package=components"
set "NUITKA_OPTS=%NUITKA_OPTS% --include-package=matplotlib"
set "NUITKA_OPTS=%NUITKA_OPTS% --include-package-data=matplotlib"

if exist "systemon.png" (
    set "NUITKA_OPTS=%NUITKA_OPTS% --include-data-files=systemon.png=systemon.png"
)

if exist "systemonplugins" (
    set "NUITKA_OPTS=%NUITKA_OPTS% --include-data-dir=systemonplugins=systemonplugins"
)

nuitka %NUITKA_OPTS% systemon.py
if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

echo.
echo BUILD OK. Check the dist folder for SystemOn.exe
pause
