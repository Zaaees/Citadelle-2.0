import os
import sys
import threading
import traceback
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import time
import asyncio
import signal
import json
from datetime import datetime, timedelta
from utils.health_monitor import get_health_monitor
from utils.connection_manager import resource_monitor

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('bot')

# Charger les variables d'environnement
load_dotenv()

# Variables globales pour le monitoring
bot_start_time = datetime.now()
last_heartbeat = datetime.now()
request_count = 0

# Serveur HTTP amélioré pour Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global request_count, last_heartbeat
        request_count += 1
        last_heartbeat = datetime.now()

        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(b'Bot is running!')

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()

            uptime = datetime.now() - bot_start_time
            health_data = {
                'status': 'healthy',
                'uptime_seconds': int(uptime.total_seconds()),
                'uptime_human': str(uptime),
                'request_count': request_count,
                'last_heartbeat': last_heartbeat.isoformat(),
                'timestamp': datetime.now().isoformat()
            }

            # Ajouter les métriques avancées si disponibles
            try:
                from utils.health_monitor import health_monitor
                if health_monitor:
                    advanced_metrics = health_monitor.metrics.get_health_summary()
                    health_data.update(advanced_metrics)
            except Exception as e:
                health_data['advanced_metrics_error'] = str(e)

            self.wfile.write(json.dumps(health_data).encode())

        elif self.path == '/health/detailed':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()

            try:
                from utils.health_monitor import health_monitor
                if health_monitor:
                    report = health_monitor.get_health_report()
                    self.wfile.write(report.encode())
                else:
                    self.wfile.write(b'Monitoring avance non disponible')
            except Exception as e:
                self.wfile.write(f'Erreur: {str(e)}'.encode())

        elif self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(b'pong')

        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

        logger.info(f"GET {self.path} from {self.client_address[0]} - Request #{request_count}")

    def do_HEAD(self):
        global last_heartbeat
        last_heartbeat = datetime.now()
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        logger.info(f"HEAD {self.path} from {self.client_address[0]}")

    def log_message(self, format, *args):
        # Réduire le spam de logs pour les requêtes normales
        return

def start_http_server():
    max_retries = 10
    retry_count = 0

    while retry_count < max_retries:
        try:
            port = int(os.environ.get("PORT", 10000))
            logger.info(f"Tentative de démarrage du serveur HTTP sur le port {port} (essai {retry_count + 1}/{max_retries})")

            # Créer le serveur avec des options de socket améliorées
            server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
            server.socket.setsockopt(1, 2, 1)  # SO_REUSEADDR

            logger.info(f"✅ Serveur HTTP démarré avec succès sur le port {port}")
            logger.info(f"🌐 Endpoints disponibles:")
            logger.info(f"   - GET /      : Health check basique")
            logger.info(f"   - GET /health: Informations détaillées")
            logger.info(f"   - GET /ping  : Ping rapide")

            server.serve_forever()

        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning(f"Port {port} déjà utilisé, attente de 10 secondes...")
                time.sleep(10)
            else:
                logger.error(f"Erreur OS lors du démarrage du serveur : {e}")
                time.sleep(5)
        except Exception as e:
            logger.error(f"Erreur lors du démarrage du serveur : {e}")
            traceback.print_exc()
            time.sleep(5)

        retry_count += 1
        if retry_count < max_retries:
            logger.info(f"Nouvelle tentative dans 5 secondes...")
            time.sleep(5)

    logger.critical(f"❌ Impossible de démarrer le serveur HTTP après {max_retries} tentatives")
    # Ne pas faire os._exit ici car cela tuerait tout le processus

def check_bot_health(bot):
    consecutive_failures = 0
    max_consecutive_failures = 3
    last_task_check = datetime.now()

    while True:
        time.sleep(180)  # Vérification toutes les 3 minutes

        try:
            # Vérifications de santé
            current_time = datetime.now()

            # 1. Vérifier si on_ready a été appelé
            if not bot.ready_called:
                consecutive_failures += 1
                logger.warning(f"⚠️ on_ready n'a pas encore été appelé (échec {consecutive_failures}/{max_consecutive_failures})")
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ on_ready n'a jamais été appelé après plusieurs vérifications. Redémarrage du bot...")
                    os._exit(1)
                continue

            # 2. Vérifier la latence
            if bot.latency == float('inf') or bot.latency > 30.0:
                consecutive_failures += 1
                logger.warning(f"⚠️ Latence problématique: {bot.latency}s (échec {consecutive_failures}/{max_consecutive_failures})")
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ Latence critique détectée. Redémarrage du bot...")
                    os._exit(1)
                continue

            # 3. Vérifier si le bot est connecté
            if not bot.is_ready():
                consecutive_failures += 1
                logger.warning(f"⚠️ Bot non prêt (échec {consecutive_failures}/{max_consecutive_failures})")
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ Bot non prêt après plusieurs vérifications. Redémarrage...")
                    os._exit(1)
                continue

            # 4. Vérifier les tâches des cogs toutes les 15 minutes
            if (current_time - last_task_check).total_seconds() > 900:  # 15 minutes
                check_cog_tasks_health(bot)
                last_task_check = current_time

            # 5. Nettoyer les ressources périodiquement
            resource_monitor.check_and_cleanup()

            # 6. Vérifier le heartbeat du serveur HTTP
            time_since_heartbeat = current_time - last_heartbeat
            if time_since_heartbeat > timedelta(minutes=10):
                logger.warning(f"⚠️ Aucun heartbeat HTTP depuis {time_since_heartbeat}")

            # Si on arrive ici, tout va bien
            if consecutive_failures > 0:
                logger.info(f"✅ Santé du bot rétablie après {consecutive_failures} échecs")
            consecutive_failures = 0

            logger.info(f"💚 Santé du bot: OK (latence: {bot.latency:.2f}s, requêtes HTTP: {request_count})")

        except Exception as e:
            consecutive_failures += 1
            logger.error(f"❌ Erreur lors de la vérification de santé: {e} (échec {consecutive_failures}/{max_consecutive_failures})")
            if consecutive_failures >= max_consecutive_failures:
                logger.critical("❌ Trop d'erreurs lors des vérifications de santé. Redémarrage...")
                os._exit(1)

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
                    logger.info(f"🏓 Self-ping réussi (localhost)")
                    continue
            except:
                pass

            # Si localhost ne marche pas, essayer l'URL Render si disponible
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                try:
                    response = requests.get(f"{render_url}/ping", timeout=10)
                    if response.status_code == 200:
                        logger.info(f"🏓 Self-ping réussi (Render URL)")
                        continue
                except:
                    pass

            logger.warning("⚠️ Self-ping échoué")

        except Exception as e:
            logger.error(f"❌ Erreur lors du self-ping: {e}")

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

class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_server_thread = None
        self.health_check_thread = None
        self.self_ping_thread = None
        self.ready_called = False
        self.health_monitor = get_health_monitor(self)

    async def setup_hook(self):
        extensions = [
            'cogs.inventaire',
            'cogs.Cards',
            'cogs.RPTracker',
            'cogs.bump',
            'cogs.vocabulaire',
            'cogs.souselement',
            'cogs.ticket',
            'cogs.validation',
            'cogs.InactiveUserTracker',
            'cogs.excès',
            'cogs.scene_surveillance',
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Extension {ext} chargée")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {ext} : {e}")
                traceback.print_exc()

        try:
            await self.tree.sync()
            logger.info("Commandes synchronisées avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation des commandes : {e}")
            traceback.print_exc()

        logger.info("Tous les cogs ont été chargés")

    def start_http_server_thread(self):
        self.http_server_thread = threading.Thread(target=start_http_server, daemon=True)
        self.http_server_thread.start()
        logger.info("Thread du serveur HTTP démarré")

    def start_health_check_thread(self):
        self.health_check_thread = threading.Thread(target=check_bot_health, args=(self,), daemon=True)
        self.health_check_thread.start()
        logger.info("Thread de surveillance de santé démarré")

    def start_self_ping_thread(self):
        self.self_ping_thread = threading.Thread(target=self_ping, daemon=True)
        self.self_ping_thread.start()
        logger.info("Thread de self-ping démarré")

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Erreur non gérée dans l'événement {event_method}")
        logger.error(traceback.format_exc())
        with open('error.log', 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Erreur dans {event_method}: {traceback.format_exc()}\n")

    async def on_disconnect(self):
        """Événement appelé lors de la déconnexion."""
        logger.warning("🔌 Déconnecté de Discord")
        self.ready_called = False  # Marquer comme non prêt
        if self.health_monitor:
            self.health_monitor.metrics.record_connection_event('disconnect')

    async def on_resumed(self):
        """Événement appelé lors de la reconnexion."""
        logger.info("🔄 Reconnexion réussie à Discord")
        self.ready_called = True  # Marquer comme prêt

        if self.health_monitor:
            self.health_monitor.metrics.record_connection_event('resumed')

        # Vérifier et redémarrer les threads si nécessaire
        await self._check_and_restart_threads()

    async def _check_and_restart_threads(self):
        """Vérifie et redémarre les threads si nécessaire."""
        try:
            if not self.http_server_thread or not self.http_server_thread.is_alive():
                logger.warning("⚠️ Thread serveur HTTP mort, redémarrage...")
                self.start_http_server_thread()

            if not self.health_check_thread or not self.health_check_thread.is_alive():
                logger.warning("⚠️ Thread surveillance santé mort, redémarrage...")
                self.start_health_check_thread()

            if not self.self_ping_thread or not self.self_ping_thread.is_alive():
                logger.warning("⚠️ Thread self-ping mort, redémarrage...")
                self.start_self_ping_thread()

        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification des threads: {e}")

def main():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # Configuration plus robuste pour Discord.py
    bot = CustomBot(
        command_prefix='!',
        intents=intents,
        heartbeat_timeout=60.0,  # Timeout pour le heartbeat
        guild_ready_timeout=10.0,  # Timeout pour les guildes
        max_messages=5000,  # Cache plus généreux pour les fonctionnalités existantes
        chunk_guilds_at_startup=False,  # Éviter de charger tous les membres au démarrage
        member_cache_flags=discord.MemberCacheFlags.from_intents(intents)  # Cache adapté aux intents
    )
    bot.start_http_server_thread()
    bot.start_health_check_thread()
    bot.start_self_ping_thread()

    async def on_ready():
        bot.ready_called = True
        logger.info(f'🤖 Connecté en tant que {bot.user.name}')
        logger.info(f'🆔 ID du bot : {bot.user.id}')
        logger.info(f'🏓 Latence actuelle : {bot.latency:.2f}s')

        if bot.health_monitor:
            bot.health_monitor.metrics.record_connection_event('ready')
            bot.health_monitor.start_monitoring()

        # Vérifier et redémarrer les threads si nécessaire
        await bot._check_and_restart_threads()
        logger.info("🚀 Bot complètement opérationnel !")

    bot.add_listener(on_ready, 'on_ready')

    while True:
        try:
            logger.info("Démarrage du bot...")
            bot.run(os.getenv('DISCORD_TOKEN'))
        except Exception as e:
            logger.critical(f"Erreur lors de l'exécution du bot : {e}")
            traceback.print_exc()
            logger.info("Tentative de reconnexion dans 60 secondes...")
            time.sleep(60)
        else:
            logger.info("Le bot s'est arrêté normalement.")
            break

if __name__ == '__main__':
    main()
