@echo off
rem Liga o Remote Control do Claude Code escondido (sem janela de terminal) e abre o resultado no Bloco de Notas.
rem Uso: remote-control.bat [pasta de trabalho]   (sem argumento usa a pasta deste arquivo)
if "%~1"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0remote-control.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0remote-control.ps1" -Pasta "%~1"
)
