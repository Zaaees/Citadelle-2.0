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

# Import de l'état du bot centralisé
from bot_state import update_bot_state, get_bot_state, reset_bot_state


class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready_called = False
        # Initialisation différée du health monitor
        self.health_monitor = None
        self._init_health_monitor()
        
    def _init_health_monitor(self):
        """Initialise le health monitor de manière sécurisée."""
        try:
            if HEALTH_MONITOR_AVAILABLE:
                self.health_monitor = get_health_monitor(self)
                logger.info("✅ Health monitor initialisé")
            else:
                logger.info("⚠️ Health monitor non disponible")
        except Exception as e:
            logger.warning(f"Impossible d'initialiser le health monitor: {e}")
            self.health_monitor = None
        self.connection_attempts = 0
        self.max_connection_attempts = 5

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
            except RuntimeError as e:
                logger.error(f"RuntimeError lors du chargement de {ext} : {e}")
                # Ne pas arrêter le bot pour une erreur de cog
                continue
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {ext} : {e}")
                traceback.print_exc()
                # Continuer avec les autres cogs

        try:
            await self.tree.sync()
            logger.info("Commandes synchronisées avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation des commandes : {e}")
            traceback.print_exc()

        logger.info("Tous les cogs ont été chargés")



    async def on_disconnect(self):
        """Événement appelé lors de la déconnexion."""
        logger.warning("🔌 Déconnecté de Discord")
        self.ready_called = False
        update_bot_state('disconnected', last_disconnect=datetime.now())
        if self.health_monitor:
            self.health_monitor.metrics.record_connection_event('disconnect')

    async def on_resumed(self):
        """Événement appelé lors de la reconnexion."""
        logger.info("🔄 Reconnexion réussie à Discord")
        self.ready_called = True
        self.connection_attempts = 0  # Reset le compteur
        update_bot_state('connected', last_ready=datetime.now(), latency=self.latency)
        
        if self.health_monitor:
            self.health_monitor.metrics.record_connection_event('resumed')

    async def on_error(self, event_method, *args, **kwargs):
        """Gestion d'erreur améliorée."""
        error_msg = f"Erreur non gérée dans l'événement {event_method}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # Mettre à jour l'état avec l'erreur
        current_state = get_bot_state()
        update_bot_state('error', error_count=current_state['error_count'] + 1)
        
        with open('error.log', 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {error_msg}: {traceback.format_exc()}\n")

class BotManager:
    """Gestionnaire pour le bot avec redémarrage automatique."""
    
    def __init__(self):
        self.bot = None
        self.http_server_thread = None
        self.health_check_thread = None
        self.self_ping_thread = None
        self.should_restart = True
        self.max_restart_attempts = 5  # Limiter les tentatives
        self.restart_delay = 30  # secondes
        
    def create_bot(self):
        """Créer une nouvelle instance du bot."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        # Configuration plus agressive pour la robustesse
        bot = CustomBot(
            command_prefix='!',
            intents=intents,
            heartbeat_timeout=30.0,  # Plus agressif
            guild_ready_timeout=5.0,  # Plus rapide
            max_messages=5000,
            chunk_guilds_at_startup=False,
            member_cache_flags=discord.MemberCacheFlags.from_intents(intents)
        )
        
        async def on_ready():
            bot.ready_called = True
            bot.connection_attempts = 0
            update_bot_state('connected', last_ready=datetime.now(), latency=bot.latency)
            
            logger.info(f'🤖 Connecté en tant que {bot.user.name}')
            logger.info(f'🆔 ID du bot : {bot.user.id}')
            logger.info(f'🏓 Latence actuelle : {bot.latency:.2f}s')

            if bot.health_monitor:
                bot.health_monitor.metrics.record_connection_event('ready')
                bot.health_monitor.start_monitoring()

            logger.info("🚀 Bot complètement opérationnel !")

        bot.add_listener(on_ready, 'on_ready')
        return bot
    
    def start_threads(self):
        """Démarrer les threads de support (serveur, monitoring, ping)."""
        # Thread serveur HTTP (indépendant du bot)
        if not self.http_server_thread or not self.http_server_thread.is_alive():
            self.http_server_thread = threading.Thread(target=start_http_server, daemon=True)
            self.http_server_thread.start()
            logger.info("📡 Thread serveur HTTP démarré")

        # Thread monitoring santé
        if not self.health_check_thread or not self.health_check_thread.is_alive():
            self.health_check_thread = threading.Thread(
                target=self._health_check_wrapper, daemon=True
            )
            self.health_check_thread.start()
            logger.info("🏥 Thread monitoring santé démarré")

        # Thread self-ping
        if not self.self_ping_thread or not self.self_ping_thread.is_alive():
            self.self_ping_thread = threading.Thread(target=self_ping, daemon=True)
            self.self_ping_thread.start()
            logger.info("🏓 Thread self-ping démarré")
    
    def _health_check_wrapper(self):
        """Wrapper pour le health check qui gère les restarts."""
        while self.should_restart:
            try:
                # Thread-safe check du bot
                current_bot = self.bot
                if current_bot and current_bot.is_closed():
                    logger.warning("🔄 Bot fermé détecté, tentative de redémarrage...")
                    self._restart_bot_async()
                    time.sleep(self.restart_delay)
                    continue
                    
                if current_bot:
                    try:
                        check_bot_health(current_bot)
                    except Exception as e:
                        logger.error(f"❌ Erreur dans health check: {e}")
                        # Si erreur critique, marquer pour redémarrage
                        if "critical" in str(e).lower():
                            logger.error("Erreur critique détectée, redémarrage programmé")
                            self._restart_bot_async()
                            time.sleep(self.restart_delay)
                            continue
                
            except Exception as e:
                logger.error(f"❌ Erreur dans health check wrapper: {e}")
                
            time.sleep(60)  # Vérification plus fréquente
    
    def _restart_bot_async(self):
        """Redémarrer le bot de manière asynchrone avec protection contre les boucles infinies."""
        current_state = get_bot_state()
        restart_count = current_state['restart_count']
        
        # Protection contre les redémarrages excessifs
        if restart_count >= 5:
            logger.critical(f"❌ Trop de redémarrages ({restart_count}). Arrêt pour éviter les boucles infinies.")
            self.should_restart = False
            update_bot_state('error', error_count=current_state['error_count'] + 1)
            return
            
        logger.info(f"🔄 Redémarrage #{restart_count + 1} en cours...")
        update_bot_state('initializing', restart_count=restart_count + 1)
        
        # Fermer proprement l'ancien bot avec timeout
        old_bot = self.bot
        if old_bot and not old_bot.is_closed():
            try:
                # Essayer de fermer avec timeout
                if hasattr(old_bot, 'loop') and old_bot.loop and not old_bot.loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(old_bot.close(), old_bot.loop)
                    future.result(timeout=10.0)  # Timeout de 10 secondes
                    logger.info("✅ Ancien bot fermé proprement")
                else:
                    logger.warning("⚠️ Loop de l'ancien bot fermée, nettoyage forcé")
                    
            except asyncio.TimeoutError:
                logger.error("❌ Timeout lors de la fermeture de l'ancien bot")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la fermeture du bot: {e}")
                
        # Pause avant redémarrage pour éviter la surcharge
        time.sleep(2)
        
        # Réinitialiser l'état pour le nouveau bot
        reset_bot_state()
        
        try:
            self.bot = self.create_bot()
            
            # Démarrer le nouveau bot dans un thread séparé
            bot_thread = threading.Thread(target=self._run_bot, daemon=True)
            bot_thread.start()
            logger.info("🚀 Nouveau bot créé et démarré")
            
        except Exception as e:
            logger.critical(f"❌ Impossible de créer le nouveau bot: {e}")
            update_bot_state('error')
            self.should_restart = False
    
    def _run_bot(self):
        """Exécuter le bot avec gestion d'erreurs."""
        max_attempts = 5
        attempt = 0
        
        while attempt < max_attempts and self.should_restart:
            try:
                update_bot_state('connecting')
                logger.info(f"🚀 Démarrage du bot (tentative {attempt + 1}/{max_attempts})")
                self.bot.run(os.getenv('DISCORD_TOKEN'))
                break  # Si on arrive ici, le bot s'est fermé proprement
                
            except discord.LoginFailure:
                logger.critical("❌ Token Discord invalide!")
                update_bot_state('error')
                break
                
            except discord.HTTPException as e:
                logger.error(f"❌ Erreur HTTP Discord: {e}")
                attempt += 1
                if attempt < max_attempts:
                    delay = min(300, 30 * (2 ** attempt))  # Backoff exponentiel, max 5min
                    logger.info(f"⏳ Attente de {delay}s avant nouvelle tentative...")
                    time.sleep(delay)
                    
            except Exception as e:
                logger.critical(f"❌ Erreur critique du bot: {e}")
                traceback.print_exc()
                update_bot_state('error')
                attempt += 1
                if attempt < max_attempts:
                    time.sleep(60)
        
        if attempt >= max_attempts:
            logger.critical("❌ Échec définitif après plusieurs tentatives")
            update_bot_state('error')
    
    def start(self):
        """Démarrer le gestionnaire de bot."""
        logger.info("🎬 Démarrage du BotManager...")
        
        # Démarrer les threads de support en premier
        self.start_threads()
        
        # Créer et démarrer le bot
        self.bot = self.create_bot()
        bot_thread = threading.Thread(target=self._run_bot, daemon=False)
        bot_thread.start()
        
        # Attendre que le thread principal se termine
        try:
            bot_thread.join()
        except KeyboardInterrupt:
            logger.info("🛑 Arrêt demandé par l'utilisateur")
            self.should_restart = False
            if self.bot and not self.bot.is_closed():
                asyncio.run(self.bot.close())

def main():
    """Point d'entrée principal."""
    manager = BotManager()
    manager.start()

if __name__ == '__main__':
    main()
