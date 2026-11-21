@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0triage_app.ps1"
if errorlevel 1 (
    echo.
    echo Ocorreu um erro ao executar a interface de triagem.
    pause
)
