# Charger les variables d'environnement
load_dotenv()

import os
import threading
import traceback
import logging
import discord
from discord.ext import commands
import time
import asyncio
from datetime import datetime
from server_unified import start_unified_server, backend_path
# Assurer que le backend est accessible pour tout le processus
import sys
if backend_path not in sys.path:
    sys.path.append(backend_path)
from server_minimal import update_bot_health
from watchdog_discord import create_watchdog, get_watchdog

# Configuration des logs - moins verbose
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('bot')


class StableBot(commands.Bot):
    """Bot Discord avec gestion robuste des connexions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready_called = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.last_ready_time = None
        self.consecutive_disconnects = 0
        self.watchdog = None
        self._activity_count = 0

    async def setup_hook(self):
        """Charge les cogs avec gestion d'erreurs robuste."""
        # Ordre prioritaire : cogs avec commandes slash d'abord
        extensions = [
            'cogs.Cards',              # /cartes
            'cogs.scene_surveillance', # /mj, /scenes_actives
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

                logger.error(f"🔍 Erreur détaillée lors du chargement de {ext}:")
                logger.error(f"   Type: {error_type}")
                logger.error(f"   Message: {error_str}")

                if "MalformedError" in error_str or "No key could be detected" in error_str:
                    logger.warning(f"⚠️ {ext}: Google Sheets non configuré - cog ignoré ({error_type})")
                elif "ModuleNotFoundError" in error_str:
                    logger.warning(f"⚠️ {ext}: Dépendance manquante - cog ignoré ({error_type})")
                elif ext in critical_cogs:
                    logger.error(f"❌ CRITIQUE: Échec de {ext}: {error_type}")
                    logger.error(f"🔍 Traceback: {traceback.format_exc()}")
                else:
                    logger.warning(f"⚠️ Optionnel: {ext} ignoré ({error_type})")
                    logger.warning(f"🔍 Traceback pour debug: {traceback.format_exc()}")

        logger.info(f"📊 Extensions chargées: {loaded_count}/{len(extensions)} ({critical_loaded}/{len(critical_cogs)} critiques)")

        # Synchronisation propre des commandes sans doublons
        try:
            guild_id = os.getenv('GUILD_ID')
            if guild_id:
                try:
                    guild = discord.Object(id=int(guild_id))
                    logger.info("🧹 Nettoyage des commandes du serveur...")
                    self.tree.clear_commands(guild=guild)

                    synced = await self.tree.sync(guild=guild)
                    logger.info(f"✅ {len(synced)} commandes synchronisées PROPREMENT pour serveur {guild_id}")
                except Exception as ge:
                    logger.error(f"❌ Erreur sync serveur spécifique: {ge}")
                    synced = await self.tree.sync()
                    logger.info(f"⚠️ Fallback: {len(synced)} commandes synchronisées globalement (1h délai)")
            else:
                synced = await self.tree.sync()
                logger.info(f"✅ {len(synced)} commandes synchronisées globalement (délai 1h)")
                logger.warning("💡 Configurez GUILD_ID dans .env pour sync instantanée!")

            if synced:
                commands_list = [cmd.name for cmd in synced]
                logger.info(f"🔍 Commandes synchronisées: {', '.join(commands_list)}")

        except Exception as e:
            logger.error(f"❌ Erreur critique sync commandes: {e}")
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")

    async def on_disconnect(self):
        """Gestion intelligente des déconnexions."""
        self.ready_called = False
        self.consecutive_disconnects += 1

        downtime = datetime.now() - self.last_ready_time if self.last_ready_time else None

        logger.warning(f"🔌 Déconnecté de Discord (#{self.consecutive_disconnects})")
        if downtime:
            logger.warning(f"⏱️ Temps de connexion avant déco: {downtime}")

        # Mettre à jour le statut de santé
        update_bot_health(healthy=True, discord_connected=False)

    async def on_resumed(self):
        """Gestion optimisée des reconnexions."""
        self.ready_called = True
        self.connection_attempts = 0
        self.consecutive_disconnects = 0
        self.last_ready_time = datetime.now()

        logger.info(f"🔄 Reconnecté à Discord (latence: {self.latency:.2f}s)")

        # Mettre à jour le statut de santé
        update_bot_health(healthy=True, discord_connected=True)

        # Notifier le watchdog
        if self.watchdog:
            self.watchdog.record_gateway_response()

    async def on_message(self, message):
        """Traite les messages et enregistre l'activité pour le watchdog."""
        # Enregistrer l'activité pour le watchdog (preuve que la connexion est vivante)
        if self.watchdog:
            self.watchdog.record_activity()

        self._activity_count += 1

        # Traiter les commandes normales
        await self.process_commands(message)

    async def on_error(self, event_method, *args, **kwargs):
        """Gestion d'erreur renforcée contre les crashes silencieux."""
        error_msg = f"❌ ERREUR CRITIQUE dans {event_method}"
        logger.error(error_msg)
        logger.error(f"🔍 Traceback complet: {traceback.format_exc()}")

        if args:
            logger.error(f"🔍 Arguments: {args}")
        if kwargs:
            logger.error(f"🔍 Keyword arguments: {kwargs}")

        try:
            if not self.is_closed():
                logger.warning("⚠️ Bot encore connecté après erreur, continuant...")
            else:
                logger.critical("💀 Bot fermé après erreur critique!")
        except Exception as e:
            logger.critical(f"💀 Impossible de vérifier l'état du bot: {e}")


class BotManagerStable:
    """Gestionnaire de bot avec watchdog intégré."""

    def __init__(self):
        self.bot = None
        self.should_restart = True
        self.watchdog = None

    def create_bot(self):
        """Créer le bot avec configuration optimisée pour stabilité maximale."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        bot = StableBot(
            command_prefix='!',
            intents=intents,
            heartbeat_timeout=180.0,      # 3 minutes - très tolérant
            guild_ready_timeout=120.0,    # 2 minutes pour les gros serveurs
            max_messages=100,             # Minimal pour économiser la mémoire
            chunk_guilds_at_startup=False,
            enable_debug_events=False,
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

            # Mettre à jour le statut de santé (Discord EST connecté)
            update_bot_health(healthy=True, discord_connected=True)

            # Créer et démarrer le watchdog Discord
            if not bot.watchdog:
                bot.watchdog = create_watchdog(
                    bot,
                    health_callback=lambda healthy: update_bot_health(
                        healthy=healthy,
                        discord_connected=healthy,
                        watchdog_status=bot.watchdog.get_status() if bot.watchdog else None
                    )
                )
                await bot.watchdog.start()
                logger.info("🐕 Watchdog Discord intégré au bot")

            logger.info("🚀 Bot ultra-robuste opérationnel avec watchdog!")

        return bot

    def start_support_threads(self):
        """Démarrer les threads de support."""
        # Serveur HTTP pour health checks ET API Backend
        server_thread = start_unified_server()
        logger.info("📡 Serveur Unifié (Bot + API) démarré")

        # Thread de log périodique pour vérifier que le bot tourne
        def periodic_status_log():
            while True:
                time.sleep(1800)  # Toutes les 30 minutes
                try:
                    if self.bot and self.bot.is_ready() and not self.bot.is_closed():
                        watchdog = get_watchdog()
                        status = watchdog.get_status() if watchdog else {}
                        logger.info(
                            f"📊 Status périodique - "
                            f"Latence: {self.bot.latency:.2f}s | "
                            f"Serveurs: {len(self.bot.guilds)} | "
                            f"Watchdog: {status.get('is_healthy', 'N/A')} | "
                            f"Reconnexions: {status.get('total_reconnections', 0)}"
                        )
                    else:
                        logger.warning("📊 Status périodique - Bot non prêt ou fermé")
                except Exception as e:
                    logger.error(f"❌ Erreur status périodique: {e}")

        status_thread = threading.Thread(target=periodic_status_log, daemon=True)
        status_thread.start()
        logger.info("📊 Logging de status périodique démarré")

    def run_bot(self):
        """Exécuter le bot avec récupération maximale."""
        max_attempts = 10  # Beaucoup de tentatives
        attempt = 0
        base_delay = 30  # Délai de base en secondes

        while attempt < max_attempts:
            try:
                logger.info(f"🚀 Démarrage bot (tentative {attempt + 1}/{max_attempts})")

                # Nettoyage préventif avant redémarrage
                if attempt > 0:
                    import gc
                    gc.collect()
                    logger.info("🧹 Nettoyage mémoire effectué")

                    # Recréer le bot si nécessaire
                    self.bot = self.create_bot()

                # Marquer comme sain avant démarrage (HTTP OK, Discord pas encore)
                update_bot_health(healthy=True, discord_connected=False)

                # Lancer le bot avec reconnexion automatique activée
                self.bot.run(os.getenv('DISCORD_TOKEN'), reconnect=True)

                # Si on arrive ici, le bot s'est arrêté proprement
                logger.info("🛑 Bot arrêté proprement")
                break

            except discord.LoginFailure as e:
                logger.critical(f"❌ Token Discord invalide: {e}")
                update_bot_health(healthy=False, discord_connected=False)
                break

            except discord.HTTPException as e:
                logger.error(f"❌ Erreur HTTP Discord: {e}")
                if "429" in str(e):  # Rate limit
                    delay = 300  # 5 minutes pour rate limit
                    logger.warning(f"🚦 Rate limit détecté, attente {delay}s")
                    time.sleep(delay)
                attempt += 1

            except discord.GatewayNotFound as e:
                logger.error(f"❌ Gateway Discord introuvable: {e}")
                delay = 60
                logger.warning(f"⏳ Attente {delay}s avant réessai...")
                time.sleep(delay)
                attempt += 1

            except discord.ConnectionClosed as e:
                logger.error(f"❌ Connexion fermée par Discord: {e}")
                # Backoff exponentiel avec cap
                delay = min(base_delay * (2 ** attempt), 600)
                logger.warning(f"⏳ Reconnexion dans {delay}s...")
                time.sleep(delay)
                attempt += 1

            except Exception as e:
                logger.error(f"❌ Erreur bot inattendue: {e}")
                logger.error(f"🔍 Traceback: {traceback.format_exc()}")

                attempt += 1
                if attempt < max_attempts:
                    # Délai exponentiel: 30s, 60s, 120s, 240s... max 10min
                    delay = min(base_delay * (2 ** (attempt - 1)), 600)
                    logger.info(f"⏳ Tentative {attempt}/{max_attempts} - Attente {delay}s...")
                    update_bot_health(healthy=False, discord_connected=False)
                    time.sleep(delay)

        if attempt >= max_attempts:
            logger.critical("❌ Échec définitif après toutes les tentatives")
            update_bot_health(healthy=False, discord_connected=False)
            # Attendre un peu puis quitter pour que Render redémarre le service
            time.sleep(30)
            raise SystemExit("Bot failed after max attempts")

    def start(self):
        """Démarrer le gestionnaire."""
        logger.info("🎬 Démarrage BotManagerStable avec Watchdog...")

        self.start_support_threads()
        self.bot = self.create_bot()

        try:
            self.run_bot()
        except KeyboardInterrupt:
            logger.info("🛑 Arrêt demandé par l'utilisateur")
            if self.bot and not self.bot.is_closed():
                asyncio.run(self.bot.close())
        except SystemExit as e:
            logger.critical(f"🛑 Arrêt système: {e}")
            raise


def main():
    """Point d'entrée stable."""
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE CITADELLE BOT v2.0 - MODE ULTRA-ROBUSTE")
    logger.info("=" * 60)

    # Vérification des variables d'environnement
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
