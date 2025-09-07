import os
import time
import logging
from datetime import datetime, timedelta
from server import get_last_heartbeat, get_request_count

logger = logging.getLogger('bot')

# Variable globale pour contrôler l'arrêt du monitoring
_monitoring_active = True

def stop_health_monitoring():
    """Arrête le monitoring de santé proprement."""
    global _monitoring_active
    _monitoring_active = False

def check_bot_health_minimal(bot):
    """Version simplifiée et stable du monitoring."""
    global _monitoring_active
    consecutive_failures = 0
    max_consecutive_failures = 20  # Plus tolérant
    check_interval = 600  # 10 minutes
    
    logger.info(f"🏥 Monitoring minimal démarré (vérification toutes les {check_interval}s)")
    
    while _monitoring_active:
        time.sleep(check_interval)
        
        try:
            # Vérification simple : bot fermé
            if bot.is_closed():
                logger.warning("⚠️ Bot fermé détecté, arrêt du monitoring")
                _monitoring_active = False
                break
            
            # Vérification simple : bot prêt
            if not bot.is_ready():
                consecutive_failures += 1
                logger.warning(f"⚠️ Bot non prêt ({consecutive_failures}/{max_consecutive_failures})")
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ Bot non prêt depuis trop longtemps - MONITORING SEULEMENT")
                    # NE PAS redémarrer automatiquement
                continue
            
            # Tout va bien, réinitialiser le compteur
            if consecutive_failures > 0:
                logger.info(f"✅ Bot rétabli après {consecutive_failures} vérifications")
                consecutive_failures = 0
            
            # Log périodique
            logger.info(f"💚 Bot stable (latence: {bot.latency:.2f}s)")
            
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"❌ Erreur monitoring: {e} ({consecutive_failures}/{max_consecutive_failures})")
            # Continuer sans redémarrer

def check_cog_tasks_health(bot):
    """Version simplifiée de la vérification des cogs."""
    try:
        logger.info("🔍 Vérification simplifiée des cogs...")
        
        # Vérifier seulement les cogs critiques sans les redémarrer
        critical_cogs = ['Bump', 'RPTracker']
        for cog_name in critical_cogs:
            cog = bot.get_cog(cog_name)
            if cog:
                logger.info(f"✅ Cog {cog_name} chargé")
            else:
                logger.warning(f"⚠️ Cog {cog_name} non chargé")
                
    except Exception as e:
        logger.error(f"❌ Erreur vérification cogs: {e}")

# Self-ping supprimé - pas nécessaire pour Background Worker
# Render maintient automatiquement les Background Workers actifs
