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
from server_minimal import start_server_thread, update_bot_health
from monitoring_minimal import check_bot_health_minimal

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
        self.max_connection_attempts = 3
        self.last_ready_time = None
        self.consecutive_disconnects = 0

    async def setup_hook(self):
        """Charge les cogs avec gestion d'erreurs robuste."""
        # Ordre prioritaire : cogs avec commandes slash d'abord
        extensions = [
            'cogs.Cards',              # ✅ /cartes
            'cogs.scene_surveillance', # ✅ /mj, /scenes_actives  
            'cogs.RPTracker', 
            'cogs.bump',
            'cogs.validation',
            'cogs.InactiveUserTracker',
            'cogs.ticket',
            # Cogs optionnels qui PEUVENT échouer (Google Sheets)
            'cogs.souselement',        # /ajouter-sous-element, /sous-éléments
            'cogs.vocabulaire',        # /vocabulaire
            'cogs.excès',             # /excès
            'cogs.inventaire',
        ]
        
        # Cogs avec commandes slash critiques à charger absolument
        critical_cogs = ['cogs.Cards', 'cogs.scene_surveillance']
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
                error_type = type(e).__name__
                error_str = str(e)
                
                # Log l'erreur complète pour debugging
                logger.error(f"🔍 Erreur détaillée lors du chargement de {ext}:")
                logger.error(f"   Type: {error_type}")
                logger.error(f"   Message: {error_str}")
                
                if "MalformedError" in error_str or "No key could be detected" in error_str:
                    logger.warning(f"⚠️ {ext}: Google Sheets non configuré - cog ignoré ({error_type})")
                elif "ModuleNotFoundError" in error_str:
                    logger.warning(f"⚠️ {ext}: Dépendance manquante - cog ignoré ({error_type})")
                elif ext in critical_cogs:
                    logger.error(f"❌ CRITIQUE: Échec de {ext}: {error_type}")
                    logger.error(f"🔍 Détails: {e}")
                    import traceback
                    logger.error(f"🔍 Traceback: {traceback.format_exc()}")
                else:
                    logger.warning(f"⚠️ Optionnel: {ext} ignoré ({error_type})")
                    # Afficher quand même le traceback pour les cogs optionnels pour debug
                    import traceback
                    logger.warning(f"🔍 Traceback pour debug: {traceback.format_exc()}")
        
        logger.info(f"📊 Extensions chargées: {loaded_count}/{len(extensions)} ({critical_loaded}/{len(critical_cogs)} critiques)")
        
        # Synchronisation propre des commandes sans doublons
        try:
            guild_id = os.getenv('GUILD_ID')
            if guild_id:
                try:
                    guild = discord.Object(id=int(guild_id))
                    # Nettoyer d'abord les commandes du serveur pour éviter les doublons
                    logger.info("🧹 Nettoyage des commandes du serveur...")
                    self.tree.clear_commands(guild=guild)
                    
                    # Synchronisation propre sur le serveur (instantané)
                    synced = await self.tree.sync(guild=guild)
                    logger.info(f"✅ {len(synced)} commandes synchronisées PROPREMENT pour serveur {guild_id}")
                except Exception as ge:
                    logger.error(f"❌ Erreur sync serveur spécifique: {ge}")
                    # Fallback sur sync globale
                    synced = await self.tree.sync()
                    logger.info(f"⚠️ Fallback: {len(synced)} commandes synchronisées globalement (1h délai)")
            else:
                # Pas de GUILD_ID configuré, sync globale uniquement
                synced = await self.tree.sync()
                logger.info(f"✅ {len(synced)} commandes synchronisées globalement (délai 1h)")
                logger.warning("💡 Configurez GUILD_ID dans .env pour sync instantanée!")
            
            # Lister les commandes synchronisées pour diagnostic
            if synced:
                commands_list = [cmd.name for cmd in synced]
                logger.info(f"🔍 Commandes synchronisées: {', '.join(commands_list)}")
                    
        except Exception as e:
            logger.error(f"❌ Erreur critique sync commandes: {e}")
            logger.error("🔍 Vérifiez les permissions bot (applications.commands scope)")
            import traceback
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")



    async def on_disconnect(self):
        """Gestion intelligente des déconnexions."""
        self.ready_called = False
        self.consecutive_disconnects += 1
        
        # Temps depuis la dernière connexion réussie
        downtime = datetime.now() - self.last_ready_time if self.last_ready_time else None
        
        logger.warning(f"🔌 Déconnecté de Discord (#{self.consecutive_disconnects})")
        if downtime:
            logger.warning(f"⏱️ Temps de connexion avant déco: {downtime}")
        
        # Marquer comme malsain pour health check
        update_bot_health(healthy=False)

    async def on_resumed(self):
        """Gestion optimisée des reconnexions."""
        self.ready_called = True
        self.connection_attempts = 0
        self.consecutive_disconnects = 0
        self.last_ready_time = datetime.now()
        
        logger.info(f"🔄 Reconnecté à Discord (latence: {self.latency:.2f}s)")
        
        # Marquer comme sain pour health check
        update_bot_health(healthy=True)

    async def on_error(self, event_method, *args, **kwargs):
        """Gestion d'erreur renforcée contre les crashes silencieux."""
        error_msg = f"❌ ERREUR CRITIQUE dans {event_method}"
        logger.error(error_msg)
        logger.error(f"🔍 Traceback complet: {traceback.format_exc()}")
        
        # Log détaillé pour debugging
        if args:
            logger.error(f"🔍 Arguments: {args}")
        if kwargs:
            logger.error(f"🔍 Keyword arguments: {kwargs}")
        
        # Essayer de ne pas crasher le bot
        try:
            if not self.is_closed():
                logger.warning("⚠️ Bot encore connecté après erreur, continuant...")
            else:
                logger.critical("💀 Bot fermé après erreur critique!")
        except Exception as e:
            logger.critical(f"💀 Impossible de vérifier l'état du bot: {e}")

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
            heartbeat_timeout=180.0,  # Ultra-tolérant: 3 minutes
            guild_ready_timeout=120.0,  # 2 minutes pour les gros serveurs
            max_messages=100,  # Minimal pour économiser la mémoire
            chunk_guilds_at_startup=False,
            enable_debug_events=False,  # Réduire le spam de logs
            assume_unsync_clock=False
        )
        
        @bot.event
        async def on_ready():
            bot.ready_called = True
            bot.last_ready_time = datetime.now()
            bot.consecutive_disconnects = 0
            
            logger.info(f'🤖 Bot connecté: {bot.user.name}')
            logger.info(f'🏓 Latence: {bot.latency:.2f}s')
            logger.info(f'🌐 Serveurs: {len(bot.guilds)}')
            logger.info("🚀 Bot ultra-robuste opérationnel!")
            
            # Marquer comme sain
            update_bot_health(healthy=True)

        return bot
    
    def start_support_threads(self):
        """Démarrer les threads optimisés pour Web Service ultra-robuste."""
        # Serveur HTTP minimal
        server_thread = start_server_thread()
        logger.info("📡 Serveur HTTP minimal démarré")
        
        # Monitoring avec heartbeat intelligent
        def monitoring_wrapper():
            time.sleep(90)  # Plus de temps pour l'initialisation complète
            if self.bot and not self.bot.is_closed():
                check_bot_health_minimal(self.bot)
        
        monitor_thread = threading.Thread(target=monitoring_wrapper, daemon=True)
        monitor_thread.start()
        logger.info("🏥 Monitoring ultra-robuste démarré")
        
        # Heartbeat périodique pour maintenir la connexion
        def heartbeat_keeper():
            while True:
                time.sleep(600)  # 10 minutes
                try:
                    if self.bot and self.bot.is_ready() and not self.bot.is_closed():
                        # Vérifier que le loop existe et n'est pas fermé
                        if self.bot.loop and not self.bot.loop.is_closed():
                            # Ping silencieux pour maintenir la connexion
                            asyncio.run_coroutine_threadsafe(
                                self.bot.change_presence(), self.bot.loop
                            )
                            logger.debug("💓 Heartbeat keepalive envoyé")
                        else:
                            logger.warning("⚠️ Bot loop is closed, skipping heartbeat")
                except Exception as e:
                    logger.debug(f"⚠️ Heartbeat failed: {e}")
        
        heartbeat_thread = threading.Thread(target=heartbeat_keeper, daemon=True)
        heartbeat_thread.start()
        logger.info("💓 Heartbeat keepalive démarré")
    
    
    
    def run_bot(self):
        """Exécuter le bot avec récupération maximale."""
        max_attempts = 5  # Plus de tentatives
        attempt = 0
        
        while attempt < max_attempts:
            try:
                logger.info(f"🚀 Démarrage bot ultra-robuste (tentative {attempt + 1}/{max_attempts})")
                
                # Nettoyage préventif avant redémarrage
                if attempt > 0:
                    logger.info("🧹 Nettoyage des ressources avant redémarrage...")
                    # Fermer proprement le bot précédent
                    if self.bot and not self.bot.is_closed():
                        try:
                            asyncio.run(self.bot.close())
                            logger.info("✅ Bot précédent fermé proprement")
                        except Exception as close_error:
                            logger.warning(f"⚠️ Erreur lors de la fermeture du bot: {close_error}")

                    # Nettoyer le cache et les connexions
                    import gc
                    gc.collect()
                    logger.info("✅ Garbage collection effectué")

                    # Recréer une instance fraîche du bot
                    self.bot = self.create_bot()
                    logger.info("✅ Nouvelle instance du bot créée")
                
                # Marquer comme sain avant démarrage
                update_bot_health(healthy=True)
                
                self.bot.run(os.getenv('DISCORD_TOKEN'), reconnect=True)
                break  # Sortie propre
                
            except discord.LoginFailure as e:
                logger.critical(f"❌ Token Discord invalide: {e}")
                update_bot_health(healthy=False)
                break
            
            except discord.HTTPException as e:
                logger.error(f"❌ Erreur HTTP Discord: {e}")
                if "429" in str(e):  # Rate limit
                    delay = 300  # 5 minutes pour rate limit
                    logger.warning(f"🚦 Rate limit détecté, attente {delay}s")
                    time.sleep(delay)
                attempt += 1
                
            except Exception as e:
                logger.error(f"❌ Erreur bot inattendue: {e}")
                logger.error(f"🔍 Traceback: {traceback.format_exc()}")
                
                attempt += 1
                if attempt < max_attempts:
                    # Délai progressif: 30s, 60s, 120s, 240s
                    delay = min(30 * (2 ** attempt), 300)
                    logger.info(f"⏳ Tentative {attempt}/{max_attempts} - Attente {delay}s...")
                    update_bot_health(healthy=False)
                    time.sleep(delay)
        
        if attempt >= max_attempts:
            logger.critical("❌ Échec définitif après toutes les tentatives")
            update_bot_health(healthy=False)
    
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
