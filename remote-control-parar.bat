@echo off
rem Desliga o Remote Control iniciado por remote-control.bat.
set "PIDF=C:\logs\remote-control.pid"
set "RES=C:\logs\remote-control-resumo.txt"
if not exist "%PIDF%" (
    echo O Remote Control nao esta ligado.> "%RES%"
    start "" notepad.exe "%RES%"
    exit /b
)
set /p RPID=<"%PIDF%"
taskkill /PID %RPID% /T /F >nul 2>nul
if errorlevel 1 (
    echo O processo %RPID% ja nao estava rodando.> "%RES%"
) else (
    echo Remote Control desligado.> "%RES%"
)
del "%PIDF%" >nul 2>nul
start "" notepad.exe "%RES%"
