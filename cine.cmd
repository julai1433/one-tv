@echo off
rem One TV en Windows: doble clic para arrancar. En una ventana de comandos abierta en esta carpeta:
rem   cine | cine configurar | cine autoarranque | cine quitar-autoarranque | cine estado | cine catalogo
rem Lo hace windows\cine.ps1: revisa que esten Python y ffmpeg (si falta alguno, ofrece instalarlo) y arranca.
setlocal
title One TV
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\cine.ps1" %*
set "CODIGO=%ERRORLEVEL%"
rem Abierto con doble clic (sin nada mas): la ventana espera una tecla antes de cerrarse, para leer lo que paso.
if "%~1"=="" pause
exit /b %CODIGO%
