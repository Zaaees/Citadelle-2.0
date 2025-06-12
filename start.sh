#!/bin/bash

# Script de démarrage robuste pour Render
echo "🚀 Démarrage du bot Citadelle 2.0..."

# Vérifier les variables d'environnement critiques
if [ -z "$DISCORD_TOKEN" ]; then
    echo "❌ ERREUR: DISCORD_TOKEN non défini"
    exit 1
fi

if [ -z "$PORT" ]; then
    echo "⚠️ PORT non défini, utilisation du port par défaut 10000"
    export PORT=10000
fi

echo "✅ Variables d'environnement vérifiées"
echo "🔧 Port configuré: $PORT"

# Installer les dépendances si nécessaire
if [ ! -d "__pycache__" ]; then
    echo "📦 Installation des dépendances..."
    pip install -r requirements.txt
fi

# Créer les dossiers nécessaires
mkdir -p logs
mkdir -p data

echo "🤖 Lancement du bot..."

# Lancer le bot avec gestion des erreurs
python main.py

# Si le script arrive ici, c'est qu'il y a eu une erreur
echo "❌ Le bot s'est arrêté de manière inattendue"
exit 1
