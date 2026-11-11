@echo off
rem Abre o CCA (Claude Code Acessivel) sem deixar janela de console aberta.
rem Usa o Python 3.13 onde wxPython e claude-agent-sdk estao instalados.
cd /d "%~dp0"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" app.py
    exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3.13 app.py
    exit /b
)
echo Nao encontrei o Python 3.13. Instale o Python e rode: python -m pip install wxPython claude-agent-sdk
pause
