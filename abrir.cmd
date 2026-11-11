@echo off
rem Abre o CCA (Claude Code Acessivel) sem deixar janela de console aberta.
rem Procura o Python 3.10 ou mais novo (primeiro o 3.13 desta maquina, depois o
rem inicializador "py", depois o que estiver no PATH). Se faltarem o wxPython ou o
rem claude-agent-sdk, oferece instalar.
cd /d "%~dp0"
set "PYEXE="

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYEXE (
    where py >nul 2>nul
    if not errorlevel 1 for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
)
if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
)
if not defined PYEXE goto sem_python

"%PYEXE%" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 goto python_velho

"%PYEXE%" -c "import wx, claude_agent_sdk" >nul 2>nul
if errorlevel 1 goto instalar

:abrir
for %%i in ("%PYEXE%") do set "PYWEXE=%%~dpipythonw.exe"
if not exist "%PYWEXE%" set "PYWEXE=%PYEXE%"
start "" "%PYWEXE%" app.py
exit /b

:instalar
echo Faltam o wxPython ou o claude-agent-sdk neste Python:
echo   %PYEXE%
choice /c SN /m "Instalar agora (precisa de internet)"
if errorlevel 2 exit /b 1
"%PYEXE%" -m pip install wxPython claude-agent-sdk
"%PYEXE%" -c "import wx, claude_agent_sdk" >nul 2>nul
if errorlevel 1 (
    echo Nao consegui instalar. Rode: "%PYEXE%" -m pip install wxPython claude-agent-sdk
    pause
    exit /b 1
)
goto abrir

:python_velho
echo O Python encontrado e velho demais: %PYEXE%
echo O CCA precisa do Python 3.10 ou mais novo (recomendado o 3.13), em python.org.
pause
exit /b 1

:sem_python
echo Nao encontrei o Python. Instale o Python 3.10 ou mais novo (recomendado o 3.13) em python.org,
echo marcando "Add Python to PATH" no instalador, e abra este arquivo de novo.
pause
exit /b 1
