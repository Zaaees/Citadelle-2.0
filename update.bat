@echo off
REM Script batch pour automatiser les mises a jour GitHub sur Windows

echo ============================================
echo    Auto-Update GitHub - Citadelle Bot
echo ============================================
echo.

REM Verifier si Python est disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH
    pause
    exit /b 1
)

REM Executer l'auto-updater
echo [INFO] Verification des changements...
python auto_update.py --check
if errorlevel 1 (
    echo [INFO] Aucun changement detecte
    echo.
    echo Appuyez sur une touche pour fermer...
    pause >nul
    exit /b 0
)

echo [INFO] Changements detectes, demarrage de l'auto-update...
echo.
python auto_update.py

if errorlevel 1 (
    echo.
    echo [ERREUR] Erreur lors de la mise a jour
    echo Verifiez les logs dans auto_update.log
    pause
    exit /b 1
) else (
    echo.
    echo [SUCCESS] Mise a jour GitHub terminee avec succes!
    echo Render va maintenant deployer automatiquement les changements.
    timeout /t 5
)