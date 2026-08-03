@echo off
REM ============================================================
REM  Impede o servidor de dormir/hibernar - de forma definitiva.
REM  Rodar UMA VEZ, como ADMINISTRADOR.
REM
REM  Vale para a MAQUINA inteira (nao so para o NFSe), entao nao
REM  precisa repetir no Integra nem no Reinf.
REM
REM  Por que existe, se o preparar_servidor.bat ja zerava os tempos:
REM  zerar "suspender apos" nao basta. O Windows tem um tempo limite
REM  de suspensao NAO ASSISTIDA, invisivel no painel de energia, que
REM  derruba a maquina depois de um tempo ocioso mesmo com o resto
REM  zerado. E "powercfg /change" so mexe no plano de energia ATIVO -
REM  se o plano trocar (atualizacao, troca de perfil), tudo volta.
REM ============================================================
setlocal

net session >nul 2>&1
if errorlevel 1 (
    echo ERRO: rode este arquivo como ADMINISTRADOR.
    pause
    exit /b 1
)

echo.
echo [1/4] Desativando a hibernacao por completo...
REM Tira a hibernacao da jogada, apaga o hiberfil.sys (libera disco)
REM e desliga de quebra a Inicializacao Rapida, que atrapalha servidor.
powercfg /hibernate off

echo [2/4] Zerando suspensao, hibernacao e desligamento de disco...
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
powercfg /change disk-timeout-ac 0
powercfg /change disk-timeout-dc 0

echo [3/4] Zerando a suspensao nao assistida em todos os planos de energia...
REM 7bc4a2f9-... = "Tempo limite de suspensao nao assistida do sistema"
REM Aplicado nos planos padrao tambem, para sobreviver a troca de plano.
for %%S in (SCHEME_CURRENT SCHEME_BALANCED SCHEME_MIN SCHEME_MAX) do (
    powercfg /setacvalueindex %%S SUB_SLEEP 7bc4a2f9-d8fc-4469-b07b-33eb785aaca0 0 >nul 2>&1
    powercfg /setdcvalueindex %%S SUB_SLEEP 7bc4a2f9-d8fc-4469-b07b-33eb785aaca0 0 >nul 2>&1
    powercfg /setacvalueindex %%S SUB_SLEEP STANDBYIDLE 0 >nul 2>&1
    powercfg /setdcvalueindex %%S SUB_SLEEP STANDBYIDLE 0 >nul 2>&1
    powercfg /setacvalueindex %%S SUB_SLEEP HIBERNATEIDLE 0 >nul 2>&1
    powercfg /setdcvalueindex %%S SUB_SLEEP HIBERNATEIDLE 0 >nul 2>&1
)
powercfg /setactive SCHEME_CURRENT

echo [4/4] Conferindo o resultado...
echo.
echo --- Estados de suspensao ainda disponiveis nesta maquina ---
powercfg /a
echo.
echo Se a lista acima disser que a Hibernacao NAO esta disponivel,
echo o ajuste pegou. A tela ainda apaga sozinha - isso e proposital,
echo economiza o monitor e nao afeta os sistemas.
echo.
echo Falta um ajuste que so existe no SETUP/BIOS da placa:
echo   "Restore on AC Power Loss" (ou "After Power Failure") = Power On
echo Com ele, o PC religa sozinho depois de queda de energia.
echo.

REM Quando chamado pelo preparar_servidor.bat, nao pausa duas vezes
if /i "%~1"=="/semPausa" exit /b 0
pause
