@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0nzo-repo.ps1" %*
exit /b %ERRORLEVEL%
