import os
import threading
import traceback
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
import time
import asyncio
from datetime import datetime
from server import start_http_server
from monitoring_minimal import check_bot_health_minimal, self_ping_minimal

# Configuration des logs - moins verbose
logging.basicConfig(
    level=logging.INFO,  # INFO au lieu de WARNING
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('bot')

# Charger les variables d'environnement
load_dotenv()


class StableBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready_called = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3  # Limité pour éviter les boucles

    async def setup_hook(self):
        """Charge les cogs avec gestion d'erreurs robuste."""
        extensions = [
            'cogs.Cards',
            'cogs.RPTracker', 
            'cogs.scene_surveillance',
            'cogs.bump',
            'cogs.validation',
            'cogs.InactiveUserTracker',
            # Cogs optionnels qui peuvent échouer
            'cogs.inventaire',
            'cogs.vocabulaire',
            'cogs.souselement',
            'cogs.ticket',
            'cogs.excès',
        ]
        
        critical_cogs = ['cogs.Cards', 'cogs.RPTracker', 'cogs.scene_surveillance']
        loaded_count = 0
        critical_loaded = 0
        
        for ext in extensions:
            try:
                await self.load_extension(ext)
                loaded_count += 1
                if ext in critical_cogs:
                    critical_loaded += 1
                logger.info(f"✅ Extension {ext} chargée")
            except Exception as e:
                if ext in critical_cogs:
                    logger.error(f"❌ CRITIQUE: Échec de {ext}: {e}")
                else:
                    logger.warning(f"⚠️ Optionnel: Échec de {ext}: {e}")
        
        logger.info(f"📊 Extensions chargées: {loaded_count}/{len(extensions)} ({critical_loaded}/{len(critical_cogs)} critiques)")
        
        try:
            await self.tree.sync()
            logger.info("✅ Commandes synchronisées")
        except Exception as e:
            logger.warning(f"⚠️ Erreur sync commandes: {e}")



    async def on_disconnect(self):
        """Gestion simple des déconnexions."""
        logger.warning("🔌 Déconnecté de Discord")
        self.ready_called = False

    async def on_resumed(self):
        """Gestion simple des reconnexions."""
        logger.info("🔄 Reconnecté à Discord")
        self.ready_called = True
        self.connection_attempts = 0

    async def on_error(self, event_method, *args, **kwargs):
        """Gestion d'erreur simplifiée."""
        error_msg = f"Erreur dans {event_method}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())

class BotManagerStable:
    """Gestionnaire de bot simplifié et stable."""
    
    def __init__(self):
        self.bot = None
        self.should_restart = True
        
    def create_bot(self):
        """Créer le bot avec configuration optimisée."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        bot = StableBot(
            command_prefix='!',
            intents=intents,
            heartbeat_timeout=120.0,  # Très tolérant
            guild_ready_timeout=60.0,
            max_messages=500,  # Réduire l'usage mémoire
            chunk_guilds_at_startup=False
        )
        
        @bot.event
        async def on_ready():
            bot.ready_called = True
            logger.info(f'🤖 Bot connecté: {bot.user.name}')
            logger.info(f'🏓 Latence: {bot.latency:.2f}s')
            logger.info("🚀 Bot opérationnel!")

        return bot
    
    def start_support_threads(self):
        """Démarrer uniquement les threads essentiels."""
        # Thread serveur HTTP
        http_thread = threading.Thread(target=start_http_server, daemon=True)
        http_thread.start()
        logger.info("📡 Serveur HTTP démarré")
        
        # Thread monitoring minimal (sans redémarrage automatique)
        def monitoring_wrapper():
            time.sleep(60)  # Attendre que le bot soit prêt
            if self.bot and not self.bot.is_closed():
                check_bot_health_minimal(self.bot)
        
        monitor_thread = threading.Thread(target=monitoring_wrapper, daemon=True)
        monitor_thread.start()
        logger.info("🏥 Monitoring minimal démarré")
        
        # Thread self-ping minimal
        ping_thread = threading.Thread(target=self_ping_minimal, daemon=True)
        ping_thread.start()
        logger.info("🏓 Self-ping minimal démarré")
    
    
    
    def run_bot(self):
        """Exécuter le bot de manière stable."""
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            try:
                logger.info(f"🚀 Démarrage bot (tentative {attempt + 1}/{max_attempts})")
                self.bot.run(os.getenv('DISCORD_TOKEN'))
                break  # Sortie propre
                
            except discord.LoginFailure:
                logger.critical("❌ Token Discord invalide!")
                break
                
            except Exception as e:
                logger.error(f"❌ Erreur bot: {e}")
                attempt += 1
                if attempt < max_attempts:
                    delay = 60 * attempt  # 1, 2, 3 minutes
                    logger.info(f"⏳ Attente {delay}s avant nouvelle tentative...")
                    time.sleep(delay)
        
        if attempt >= max_attempts:
            logger.critical("❌ Échec définitif du bot")
    
    def start(self):
        """Démarrer le gestionnaire."""
        logger.info("🎬 Démarrage BotManagerStable...")
        
        self.start_support_threads()
        self.bot = self.create_bot()
        
        try:
            self.run_bot()
        except KeyboardInterrupt:
            logger.info("🛑 Arrêt demandé")
            if self.bot and not self.bot.is_closed():
                asyncio.run(self.bot.close())

def main():
    """Point d'entrée stable."""
    # Vérification des variables d'environnement au démarrage
    discord_token = os.getenv('DISCORD_TOKEN')
    if not discord_token or discord_token == 'YOUR_DISCORD_TOKEN_HERE':
        logger.critical("❌ DISCORD_TOKEN manquant ou invalide dans .env!")
        logger.info("📝 Configurez votre token Discord dans le fichier .env")
        return
    
    service_account = os.getenv('SERVICE_ACCOUNT_JSON', '{}')
    if service_account == '{}':
        logger.warning("⚠️ SERVICE_ACCOUNT_JSON non configuré - cogs Google Sheets en mode dégradé")
    
    manager = BotManagerStable()
    manager.start()

if __name__ == '__main__':
    main()
