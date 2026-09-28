@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_seo_auditor.ps1"
if errorlevel 1 pause
endlocal
