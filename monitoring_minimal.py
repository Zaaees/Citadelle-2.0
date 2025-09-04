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

def self_ping_minimal():
    """Version simplifiée et stable du self-ping."""
    import requests
    
    consecutive_failures = 0
    max_failures = 10
    ping_interval = 900  # 15 minutes
    
    logger.info("🏓 Self-ping minimal démarré")
    
    while True:
        try:
            time.sleep(ping_interval)
            port = int(os.environ.get("PORT", 10000))
            
            # Ping simple localhost uniquement
            try:
                response = requests.get(f"http://localhost:{port}/ping", timeout=10)
                if response.status_code == 200:
                    consecutive_failures = 0
                    if datetime.now().minute < 5:  # Log une fois par heure
                        logger.info("🏓 Self-ping OK")
                else:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ Self-ping échec HTTP {response.status_code}")
                    
            except Exception as e:
                consecutive_failures += 1
                logger.warning(f"⚠️ Self-ping échec: {e}")
            
            if consecutive_failures >= max_failures:
                logger.error("❌ Self-ping échecs multiples - serveur possiblement down")
                # NE PAS forcer d'action, juste logger
                consecutive_failures = 0  # Reset pour éviter le spam
                
        except Exception as e:
            logger.error(f"❌ Erreur critique self-ping: {e}")
            time.sleep(60)
