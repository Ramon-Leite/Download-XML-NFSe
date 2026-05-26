@echo off
cd /d "%~dp0"
if exist "python\pythonw.exe" (
    start "" "python\pythonw.exe" sincronizar_direto.py
) else (
    start "" pythonw sincronizar_direto.py
)
exit
