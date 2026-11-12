@echo off
rem Acceso a la app desde el celular: app local + tunel HTTPS + QR.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0acceso_celular.ps1"
pause
