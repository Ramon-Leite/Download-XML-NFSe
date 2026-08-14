@echo off
REM ============================================================
REM  Para o servidor NFSe por completo e com seguranca.
REM  Encerra a tarefa agendada E o processo Python que ficaria orfao
REM  segurando a porta -- mirando SO nos processos desta instalacao.
REM
REM  Nunca use "taskkill /F /IM pythonw.exe" no lugar disto: aquilo
REM  derruba todo Python sem console da maquina, inclusive de outros
REM  sistemas que rodem no mesmo servidor.
REM
REM  Para so ver o que seria encerrado, sem encerrar:
REM      parar_servidor.bat /listar
REM ============================================================
setlocal

if /i "%~1"=="/listar" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0parar_servidor.ps1" -Listar
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0parar_servidor.ps1"
)
