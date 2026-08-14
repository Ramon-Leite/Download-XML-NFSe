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
REM Delegado ao parar_servidor.bat porque o "schtasks /end" sozinho encerra
REM apenas o processo de topo da tarefa: o Python que ele lancou sobrevive
REM como orfao segurando a porta. Sem mata-lo, o /run la embaixo sobe uma
REM SEGUNDA instancia -- a nova roda a migracao do banco, mas quem responde
REM as requisicoes continua sendo a ANTIGA. O sintoma engana: os arquivos de
REM static/ sao lidos do disco e mudam na hora, entao a tela parece
REM atualizada enquanto a API ainda serve o codigo velho.
call "%~dp0parar_servidor.bat"

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

REM Confere que subiu UMA instancia so. Duas significam orfao vivo, e nesse
REM caso a API responde com o codigo antigo sem dar erro nenhum.
REM A contagem usa o mesmo criterio do parar_servidor.ps1 de proposito: dois
REM filtros separados acabariam divergindo com o tempo.
set INSTANCIAS=0
for /f %%n in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0parar_servidor.ps1" -Contar') do set INSTANCIAS=%%n
if "%INSTANCIAS%"=="0" (
    echo.
    echo *** AVISO: o servidor NAO subiu, ninguem esta atendendo a porta.
    echo *** Veja o erro em data\logs\nfse.log
    echo *** Para tentar de novo:  schtasks /run /tn "NFSe Servidor"
) else if not "%INSTANCIAS%"=="1" (
    echo.
    echo *** AVISO: %INSTANCIAS% servidores atendendo a mesma porta, o esperado e 1.
    echo *** Nesse estado a tela atualiza mas a API pode servir codigo ANTIGO.
    echo *** Corrija rodando:  servidor\parar_servidor.bat
    echo *** e em seguida:     schtasks /run /tn "NFSe Servidor"
)

echo.
echo === Pronto. Confira em http://localhost:8000 ===
echo Se algo quebrar, veja data\logs\nfse.log
echo.
pause
