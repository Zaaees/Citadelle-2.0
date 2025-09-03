#!/bin/bash
# Script shell pour automatiser les mises a jour GitHub sur Unix/Linux/macOS

echo "============================================"
echo "   Auto-Update GitHub - Citadelle Bot"
echo "============================================"
echo

# Verifier si Python est disponible
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERREUR] Python n'est pas installe ou pas dans le PATH"
    exit 1
fi

# Choisir la commande Python appropriee
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

echo "[INFO] Verification des changements..."
$PYTHON_CMD auto_update.py --check
if [ $? -ne 0 ]; then
    echo "[INFO] Aucun changement detecte"
    exit 0
fi

echo "[INFO] Changements detectes, demarrage de l'auto-update..."
echo
$PYTHON_CMD auto_update.py

if [ $? -ne 0 ]; then
    echo
    echo "[ERREUR] Erreur lors de la mise a jour"
    echo "Verifiez les logs dans auto_update.log"
    exit 1
else
    echo
    echo "[SUCCESS] Mise a jour GitHub terminee avec succes!"
    echo "Render va maintenant deployer automatiquement les changements."
    sleep 3
fi