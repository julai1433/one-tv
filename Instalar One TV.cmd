@echo off
rem Doble clic para instalar (o poner al dia) One TV en Windows. Hace lo mismo que pegar esto en PowerShell:
rem   irm https://raw.githubusercontent.com/julai1433/one-tv/main/windows/instalar.ps1 | iex
rem Si Windows avisa que el archivo viene de internet: "Mas informacion" y "Ejecutar de todas formas".
setlocal
title Instalar One TV
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/julai1433/one-tv/main/windows/instalar.ps1 | iex"
set "CODIGO=%ERRORLEVEL%"
echo.
pause
exit /b %CODIGO%
