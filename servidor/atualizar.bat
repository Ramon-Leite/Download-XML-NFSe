@echo off
REM ============================================================
REM  Atualiza o sistema no servidor.
REM  Substitui todo o fluxo antigo de build_update.py + ZIP:
REM  agora e so puxar o codigo novo do GitHub e reiniciar.
REM  Rodar como ADMINISTRADOR (por causa do schtasks).
REM ============================================================
setlocal

cd /d "%~dp0.."

echo [1/4] Parando o servidor...
schtasks /end /tn "NFSe Servidor" >nul 2>&1
timeout /t 3 /nobreak >nul

echo [2/4] Baixando a versao nova do GitHub...
git pull
if errorlevel 1 (
    echo ERRO: falhou o git pull. Servidor sera religado sem atualizar.
    schtasks /run /tn "NFSe Servidor"
    pause
    exit /b 1
)

echo [3/4] Atualizando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet

echo [4/4] Subindo o servidor...
schtasks /run /tn "NFSe Servidor"
timeout /t 8 /nobreak >nul

echo.
echo === Pronto. Confira em http://localhost:8000 ===
echo Se algo quebrar, veja data\logs\nfse.log
echo.
pause
