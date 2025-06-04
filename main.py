import os
import sys
import threading
import traceback
import logging
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv
import time

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

# Serveur HTTP minimal pour Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
        logger.info(f"GET request received at {self.path} from {self.client_address}")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache, no-store')
        self.end_headers()
        logger.info(f"HEAD request received at {self.path} from {self.client_address}")

    def log_message(self, format, *args):
        if args[0].startswith('HEAD') or args[0].startswith('GET'):
            logger.debug(f"{self.client_address[0]} - - [{time.strftime('%d/%b/%Y %H:%M:%S')}] {args[0]}")
        return

def start_http_server(stop_event, max_retries=5):
    """Start a simple HTTP server with retry logic.

    Parameters
    ----------
    max_retries : int, optional
        Number of times to retry starting the server before giving up.
        ``None`` means infinite retries. Defaults to 5.
    """

    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Port utilisé: {port}")

    attempts = 0
    server = None
    while not stop_event.is_set():
        try:
            server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
            server.timeout = 1
            logger.info(f"Serveur HTTP démarré avec succès sur le port {port}")
            while not stop_event.is_set():
                server.handle_request()
            break
        except Exception as e:
            attempts += 1
            logger.error(f"Erreur lors du démarrage du serveur : {e}")
            traceback.print_exc()
            if max_retries is not None and attempts >= max_retries:
                logger.critical("Nombre maximum de tentatives atteint. Abandon.")
                raise
            time.sleep(5)
            logger.info("Tentative de redémarrage du serveur HTTP...")
    if server is not None:
        server.server_close()

def check_bot_health(bot, stop_event):
    while not stop_event.is_set():
        if stop_event.wait(300):
            break
        if not bot.ready_called:
            logger.critical("on_ready n'a jamais été appelé. Fermeture du bot...")
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
            stop_event.set()
        elif bot.latency == float('inf'):
            logger.critical("Latence infinie détectée. Perte probable de connexion WebSocket.")
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
            stop_event.set()

class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_server_thread = None
        self.health_check_thread = None
        self.ready_called = False
        self.stop_event = threading.Event()

    async def setup_hook(self):
        try:
            await self.load_extension('cogs.inventaire')
            await self.load_extension('cogs.Cards')
            await self.load_extension('cogs.RPTracker')
            await self.load_extension('cogs.bump')
            await self.load_extension('cogs.vocabulaire')
            await self.load_extension('cogs.souselement')
            await self.load_extension('cogs.ticket')
            await self.load_extension('cogs.validation')
            await self.load_extension('cogs.InactiveUserTracker')
            await self.load_extension('cogs.excès')
            await self.tree.sync()
            logger.info("Commandes synchronisées avec succès")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des extensions: {e}")
            traceback.print_exc()

    def start_http_server_thread(self):
        self.http_server_thread = threading.Thread(target=start_http_server, args=(self.stop_event,), daemon=True)
        self.http_server_thread.start()
        logger.info("Thread du serveur HTTP démarré")

    def start_health_check_thread(self):
        self.health_check_thread = threading.Thread(target=check_bot_health, args=(self, self.stop_event), daemon=True)
        self.health_check_thread.start()
        logger.info("Thread de surveillance de santé démarré")

    def stop_threads(self):
        self.stop_event.set()
        if self.http_server_thread and self.http_server_thread.is_alive():
            self.http_server_thread.join(timeout=5)
        if self.health_check_thread and self.health_check_thread.is_alive():
            self.health_check_thread.join(timeout=5)
        logger.info("Threads arrêtés")

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Erreur non gérée dans l'événement {event_method}")
        logger.error(traceback.format_exc())
        with open('error.log', 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Erreur dans {event_method}: {traceback.format_exc()}\n")

def main():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    bot = CustomBot(command_prefix='!', intents=intents)
    bot.start_http_server_thread()
    bot.start_health_check_thread()

    async def on_ready():
        bot.ready_called = True
        logger.info(f'Connecté en tant que {bot.user.name}')
        logger.info(f'ID du bot : {bot.user.id}')
        if not bot.http_server_thread or not bot.http_server_thread.is_alive():
            logger.warning("Le thread du serveur HTTP n'est pas en cours d'exécution. Redémarrage...")
            bot.start_http_server_thread()
        if not bot.health_check_thread or not bot.health_check_thread.is_alive():
            logger.warning("Le thread de surveillance de santé n'est pas en cours d'exécution. Redémarrage...")
            bot.start_health_check_thread()

    async def on_disconnect():
        logger.warning("Déconnecté de Discord")

    async def on_resumed():
        logger.info("Reconnexion réussie à Discord")

    bot.add_listener(on_ready, 'on_ready')
    bot.add_listener(on_disconnect, 'on_disconnect')
    bot.add_listener(on_resumed, 'on_resumed')

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

    bot.stop_threads()

if __name__ == '__main__':
    main()
