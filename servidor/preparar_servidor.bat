@echo off
REM ============================================================
REM  PASSO 1 - Preparacao do PC servidor
REM  Rodar UMA VEZ, como ADMINISTRADOR, dentro da pasta do projeto.
REM  Cria o ambiente Python, libera a porta no firewall e impede
REM  que o PC durma.
REM ============================================================
setlocal

cd /d "%~dp0.."
echo.
echo === Pasta do projeto: %CD%
echo.

echo [1/4] Criando ambiente virtual Python (.venv)...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo ERRO: falhou ao criar o .venv. O Python esta instalado e no PATH?
        pause
        exit /b 1
    )
) else (
    echo     .venv ja existe, pulando.
)

echo [2/4] Instalando dependencias (pode demorar alguns minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: falhou ao instalar as dependencias.
    pause
    exit /b 1
)

echo [3/4] Liberando a porta 8000 no firewall...
REM Restrito a rede local e a faixa do Tailscale (100.64.0.0/10).
REM Assim, se este PC um dia se conectar numa rede publica, a porta NAO fica exposta.
netsh advfirewall firewall delete rule name="NFSe Servidor 8000" >nul 2>&1
netsh advfirewall firewall add rule name="NFSe Servidor 8000" dir=in action=allow ^
    protocol=TCP localport=8000 remoteip=LocalSubnet,100.64.0.0/10
if errorlevel 1 (
    echo AVISO: nao consegui criar a regra de firewall. Rodou como Administrador?
)

echo [4/4] Configurando energia (o servidor nao pode dormir)...
powercfg /change monitor-timeout-ac 15
REM O resto - hibernacao, suspensao e o tempo limite de suspensao NAO
REM ASSISTIDA (o ajuste oculto que derruba a maquina mesmo com os outros
REM zerados) - fica no script dedicado abaixo.
call "%~dp0manter_acordado.bat" /semPausa

echo.
echo === PASSO 1 CONCLUIDO ===
echo.
echo Agora: copie as pastas data\ e xmls\ do PC de producao para ca,
echo depois rode servidor\instalar_tarefas.bat (tambem como Administrador).
echo.
pause
