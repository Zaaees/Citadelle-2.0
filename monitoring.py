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
    max_consecutive_failures = int(os.environ.get('HEALTHCHECK_MAX_FAILURES', '10'))
    force_restart = os.environ.get('HEALTHCHECK_FORCE_RESTART', 'false').lower() in ('1', 'true', 'yes')
    last_task_check = datetime.now()

    while True:
        time.sleep(180)  # Vérification toutes les 3 minutes

        try:
            # Vérifications de santé
            current_time = datetime.now()

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
                        bot.loop.call_soon_threadsafe(bot.close)
                    logger.error("on_ready jamais appelé - redémarrage non forcé (configurable)")
                continue

            # 2. Vérifier la latence
            if bot.latency == float('inf') or bot.latency > 30.0:
                consecutive_failures += 1
                logger.warning(
                    f"⚠️ Latence problématique: {bot.latency}s (échec {consecutive_failures}/{max_consecutive_failures})"
                )
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ Latence critique détectée. Redémarrage du bot...")
                    if force_restart:
                        bot.loop.call_soon_threadsafe(bot.close)
                    logger.error("Latence critique détectée - redémarrage non forcé (configurable)")
                continue

            # 3. Vérifier si le bot est connecté
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
                        bot.loop.call_soon_threadsafe(bot.close)
                    logger.error("Bot non prêt - redémarrage non forcé (configurable)")
                continue

            # 4. Vérifier les tâches des cogs toutes les 15 minutes
            if (current_time - last_task_check).total_seconds() > 900:  # 15 minutes
                check_cog_tasks_health(bot)
                last_task_check = current_time

            # 5. Nettoyer les ressources périodiquement
            resource_monitor.check_and_cleanup()

            # 6. Vérifier le heartbeat du serveur HTTP
            time_since_heartbeat = current_time - get_last_heartbeat()
            if time_since_heartbeat > timedelta(minutes=10):
                logger.warning(f"⚠️ Aucun heartbeat HTTP depuis {time_since_heartbeat}")

            # Si on arrive ici, tout va bien
            if consecutive_failures > 0:
                logger.info(
                    f"✅ Santé du bot rétablie après {consecutive_failures} échecs"
                )
            consecutive_failures = 0

            logger.info(
                f"💚 Santé du bot: OK (latence: {bot.latency:.2f}s, requêtes HTTP: {get_request_count()})"
            )

        except Exception as e:
            consecutive_failures += 1
            logger.error(
                f"❌ Erreur lors de la vérification de santé: {e} (échec {consecutive_failures}/{max_consecutive_failures})"
            )
            if consecutive_failures >= max_consecutive_failures:
                logger.critical(
                    "❌ Trop d'erreurs lors des vérifications de santé. Redémarrage..."
                )
                if force_restart:
                    bot.loop.call_soon_threadsafe(bot.close)
                logger.error("Trop d'erreurs lors des vérifications de santé - redémarrage non forcé (configurable)")


def self_ping():
    """Fonction pour se ping soi-même et maintenir l'activité"""
    import requests

    while True:
        try:
            time.sleep(300)  # Ping toutes les 5 minutes
            port = int(os.environ.get("PORT", 10000))

            # Essayer de ping localhost d'abord
            try:
                response = requests.get(f"http://localhost:{port}/ping", timeout=10)
                if response.status_code == 200:
                    logger.info("🏓 Self-ping réussi (localhost)")
                    continue
            except Exception:
                pass

            # Si localhost ne marche pas, essayer l'URL Render si disponible
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                try:
                    response = requests.get(f"{render_url}/ping", timeout=10)
                    if response.status_code == 200:
                        logger.info("🏓 Self-ping réussi (Render URL)")
                        continue
                except Exception:
                    pass

            logger.warning("⚠️ Self-ping échoué")

        except Exception as e:
            logger.error(f"❌ Erreur lors du self-ping: {e}")
