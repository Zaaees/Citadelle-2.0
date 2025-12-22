@echo off
echo ========================================
echo  Citadelle Cards API - Backend
echo ========================================
echo.

cd /d "%~dp0"

echo Demarrage du serveur FastAPI...
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
