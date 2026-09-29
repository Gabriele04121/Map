@echo off
rem Start TravelOS on Windows (needs only Python 3.9+; no pip install).
cd /d "%~dp0\.."
if not exist .env copy .env.example .env >nul
where py >nul 2>nul && (py -3 run.py) || (python run.py)
