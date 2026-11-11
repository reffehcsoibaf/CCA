@echo off
rem Publica a versao atual do CCA como release Latest no GitHub.
rem Use: publicar.cmd   ou   publicar.cmd --simular (so monta os zips, sem publicar)
rem A saida tambem fica gravada em C:\logs\publicar.txt.
cd /d "%~dp0"
if not exist C:\logs mkdir C:\logs
set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=py -3.13"
%PY% -X utf8 publicar.py %* > C:\logs\publicar.txt 2>&1
type C:\logs\publicar.txt
echo.
echo Saida gravada em C:\logs\publicar.txt
pause
