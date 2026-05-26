@echo off
cd /d "%~dp0"
if exist "python\pythonw.exe" (
    start "" "python\pythonw.exe" launcher.py
) else (
    start "" pythonw launcher.py
)
exit
