@echo off
REM Build portable Windows .exe (Nuitka)
REM Requires: pip install nuitka pyqt5
REM Includes: style.css, icons, components/

nuitka ^
  --onefile ^
  --standalone ^
  --enable-plugin=pyqt5 ^
  --remove-output ^
  --include-data-files=style.css=style.css ^
  --include-data-files=systemon.png=systemon.png ^
  --include-package=components ^
  --windows-console-mode=disable ^
  --output-dir=dist ^
  systemon.py
pause