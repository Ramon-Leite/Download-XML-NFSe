@echo off
REM ============================================================
REM  PASSO 2 - Registra as tarefas do Windows
REM  Rodar UMA VEZ, como ADMINISTRADOR.
REM   - "NFSe Servidor": sobe o sistema junto com o Windows,
REM     sem precisar que alguem faca login na maquina.
REM   - "NFSe Backup": copia banco, certificados e XMLs todo dia.
REM ============================================================
setlocal

set PROJ=%~dp0..
set SCRIPTS=%~dp0

echo.
echo [1/2] Registrando a tarefa de inicializacao...
schtasks /create /tn "NFSe Servidor" ^
    /tr "\"%SCRIPTS%iniciar_servidor.bat\"" ^
    /sc onstart /delay 0000:30 /ru SYSTEM /rl highest /f
if errorlevel 1 (
    echo ERRO: falhou ao criar a tarefa. Rodou como Administrador?
    pause
    exit /b 1
)

echo [2/2] Registrando o backup diario (12:30)...
schtasks /create /tn "NFSe Backup" ^
    /tr "\"%SCRIPTS%backup.bat\"" ^
    /sc daily /st 12:30 /ru SYSTEM /rl highest /f
if errorlevel 1 (
    echo AVISO: falhou ao criar a tarefa de backup.
)

echo.
echo === PASSO 2 CONCLUIDO ===
echo.
echo Iniciando o servidor agora (sem precisar reiniciar o PC)...
schtasks /run /tn "NFSe Servidor"
timeout /t 8 /nobreak >nul

echo.
echo Teste no navegador deste PC: http://localhost:8000
echo Teste de outro PC da rede:   http://%COMPUTERNAME%:8000
echo.
pause
