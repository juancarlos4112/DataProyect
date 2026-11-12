@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  ==========================================
echo    ORDENES DE SERVICIO - RACK
echo  ==========================================
echo  Abriendo en http://localhost:8001
echo.
start "" "http://localhost:8001"
python app.py
pause
