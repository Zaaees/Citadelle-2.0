import os
import time
import logging
from datetime import datetime, timedelta

# Logger doit être défini AVANT les imports conditionnels
logger = logging.getLogger('bot')

# Imports conditionnels pour les dépendances optionnelles
try:
    from utils.connection_manager import resource_monitor
    CONNECTION_MANAGER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Connection manager non disponible: {e}")
    class MockResourceMonitor:
        def check_and_cleanup(self):
            pass
    resource_monitor = MockResourceMonitor()
    CONNECTION_MANAGER_AVAILABLE = False
    
from server import get_last_heartbeat, get_request_count


def check_cog_tasks_health(bot):
    """Vérifie la santé des tâches dans les cogs."""
    try:
        logger.info("🔍 Vérification de la santé des tâches des cogs...")

        # Vérifier les tâches du cog bump
        bump_cog = bot.get_cog('Bump')
        if bump_cog:
            try:
                if hasattr(bump_cog, 'check_bump'):
                    if not bump_cog.check_bump.is_running():
                        logger.warning("⚠️ Tâche check_bump arrêtée, tentative de redémarrage...")
                        bump_cog.check_bump.restart()
            except Exception as e:
                logger.error(f"❌ Erreur lors de la vérification des tâches Bump: {e}")

        # Vérifier les tâches du cog RPTracker
        rp_tracker_cog = bot.get_cog('RPTracker')
        if rp_tracker_cog:
            try:
                if hasattr(rp_tracker_cog, 'update_loop'):
                    if not rp_tracker_cog.update_loop.is_running():
                        logger.warning("⚠️ Tâche update_loop arrêtée, tentative de redémarrage...")
                        rp_tracker_cog.update_loop.restart()
            except Exception as e:
                logger.error(f"❌ Erreur lors de la vérification des tâches RPTracker: {e}")

        logger.info("✅ Vérification des tâches des cogs terminée")

    except Exception as e:
        logger.error(f"❌ Erreur lors de la vérification globale des tâches: {e}")


# Variable globale pour contrôler l'arrêt du monitoring
_monitoring_active = True

def stop_health_monitoring():
    """Arrête le monitoring de santé proprement."""
    global _monitoring_active
    _monitoring_active = False

def check_bot_health(bot):
    global _monitoring_active
    consecutive_failures = 0
    max_consecutive_failures = int(os.environ.get('HEALTHCHECK_MAX_FAILURES', '8'))  # Moins agressif pour Render
    force_restart = os.environ.get('HEALTHCHECK_FORCE_RESTART', 'false').lower() in ('1', 'true', 'yes')  # Désactivé par défaut pour Render
    last_task_check = datetime.now()
    high_latency_count = 0
    check_interval = int(os.environ.get('BOT_MONITORING_INTERVAL', '600'))  # 10 minutes par défaut pour Render

    logger.info(f"🏥 Health monitoring démarré (max_failures: {max_consecutive_failures}, force_restart: {force_restart})")

    while _monitoring_active:
        time.sleep(check_interval)  # Vérification moins fréquente pour Render

        try:
            # Vérifications de santé
            current_time = datetime.now()
            
            # Vérifier si le bot est fermé
            if bot.is_closed():
                logger.warning("⚠️ Bot fermé détecté, arrêt du monitoring")
                _monitoring_active = False
                break

            # 1. Vérifier si on_ready a été appelé
            if not bot.ready_called:
                consecutive_failures += 1
                logger.warning(
                    f"⚠️ on_ready n'a pas encore été appelé (échec {consecutive_failures}/{max_consecutive_failures})"
                )
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical(
                        "❌ on_ready n'a jamais été appelé après plusieurs vérifications. Redémarrage du bot..."
                    )
                    if force_restart:
                        try:
                            bot.loop.call_soon_threadsafe(bot.close)
                        except Exception as e:
                            logger.error(f"Erreur lors du close: {e}")
                    else:
                        logger.error("on_ready jamais appelé - redémarrage non forcé (configurable)")
                continue

            # 2. Vérifier la latence (seuil adapté pour Render)
            if bot.latency == float('inf') or bot.latency > 35.0:  # Seuil encore plus tolérant pour Render
                high_latency_count += 1
                logger.warning(
                    f"⚠️ Latence élevée: {bot.latency}s (compte: {high_latency_count})"
                )
                
                # Plus tolérant pour éviter les faux positifs
                if high_latency_count >= 5:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ Latence persistante détectée ({consecutive_failures}/{max_consecutive_failures})")
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logger.critical(f"❌ Latence critique persistante: {bot.latency}s")
                        if force_restart:
                            try:
                                asyncio.run_coroutine_threadsafe(bot.close(), bot.loop).result(timeout=5)
                            except Exception as e:
                                logger.error(f"Erreur lors du close: {e}")
                        else:
                            logger.error("Latence critique détectée - monitoring seulement")
                continue
            else:
                # Réinitialiser le compteur si la latence redevient normale
                if high_latency_count > 0:
                    logger.info(f"✅ Latence redevenue normale: {bot.latency}s")
                high_latency_count = 0

            # 3. Vérifier si le bot est connecté et fonctionnel
            if not bot.is_ready():
                consecutive_failures += 1
                logger.warning(
                    f"⚠️ Bot non prêt (échec {consecutive_failures}/{max_consecutive_failures})"
                )
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical(
                        "❌ Bot non prêt après plusieurs vérifications. Redémarrage..."
                    )
                    if force_restart:
                        try:
                            bot.loop.call_soon_threadsafe(bot.close)
                        except Exception as e:
                            logger.error(f"Erreur lors du close: {e}")
                    else:
                        logger.error("Bot non prêt - redémarrage non forcé (configurable)")
                continue
            
            # 3.5 Vérifier la connexion WebSocket
            if hasattr(bot, 'ws') and bot.ws and bot.ws.is_ratelimited():
                logger.warning("⚠️ Bot limité par Discord (rate limited)")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ Rate limiting persistant. Redémarrage...")
                    if force_restart:
                        try:
                            bot.loop.call_soon_threadsafe(bot.close)
                        except Exception as e:
                            logger.error(f"Erreur lors du close: {e}")
                continue

            # 4. Vérifier les tâches des cogs toutes les 10 minutes
            if (current_time - last_task_check).total_seconds() > 600:  # 10 minutes
                check_cog_tasks_health(bot)
                last_task_check = current_time

            # 5. Nettoyer les ressources périodiquement
            try:
                if CONNECTION_MANAGER_AVAILABLE:
                    resource_monitor.check_and_cleanup()
            except Exception as e:
                logger.error(f"Erreur lors du nettoyage des ressources: {e}")

            # 6. Vérifier le heartbeat du serveur HTTP (plus tolérant pour Render)
            try:
                time_since_heartbeat = current_time - get_last_heartbeat()
                if time_since_heartbeat > timedelta(minutes=15):  # Plus tolérant
                    logger.warning(f"⚠️ Aucun heartbeat HTTP depuis {time_since_heartbeat}")
                    consecutive_failures += 1
            except Exception as e:
                logger.debug(f"Erreur lors de la vérification du heartbeat: {e}")

            # Si on arrive ici, tout va bien
            if consecutive_failures > 0:
                logger.info(
                    f"✅ Santé du bot rétablie après {consecutive_failures} échecs"
                )
            consecutive_failures = 0

            # Mettre à jour l'état du bot
            try:
                from bot_state import update_bot_state
                update_bot_state('connected', latency=bot.latency)
            except (ImportError, Exception) as e:
                logger.debug(f"Impossible de mettre à jour l'état: {e}")
            
            logger.info(
                f"💚 Santé du bot: OK (latence: {bot.latency:.2f}s, requêtes HTTP: {get_request_count()}, échecs: {consecutive_failures})"
            )

        except Exception as e:
            consecutive_failures += 1
            logger.error(
                f"❌ Erreur lors de la vérification de santé: {e} (échec {consecutive_failures}/{max_consecutive_failures})"
            )
            traceback.print_exc()
            
            if consecutive_failures >= max_consecutive_failures:
                logger.critical(
                    "❌ Trop d'erreurs lors des vérifications de santé. Redémarrage..."
                )
                if force_restart:
                    try:
                        bot.loop.call_soon_threadsafe(bot.close)
                    except Exception as close_error:
                        logger.error(f"Erreur lors du close: {close_error}")
                else:
                    logger.error("Trop d'erreurs lors des vérifications de santé - redémarrage non forcé (configurable)")


def self_ping():
    """Fonction intelligente pour maintenir l'activité sur Render"""
    import requests
    
    consecutive_failures = 0
    max_failures = 5  # Plus tolérant
    ping_interval = 720  # 12 minutes pour Render (moins agressif)

    logger.info("🏓 Self-ping Render démarré")

    while True:
        try:
            time.sleep(ping_interval)
            port = int(os.environ.get("PORT", 10000))
            ping_success = False

            # Stratégie intelligente de ping
            endpoints_to_try = [
                (f"http://localhost:{port}/ping", "localhost", 8),
                (f"http://127.0.0.1:{port}/ping", "127.0.0.1", 8),
            ]
            
            # Ajouter l'URL Render si disponible
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                endpoints_to_try.append((f"{render_url}/ping", "Render URL", 15))

            for url, name, timeout in endpoints_to_try:
                try:
                    response = requests.get(url, timeout=timeout)
                    if response.status_code == 200:
                        logger.info(f"🏓 Self-ping réussi ({name})")
                        ping_success = True
                        consecutive_failures = 0
                        break
                except requests.exceptions.RequestException as e:
                    logger.debug(f"Ping {name} échoué: {e}")
                    continue

            if not ping_success:
                consecutive_failures += 1
                logger.warning(f"⚠️ Tous les self-ping ont échoué ({consecutive_failures}/{max_failures})")
                
                # Attendre plus longtemps après un échec
                if consecutive_failures >= 2:
                    time.sleep(60)  # Attendre 1 minute supplémentaire
                    
                if consecutive_failures >= max_failures:
                    logger.error("❌ Self-ping échec critique - serveur possiblement inaccessible")
                    # Ne pas forcer l'arrêt, juste logger
            else:
                # Log périodique pour confirmer l'activité
                current_hour = datetime.now().hour
                if current_hour % 2 == 0 and datetime.now().minute < 10:
                    logger.info(f"💚 Self-ping maintenance active (échecs consécutifs: {consecutive_failures})")

        except Exception as e:
            consecutive_failures += 1
            logger.error(f"❌ Erreur critique dans self-ping: {e} ({consecutive_failures}/{max_failures})")
            # Attendre avant de réessayer en cas d'erreur critique
            time.sleep(120)
