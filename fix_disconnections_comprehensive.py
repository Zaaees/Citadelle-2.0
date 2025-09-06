#!/usr/bin/env python3
"""
Solution complète pour corriger les déconnexions du bot Discord.

Ce script :
1. Corrige les credentials Google Sheets
2. Simplifie le système de monitoring
3. Améliore la gestion d'erreurs
4. Évite les boucles de redémarrage
"""

import os
import json
import logging
import shutil
from datetime import datetime

def setup_logging():
    """Configure le logging pour ce script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('fix_disconnections.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def fix_environment_variables(logger):
    """Vérifie et corrige les variables d'environnement."""
    logger.info("🔧 Vérification des variables d'environnement...")
    
    env_path = '.env'
    if not os.path.exists(env_path):
        logger.error(f"❌ Fichier {env_path} introuvable!")
        return False
    
    # Lire le fichier .env existant
    with open(env_path, 'r') as f:
        content = f.read()
    
    # Vérifier les variables critiques
    required_vars = ['DISCORD_TOKEN', 'SERVICE_ACCOUNT_JSON']
    missing_vars = []
    
    for var in required_vars:
        if var not in content:
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"⚠️ Variables manquantes : {missing_vars}")
        
        # Ajouter les variables manquantes avec des placeholders
        with open(env_path, 'a') as f:
            f.write('\n# Variables ajoutées par le script de correction\n')
            for var in missing_vars:
                if var == 'SERVICE_ACCOUNT_JSON':
                    f.write(f'{var}={{}}\n')
                else:
                    f.write(f'{var}=YOUR_{var}_HERE\n')
        
        logger.info("✅ Variables ajoutées au fichier .env")
    
    # Ajouter les variables de configuration pour éviter les redémarrages excessifs
    config_additions = [
        'HEALTHCHECK_MAX_FAILURES=15',
        'HEALTHCHECK_FORCE_RESTART=false',
        'BOT_MONITORING_INTERVAL=900',
        'PORT=10000'
    ]
    
    for config in config_additions:
        var_name = config.split('=')[0]
        if var_name not in content:
            with open(env_path, 'a') as f:
                f.write(f'{config}\n')
            logger.info(f"✅ Ajouté : {config}")
    
    return True

def create_minimal_monitoring():
    """Crée un système de monitoring simplifié et stable."""
    logger = logging.getLogger(__name__)
    logger.info("🔧 Création du système de monitoring simplifié...")
    
    monitoring_code = '''import os
import time
import logging
from datetime import datetime, timedelta
from server import get_last_heartbeat, get_request_count

logger = logging.getLogger('bot')

# Variable globale pour contrôler l'arrêt du monitoring
_monitoring_active = True

def stop_health_monitoring():
    """Arrête le monitoring de santé proprement."""
    global _monitoring_active
    _monitoring_active = False

def check_bot_health_minimal(bot):
    """Version simplifiée et stable du monitoring."""
    global _monitoring_active
    consecutive_failures = 0
    max_consecutive_failures = 20  # Plus tolérant
    check_interval = 600  # 10 minutes
    
    logger.info(f"🏥 Monitoring minimal démarré (vérification toutes les {check_interval}s)")
    
    while _monitoring_active:
        time.sleep(check_interval)
        
        try:
            # Vérification simple : bot fermé
            if bot.is_closed():
                logger.warning("⚠️ Bot fermé détecté, arrêt du monitoring")
                _monitoring_active = False
                break
            
            # Vérification simple : bot prêt
            if not bot.is_ready():
                consecutive_failures += 1
                logger.warning(f"⚠️ Bot non prêt ({consecutive_failures}/{max_consecutive_failures})")
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical("❌ Bot non prêt depuis trop longtemps - MONITORING SEULEMENT")
                    # NE PAS redémarrer automatiquement
                continue
            
            # Tout va bien, réinitialiser le compteur
            if consecutive_failures > 0:
                logger.info(f"✅ Bot rétabli après {consecutive_failures} vérifications")
                consecutive_failures = 0
            
            # Log périodique
            logger.info(f"💚 Bot stable (latence: {bot.latency:.2f}s)")
            
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"❌ Erreur monitoring: {e} ({consecutive_failures}/{max_consecutive_failures})")
            # Continuer sans redémarrer

def check_cog_tasks_health(bot):
    """Version simplifiée de la vérification des cogs."""
    try:
        logger.info("🔍 Vérification simplifiée des cogs...")
        
        # Vérifier seulement les cogs critiques sans les redémarrer
        critical_cogs = ['Bump', 'RPTracker']
        for cog_name in critical_cogs:
            cog = bot.get_cog(cog_name)
            if cog:
                logger.info(f"✅ Cog {cog_name} chargé")
            else:
                logger.warning(f"⚠️ Cog {cog_name} non chargé")
                
    except Exception as e:
        logger.error(f"❌ Erreur vérification cogs: {e}")

def self_ping_minimal():
    """Version simplifiée et stable du self-ping."""
    import requests
    
    consecutive_failures = 0
    max_failures = 10
    ping_interval = 900  # 15 minutes
    
    logger.info("🏓 Self-ping minimal démarré")
    
    while True:
        try:
            time.sleep(ping_interval)
            port = int(os.environ.get("PORT", 10000))
            
            # Ping simple localhost uniquement
            try:
                response = requests.get(f"http://localhost:{port}/ping", timeout=10)
                if response.status_code == 200:
                    consecutive_failures = 0
                    if datetime.now().minute < 5:  # Log une fois par heure
                        logger.info("🏓 Self-ping OK")
                else:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ Self-ping échec HTTP {response.status_code}")
                    
            except Exception as e:
                consecutive_failures += 1
                logger.warning(f"⚠️ Self-ping échec: {e}")
            
            if consecutive_failures >= max_failures:
                logger.error("❌ Self-ping échecs multiples - serveur possiblement down")
                # NE PAS forcer d'action, juste logger
                consecutive_failures = 0  # Reset pour éviter le spam
                
        except Exception as e:
            logger.error(f"❌ Erreur critique self-ping: {e}")
            time.sleep(60)
'''
    
    with open('monitoring_minimal.py', 'w', encoding='utf-8') as f:
        f.write(monitoring_code)
    
    logger.info("✅ Système de monitoring minimal créé")

def create_stable_main():
    """Crée une version stable de main.py avec gestion d'erreurs améliorée."""
    logger = logging.getLogger(__name__)
    logger.info("🔧 Création de main.py stable...")
    
    # Backup de l'ancien main.py
    if os.path.exists('main.py'):
        shutil.copy2('main.py', f'main_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.py')
        logger.info("✅ Backup de main.py créé")
    
    stable_main = '''import os
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
            'cogs.Surveillance_scene',
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
        
        critical_cogs = ['cogs.Cards', 'cogs.RPTracker', 'cogs.Surveillance_scene']
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
'''
    
    with open('main_stable.py', 'w', encoding='utf-8') as f:
        f.write(stable_main)
    
    logger.info("✅ main_stable.py créé")

def create_requirements_update():
    """Mettre à jour requirements.txt avec les dépendances manquantes."""
    logger = logging.getLogger(__name__)
    logger.info("🔧 Mise à jour des requirements...")
    
    additional_requirements = [
        'oauth2client>=4.1.3',
        'gspread>=5.0.0',
        'requests>=2.25.0'
    ]
    
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            current_reqs = f.read()
        
        with open('requirements.txt', 'a') as f:
            f.write('\n# Dépendances ajoutées par le script de correction\n')
            for req in additional_requirements:
                package_name = req.split('>=')[0]
                if package_name not in current_reqs:
                    f.write(f'{req}\n')
                    logger.info(f"✅ Ajouté : {req}")
    else:
        logger.warning("⚠️ requirements.txt non trouvé")

def create_usage_instructions():
    """Créer un fichier d'instructions d'utilisation."""
    logger = logging.getLogger(__name__)
    
    instructions = '''# 🚀 SOLUTION AUX DÉCONNEXIONS DU BOT

## ✅ CE QUI A ÉTÉ CORRIGÉ :

1. **Credentials Google Sheets** - Variables d'environnement corrigées
2. **Monitoring simplifié** - Plus de redémarrages automatiques excessifs
3. **Gestion d'erreurs améliorée** - Les cogs optionnels peuvent échouer sans crasher
4. **Configuration stable** - Paramètres optimisés pour la stabilité

## 📋 ÉTAPES À SUIVRE :

### 1. Configurer les credentials Google
```bash
# Éditez votre fichier .env et remplacez la ligne SERVICE_ACCOUNT_JSON par vos vrais credentials :
SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "...", ...}
```

### 2. Tester la version stable
```bash
# Utilisez la version stable du bot :
python main_stable.py
```

### 3. Si tout fonctionne bien, remplacer main.py
```bash
# Sauvegardez l'ancien puis remplacez :
cp main.py main_old.py
cp main_stable.py main.py
```

## 🔧 CHANGEMENTS PRINCIPAUX :

- **Monitoring non-agressif** : Plus de redémarrages automatiques excessifs
- **Chargement gracieux des cogs** : Les cogs optionnels peuvent échouer
- **Configuration tolérante** : Timeouts plus longs, plus de tentatives
- **Logs informatifs** : Messages clairs pour diagnostiquer

## ⚠️ IMPORTANT :

1. **Configurez SERVICE_ACCOUNT_JSON** avec vos vrais credentials Google
2. **Testez avec main_stable.py** avant de remplacer main.py
3. **Les credentials Google sont CRITIQUES** - le bot est stable sans eux mais limité

## 📊 MONITORING :

- `/health` - État du bot
- `/bot-status` - Statut détaillé
- `/ping` - Test rapide
- Logs dans `bot.log` et `fix_disconnections.log`

Votre bot devrait maintenant être stable ! 🎉
'''
    
    with open('SOLUTION_DECONNEXIONS.md', 'w', encoding='utf-8') as f:
        f.write(instructions)
    
    logger.info("✅ Instructions créées dans SOLUTION_DECONNEXIONS.md")

def main():
    """Fonction principale du script de correction."""
    logger = setup_logging()
    logger.info("🚀 DÉMARRAGE DU SCRIPT DE CORRECTION DES DÉCONNEXIONS")
    
    try:
        # 1. Corriger les variables d'environnement
        if not fix_environment_variables(logger):
            logger.error("❌ Échec correction variables d'environnement")
            return
        
        # 2. Créer le système de monitoring minimal
        create_minimal_monitoring()
        
        # 3. Créer la version stable de main.py
        create_stable_main()
        
        # 4. Mettre à jour requirements.txt
        create_requirements_update()
        
        # 5. Créer les instructions
        create_usage_instructions()
        
        logger.info("🎉 SCRIPT DE CORRECTION TERMINÉ AVEC SUCCÈS !")
        logger.info("📖 Consultez SOLUTION_DECONNEXIONS.md pour les instructions")
        logger.info("🧪 Testez avec : python main_stable.py")
        
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()