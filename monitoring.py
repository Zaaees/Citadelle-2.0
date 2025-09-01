import os
import time
import logging
from datetime import datetime, timedelta

from utils.connection_manager import resource_monitor
from server import get_last_heartbeat, get_request_count

logger = logging.getLogger('bot')


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


def check_bot_health(bot):
    consecutive_failures = 0
    max_consecutive_failures = int(os.environ.get('HEALTHCHECK_MAX_FAILURES', '5'))  # Plus agressif
    force_restart = os.environ.get('HEALTHCHECK_FORCE_RESTART', 'true').lower() in ('1', 'true', 'yes')  # Activé par défaut
    last_task_check = datetime.now()
    last_latency_check = datetime.now()
    high_latency_count = 0

    while True:
        time.sleep(120)  # Vérification plus fréquente (2 minutes)

        try:
            # Vérifications de santé
            current_time = datetime.now()
            
            # Vérifier si le bot est fermé
            if bot.is_closed():
                logger.warning("⚠️ Bot fermé détecté, arrêt du monitoring")
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

            # 2. Vérifier la latence (plus strict)
            if bot.latency == float('inf') or bot.latency > 15.0:  # Seuil plus strict
                high_latency_count += 1
                consecutive_failures += 1
                logger.warning(
                    f"⚠️ Latence problématique: {bot.latency}s (compte: {high_latency_count}, échec {consecutive_failures}/{max_consecutive_failures})"
                )
                
                # Plusieurs vérifications de latence élevée = problème
                if high_latency_count >= 3 or consecutive_failures >= max_consecutive_failures:
                    logger.critical(f"❌ Latence critique persistante: {bot.latency}s. Redémarrage du bot...")
                    if force_restart:
                        try:
                            bot.loop.call_soon_threadsafe(bot.close)
                        except Exception as e:
                            logger.error(f"Erreur lors du close: {e}")
                    else:
                        logger.error("Latence critique détectée - redémarrage non forcé (configurable)")
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
                resource_monitor.check_and_cleanup()
            except Exception as e:
                logger.error(f"Erreur lors du nettoyage des ressources: {e}")

            # 6. Vérifier le heartbeat du serveur HTTP
            time_since_heartbeat = current_time - get_last_heartbeat()
            if time_since_heartbeat > timedelta(minutes=8):  # Plus strict
                logger.warning(f"⚠️ Aucun heartbeat HTTP depuis {time_since_heartbeat}")
                consecutive_failures += 1

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
            except ImportError:
                pass
            
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
    """Fonction pour se ping soi-même et maintenir l'activité"""
    import requests
    
    consecutive_failures = 0
    max_failures = 3

    while True:
        try:
            time.sleep(300)  # Ping toutes les 5 minutes
            port = int(os.environ.get("PORT", 10000))
            ping_success = False

            # Essayer de ping localhost d'abord
            try:
                response = requests.get(f"http://localhost:{port}/ping", timeout=10)
                if response.status_code == 200:
                    logger.info("🏓 Self-ping réussi (localhost)")
                    ping_success = True
                    consecutive_failures = 0
            except Exception as e:
                logger.debug(f"Localhost ping failed: {e}")

            # Si localhost ne marche pas, essayer l'URL Render si disponible
            if not ping_success:
                render_url = os.environ.get("RENDER_EXTERNAL_URL")
                if render_url:
                    try:
                        response = requests.get(f"{render_url}/ping", timeout=15)
                        if response.status_code == 200:
                            logger.info("🏓 Self-ping réussi (Render URL)")
                            ping_success = True
                            consecutive_failures = 0
                    except Exception as e:
                        logger.debug(f"Render URL ping failed: {e}")

            if not ping_success:
                consecutive_failures += 1
                logger.warning(f"⚠️ Self-ping échoué ({consecutive_failures}/{max_failures})")
                
                if consecutive_failures >= max_failures:
                    logger.error("❌ Serveur HTTP semble non réactif après plusieurs tentatives")

        except Exception as e:
            consecutive_failures += 1
            logger.error(f"❌ Erreur lors du self-ping: {e} ({consecutive_failures}/{max_failures})")
