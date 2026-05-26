@echo off
title Instalador - Fiscal Manager
color 0A
cls
echo ===================================================
echo          INSTALADOR - FISCAL MANAGER
echo ===================================================
echo.
echo Criando atalho de acesso na sua Area de Trabalho...
echo.

# Executa comando PowerShell para criar atalho .lnk de forma nativa e segura
powershell -NoProfile -ExecutionPolicy Bypass -Command "$Shell = New-Object -ComObject WScript.Shell; $Desktop = [System.Environment]::GetFolderPath('Desktop'); $Shortcut = $Shell.CreateShortcut((Join-Path $Desktop 'Fiscal Manager.lnk')); $Shortcut.TargetPath = (Join-Path '%~dp0' 'Iniciar_Sistema.bat'); $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = (Join-Path '%~dp0' 'fiscal.ico'); $Shortcut.Description = 'Fiscal Manager - NFS-e Portal Nacional'; $Shortcut.Save()"

echo.
echo ===================================================
echo     ATALHO CRIADO COM SUCESSO NA AREA DE TRABALHO!
echo ===================================================
echo.
echo Agora voce pode fechar esta janela e iniciar o sistema
echo dando dois cliques no icone 'Fiscal Manager' da sua tela!
echo.
pause
exit
