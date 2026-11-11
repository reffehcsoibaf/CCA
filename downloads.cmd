@echo off
rem Mostra quantos downloads cada versao do CCA teve no GitHub.
rem A saida tambem fica gravada em C:\logs\downloads.txt.
cd /d "%~dp0"
if not exist C:\logs mkdir C:\logs
set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=py -3.13"
%PY% -X utf8 downloads.py %* > C:\logs\downloads.txt 2>&1
type C:\logs\downloads.txt
echo.
echo Saida gravada em C:\logs\downloads.txt
pause
