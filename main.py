import os
import threading
import traceback
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
import time
from utils.health_monitor import get_health_monitor
from server import start_http_server
from monitoring import check_bot_health, self_ping

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
cards_logger = logging.getLogger('cards')

# Charger les variables d'environnement
load_dotenv()


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
            'cogs.Surveillance_scene',
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
    bot.start_self_ping_thread()

    async def on_ready():
        bot.ready_called = True
        bot.start_health_check_thread()
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
