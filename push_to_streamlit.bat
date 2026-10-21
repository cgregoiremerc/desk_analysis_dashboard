@echo off
REM Pousse les changements sur GitHub -> Streamlit Cloud redeploie automatiquement (1-2 min)
cd /d "%~dp0"

set "HASCHANGES="
for /f "delims=" %%i in ('git status --porcelain') do set "HASCHANGES=1"
if not defined HASCHANGES (
    echo Aucun changement a pousser.
    pause
    exit /b 0
)

echo Fichiers modifies :
git status --short
echo.
set "MSG="
set /p "MSG=Message du commit (Entree = 'Update dashboard') : "
if "%MSG%"=="" set "MSG=Update dashboard"

git add .
git commit -m "%MSG%"
if errorlevel 1 goto :error
git push
if errorlevel 1 goto :error

echo.
echo [OK] Changements pousses. Streamlit Cloud redeploie l'app dans 1-2 minutes.
pause
exit /b 0

:error
echo.
echo [ERREUR] Le push a echoue - voir le message ci-dessus.
pause
exit /b 1
