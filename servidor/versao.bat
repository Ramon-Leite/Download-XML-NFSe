@echo off
REM ============================================================
REM  Mostra qual versao do sistema esta neste servidor.
REM  Diz o commit no disco, se falta puxar algo do GitHub e se o
REM  processo no ar esta mesmo rodando esse codigo.
REM  Pode rodar a qualquer momento, nao mexe em nada.
REM ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0versao.ps1"
pause
