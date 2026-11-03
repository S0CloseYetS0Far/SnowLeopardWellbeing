@echo off
rem Snow Leopard Wellbeing - double-click this file to start.
rem To stop it: press Ctrl+Shift+Q, or Ctrl+C in this window, or close this window.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run: creating a Python environment in .venv ...
    py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto :no_python

".venv\Scripts\python.exe" -c "import PySide6.QtMultimedia" 2>nul || (
    echo Installing PySide6 ^(Qt for Python^), this takes a minute ...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :install_failed
)

".venv\Scripts\python.exe" -m wellbeing %*
exit /b %errorlevel%

:no_python
echo Python 3 was not found. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then run this file again.
pause
exit /b 1

:install_failed
echo Installing the Python packages failed, see the messages above.
pause
exit /b 1
