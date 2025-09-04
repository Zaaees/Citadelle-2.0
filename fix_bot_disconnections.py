#!/usr/bin/env python3
"""
Script de correction pour résoudre les déconnexions du bot sur Render.
Corrige les problèmes de credentials Google, timeouts, et optimise le monitoring.
"""

import json
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_google_credentials():
    """Vérifie et corrige les credentials Google Sheets."""
    try:
        service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            logger.error("❌ SERVICE_ACCOUNT_JSON manquant dans les variables d'environnement")
            return False
            
        # Valider le JSON
        try:
            creds_info = json.loads(service_account_json)
            required_keys = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            
            for key in required_keys:
                if key not in creds_info:
                    logger.error(f"❌ Clé manquante dans SERVICE_ACCOUNT_JSON: {key}")
                    return False
                    
            if not creds_info['private_key'].strip():
                logger.error("❌ private_key vide dans SERVICE_ACCOUNT_JSON")
                return False
                
            logger.info("✅ Credentials Google Sheets valides")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ SERVICE_ACCOUNT_JSON n'est pas un JSON valide: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de la vérification des credentials: {e}")
        return False

def optimize_monitoring_settings():
    """Recommandations pour optimiser le monitoring sur Render."""
    recommendations = {
        'HEALTHCHECK_MAX_FAILURES': '12',  # Plus tolérant
        'HEALTHCHECK_FORCE_RESTART': 'false',  # Désactivé pour Render
        'BOT_MONITORING_INTERVAL': '600',  # 10 minutes
        'GOOGLE_SHEETS_TIMEOUT': '30',  # 30 secondes max par opération
        'RENDER_EXTERNAL_URL': 'https://votre-app.onrender.com'  # À remplacer
    }
    
    logger.info("🔧 Recommandations de variables d'environnement pour Render:")
    for key, value in recommendations.items():
        current = os.getenv(key, 'NON DÉFINIE')
        logger.info(f"  {key}: {current} → {value}")
    
    return recommendations

def check_cog_health():
    """Vérifie la santé des cogs problématiques."""
    project_root = Path(__file__).parent
    
    # Vérifier les fichiers critiques
    critical_files = [
        'cogs/Surveillance_scene.py',
        'cogs/Cards.py', 
        'cogs/bump.py',
        'monitoring.py',
        'main.py'
    ]
    
    for file_path in critical_files:
        full_path = project_root / file_path
        if not full_path.exists():
            logger.error(f"❌ Fichier critique manquant: {file_path}")
            return False
        else:
            logger.info(f"✅ {file_path} présent")
    
    return True

def main():
    """Point d'entrée principal."""
    logger.info("🔧 Diagnostic et correction des problèmes de déconnexion")
    logger.info("=" * 60)
    
    # 1. Vérifier les credentials Google
    logger.info("1️⃣ Vérification des credentials Google Sheets...")
    if not fix_google_credentials():
        logger.error("❌ PROBLÈME CRITIQUE: Credentials Google non valides")
        logger.error("   → Vérifiez SERVICE_ACCOUNT_JSON dans Render Dashboard")
        return False
    
    # 2. Vérifier les fichiers du projet
    logger.info("2️⃣ Vérification des fichiers critiques...")
    if not check_cog_health():
        logger.error("❌ PROBLÈME: Fichiers critiques manquants")
        return False
    
    # 3. Recommandations d'optimisation
    logger.info("3️⃣ Optimisation des paramètres de monitoring...")
    recommendations = optimize_monitoring_settings()
    
    # 4. Résumé des actions à effectuer
    logger.info("=" * 60)
    logger.info("📋 ACTIONS REQUISES:")
    logger.info("1. Dans Render Dashboard → Environment:")
    for key, value in recommendations.items():
        logger.info(f"   • {key} = {value}")
    
    logger.info("\n2. Redéployer l'application sur Render")
    logger.info("3. Surveiller les logs pendant 24h")
    
    logger.info("\n✅ Diagnostic terminé. Suivez les actions ci-dessus.")
    return True

if __name__ == '__main__':
    main()