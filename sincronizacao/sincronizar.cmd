@echo off
rem Sincroniza E:\Projetos com o Google Drive. Argumentos extras (-Resync, -DryRun, -Force) sao repassados.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sincronizar.ps1" %*
if not "%SINCRONIZAR_SEM_PAUSA%"=="1" pause
