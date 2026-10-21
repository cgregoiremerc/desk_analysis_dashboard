@echo off
setlocal EnableDelayedExpansion
REM Cree l'environnement virtuel du projet (.venv) et installe les dependances.
REM A lancer une seule fois (ou apres une modification de requirements.txt).
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo L'environnement .venv existe deja - mise a jour des dependances.
    goto :install
)

REM Recherche d'un vrai Python (en ignorant l'alias Microsoft Store)
set "PY="

REM 0) Anaconda installe sur ce PC (C:\Program Files\Anaconda3)
if exist "%ProgramFiles%\Anaconda3\python.exe" set "PY="%ProgramFiles%\Anaconda3\python.exe""

REM 1) Lanceur officiel "py"
if not defined PY py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"

REM 2) Installations classiques (python.org, par utilisateur ou machine)
if not defined PY for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "PY="%%d\python.exe""
if not defined PY for /d %%d in ("%ProgramFiles%\Python3*") do if exist "%%d\python.exe" set "PY="%%d\python.exe""

REM 3) Anaconda / Miniconda
if not defined PY for %%p in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%ProgramFiles%\Miniconda3") do if exist "%%~p\python.exe" set "PY="%%~p\python.exe""

REM 4) python du PATH, seulement s'il fonctionne vraiment
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"

if not defined PY (
    echo [ERREUR] Python introuvable aux emplacements connus.
    echo Installe Python 3.12 ou 3.13 depuis https://www.python.org/downloads/
    echo en cochant "Add python.exe to PATH", puis relance ce fichier.
    pause
    exit /b 1
)

echo Python trouve : !PY!
!PY! --version
echo Creation de l'environnement virtuel .venv ...
!PY! -m venv .venv
if errorlevel 1 goto :error

:install
echo Installation des dependances (requirements.txt) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [OK] Environnement pret. Lance le dashboard avec run_dashboard.bat
pause
exit /b 0

:error
echo.
echo [ERREUR] Voir le message ci-dessus.
pause
exit /b 1
