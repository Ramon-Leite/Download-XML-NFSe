@echo off
REM ============================================================
REM  Backup diario - rodado pela tarefa "NFSe Backup"
REM
REM  !! AJUSTE O DESTINO ABAIXO !!
REM  Use um HD externo, um pendrive fixo ou uma pasta sincronizada
REM  (OneDrive/Google Drive). Backup no mesmo disco nao protege
REM  contra o disco morrer.
REM  Obs: a tarefa roda como SYSTEM, entao unidades de rede
REM  mapeadas (Z:\) nao funcionam - use caminho UNC (\\PC\pasta).
REM ============================================================
setlocal

set DESTINO=D:\Backups\NFSe

cd /d "%~dp0.."

if not exist "%DESTINO%" mkdir "%DESTINO%" 2>nul
if not exist "%DESTINO%" (
    echo ERRO: destino %DESTINO% indisponivel. Backup NAO foi feito.
    exit /b 1
)

echo === Backup iniciado em %DATE% %TIME% ===

REM 1. Banco de dados - copia consistente via API do SQLite (mantem 30 dias)
".venv\Scripts\python.exe" "%~dp0backup_db.py" "%DESTINO%\banco" 30

REM 2. Certificados digitais - espelho
robocopy "data\certificados" "%DESTINO%\certificados" /MIR /R:2 /W:5 /NFL /NDL /NJH /NJS

REM 3. XMLs baixados - espelho
robocopy "xmls" "%DESTINO%\xmls" /MIR /R:2 /W:5 /NFL /NDL /NJH /NJS

REM robocopy usa codigos 0-7 para sucesso; 8+ e erro real
if errorlevel 8 (
    echo AVISO: robocopy relatou erro ao copiar arquivos.
)

echo === Backup concluido em %DATE% %TIME% ===
exit /b 0
