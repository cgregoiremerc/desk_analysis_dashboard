@echo off
setlocal EnableDelayedExpansion
REM Lance le dashboard en local, TOUJOURS sur le meme port (8501),
REM et affiche le lien de la version en ligne (Streamlit Cloud).
cd /d "%~dp0"

set "PORT=8501"
set "ONLINE_URL="
if exist "online_url.txt" set /p ONLINE_URL=<online_url.txt

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement virtuel .venv n'existe pas encore.
    echo Lance d'abord setup_env.bat
    pause
    exit /b 1
)

REM Ferme un ancien dashboard encore ouvert sur ce port (sinon Streamlit
REM demarre sur 8502, 8503... et l'ancien onglet ne se rafraichit plus).
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
    echo Fermeture de l^'ancien dashboard ^(PID %%p^) ...
    taskkill /PID %%p /F >nul 2>&1
)

echo.
echo ============================================================
echo   Dashboard local  : http://localhost:%PORT%
if defined ONLINE_URL (
echo   Dashboard en ligne: !ONLINE_URL!
) else (
echo   Dashboard en ligne: colle l'adresse dans online_url.txt
)
echo ============================================================
echo   Laisse cette fenetre ouverte. Ctrl+C pour arreter.
echo.

".venv\Scripts\python.exe" -m streamlit run app.py --server.port %PORT%
if errorlevel 1 (
    echo.
    echo [ERREUR] Le dashboard n'a pas pu demarrer. Essaie de relancer setup_env.bat
    pause
)
