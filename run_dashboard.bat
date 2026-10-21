@echo off
REM Lance le dashboard Streamlit en local (ouvre http://localhost:8501)
REM avec l'environnement virtuel du projet (.venv).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement virtuel .venv n'existe pas encore.
    echo Lance d'abord setup_env.bat
    pause
    exit /b 1
)

echo Lancement du dashboard...
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 (
    echo.
    echo [ERREUR] Le dashboard n'a pas pu demarrer. Essaie de relancer setup_env.bat
    pause
)
