@echo off
REM ============================================================
REM  Inicia o sistema em MODO SERVIDOR.
REM  Este arquivo e chamado pela tarefa agendada "NFSe Servidor"
REM  na inicializacao do Windows. Nao precisa rodar na mao.
REM ============================================================

cd /d "%~dp0.."

REM Escuta em toda a rede local (0.0.0.0) e nao abre navegador
set NFSE_SERVIDOR=1
set NFSE_PORT=8000

REM pythonw = sem janela de console. O app redireciona os logs para data\logs\
"%~dp0..\.venv\Scripts\pythonw.exe" app.py
