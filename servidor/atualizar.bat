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

REM O /end acima encerra so o processo de topo da tarefa (o cmd do .bat).
REM O pythonw.exe que ele lancou SOBREVIVE como orfao e continua segurando a
REM porta 8000. Sem matar o orfao, o /run la embaixo sobe uma segunda
REM instancia: a nova roda a migracao do banco, mas quem responde as
REM requisicoes continua sendo a ANTIGA. O resultado e traicoeiro: os
REM arquivos de static/ sao lidos do disco e mudam na hora, entao a tela
REM parece atualizada enquanto a API ainda serve o codigo velho.
REM Mata so o pythonw que esta rodando o app.py deste projeto, para nao
REM derrubar outro Python que exista na maquina.
REM Sem pipe de proposito: dentro do .bat o '|' vira separador do cmd e o
REM escape com '^' chega literal no PowerShell. O metodo .Where() evita o tema.
powershell -NoProfile -Command "@(Get-CimInstance Win32_Process).Where({$_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*app.py*'}).ForEach({Stop-Process -Id $_.ProcessId -Force})" >nul 2>&1

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

REM Confere que subiu UMA instancia so. Duas significam orfao vivo, e nesse
REM caso a API responde com o codigo antigo sem dar erro nenhum.
set INSTANCIAS=0
for /f %%n in ('powershell -NoProfile -Command "@(Get-CimInstance Win32_Process).Where({$_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*app.py*'}).Count"') do set INSTANCIAS=%%n
if not "%INSTANCIAS%"=="1" (
    echo.
    echo *** AVISO: %INSTANCIAS% instancias do servidor rodando, o esperado e 1.
    echo *** Com mais de uma, a tela atualiza mas a API serve codigo ANTIGO.
    echo *** Corrija com: taskkill /F /IM pythonw.exe
    echo *** e em seguida: schtasks /run /tn "NFSe Servidor"
)

echo.
echo === Pronto. Confira em http://localhost:8000 ===
echo Se algo quebrar, veja data\logs\nfse.log
echo.
pause
