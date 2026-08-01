@echo off
echo ===================================================
echo   VoyagerAI Launcher — Local Development Suite
echo ===================================================
echo.
echo Starting FastAPI Backend in a new window...
start "VoyagerAI Backend" cmd /k "cd backend && call venv\Scripts\activate && python -m uvicorn app.main:app --reload --port 8000"

echo Starting Next.js Frontend...
cd frontend && npm run dev
