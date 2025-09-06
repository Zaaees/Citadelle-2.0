"""
Script de diagnostic spécialisé pour détecter les problèmes de déconnexion sur Render.
"""

import os
import logging
import discord
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger('render_diagnostic')

class RenderDiagnostic:
    """Classe de diagnostic spécialisée pour Render."""
    
    def __init__(self, bot):
        self.bot = bot
        self.diagnostics = {}
        
    async def run_full_diagnostic(self):
        """Exécute un diagnostic complet."""
        logger.info("🔍 Début du diagnostic Render")
        
        results = {}
        
        # Test 1: Vérifier la configuration Discord
        results['discord_config'] = await self._check_discord_config()
        
        # Test 2: Vérifier les variables d'environnement
        results['environment'] = self._check_environment()
        
        # Test 3: Vérifier la mémoire et les ressources
        results['resources'] = self._check_resources()
        
        # Test 4: Vérifier la connectivité réseau
        results['network'] = await self._check_network()
        
        # Test 5: Vérifier les webhooks et l'activité
        results['activity'] = await self._check_bot_activity()
        
        # Générer le rapport
        report = self._generate_report(results)
        logger.info("📊 Diagnostic terminé")
        
        return report
    
    async def _check_discord_config(self):
        """Vérifie la configuration Discord."""
        checks = {}
        
        try:
            checks['bot_ready'] = self.bot.is_ready()
            checks['bot_closed'] = self.bot.is_closed()
            checks['latency'] = self.bot.latency
            checks['guild_count'] = len(self.bot.guilds)
            checks['user_count'] = sum(guild.member_count or 0 for guild in self.bot.guilds)
            
            # Vérifier les intents
            intents = self.bot.intents
            checks['intents'] = {
                'message_content': intents.message_content,
                'members': intents.members,
                'guilds': intents.guilds
            }
            
            checks['status'] = 'ok' if checks['bot_ready'] and not checks['bot_closed'] else 'warning'
            
        except Exception as e:
            checks['status'] = 'error'
            checks['error'] = str(e)
            
        return checks
    
    def _check_environment(self):
        """Vérifie les variables d'environnement."""
        checks = {}
        
        required_vars = ['DISCORD_TOKEN', 'SERVICE_ACCOUNT_JSON']
        optional_vars = ['PORT', 'RENDER_EXTERNAL_URL', 'HEALTHCHECK_MAX_FAILURES', 'HEALTHCHECK_FORCE_RESTART']
        
        checks['required'] = {}
        for var in required_vars:
            value = os.environ.get(var)
            checks['required'][var] = 'present' if value else 'missing'
            
        checks['optional'] = {}
        for var in optional_vars:
            value = os.environ.get(var)
            checks['optional'][var] = value if value else 'not_set'
            
        # Vérifier si on est sur Render
        checks['is_render'] = bool(os.environ.get('RENDER'))
        checks['render_service'] = os.environ.get('RENDER_SERVICE_NAME', 'unknown')
        
        missing_required = [k for k, v in checks['required'].items() if v == 'missing']
        checks['status'] = 'error' if missing_required else 'ok'
        
        return checks
    
    def _check_resources(self):
        """Vérifie les ressources système."""
        checks = {}
        
        try:
            import psutil
            
            # Mémoire
            memory = psutil.virtual_memory()
            checks['memory'] = {
                'total_mb': round(memory.total / 1024 / 1024),
                'used_mb': round(memory.used / 1024 / 1024),
                'percent': memory.percent
            }
            
            # CPU
            checks['cpu_percent'] = psutil.cpu_percent(interval=1)
            
            # Processus Python
            process = psutil.Process()
            checks['process'] = {
                'memory_mb': round(process.memory_info().rss / 1024 / 1024),
                'cpu_percent': process.cpu_percent(),
                'threads': process.num_threads()
            }
            
            # Évaluer le statut
            if checks['memory']['percent'] > 90 or checks['process']['memory_mb'] > 400:
                checks['status'] = 'warning'
            else:
                checks['status'] = 'ok'
                
        except ImportError:
            checks['status'] = 'error'
            checks['error'] = 'psutil not available'
        except Exception as e:
            checks['status'] = 'error' 
            checks['error'] = str(e)
            
        return checks
    
    async def _check_network(self):
        """Vérifie la connectivité réseau."""
        checks = {}
        
        try:
            import aiohttp
            
            # Test de connectivité Discord
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://discord.com/api/v10/gateway', timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            checks['discord_api'] = 'ok'
                            checks['discord_url'] = data.get('url', 'unknown')
                        else:
                            checks['discord_api'] = f'error_{resp.status}'
            except Exception as e:
                checks['discord_api'] = f'error: {str(e)}'
            
            # Test du serveur HTTP local
            port = int(os.environ.get('PORT', 10000))
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f'http://localhost:{port}/ping', timeout=5) as resp:
                        if resp.status == 200:
                            checks['local_http'] = 'ok'
                        else:
                            checks['local_http'] = f'error_{resp.status}'
            except Exception as e:
                checks['local_http'] = f'error: {str(e)}'
            
            # Évaluer le statut général
            if checks.get('discord_api') == 'ok' and checks.get('local_http') == 'ok':
                checks['status'] = 'ok'
            else:
                checks['status'] = 'warning'
                
        except ImportError:
            checks['status'] = 'error'
            checks['error'] = 'aiohttp not available'
        except Exception as e:
            checks['status'] = 'error'
            checks['error'] = str(e)
            
        return checks
    
    async def _check_bot_activity(self):
        """Vérifie l'activité du bot."""
        checks = {}
        
        try:
            # Vérifier l'activité récente
            from bot_state import get_bot_state
            state = get_bot_state()
            
            checks['bot_state'] = state['status']
            checks['restart_count'] = state['restart_count']
            checks['error_count'] = state['error_count']
            
            # Calculer le temps depuis la dernière activité
            if state['last_ready']:
                time_since_ready = datetime.now() - state['last_ready']
                checks['minutes_since_ready'] = int(time_since_ready.total_seconds() / 60)
                
            if state['last_disconnect']:
                time_since_disconnect = datetime.now() - state['last_disconnect'] 
                checks['minutes_since_disconnect'] = int(time_since_disconnect.total_seconds() / 60)
            
            # Vérifier les cogs
            loaded_cogs = list(self.bot.cogs.keys())
            checks['loaded_cogs'] = loaded_cogs
            checks['cog_count'] = len(loaded_cogs)
            
            # Évaluer le statut
            if state['status'] == 'connected' and state['error_count'] < 3:
                checks['status'] = 'ok'
            elif state['status'] in ['connecting', 'initializing']:
                checks['status'] = 'warning'
            else:
                checks['status'] = 'error'
                
        except Exception as e:
            checks['status'] = 'error'
            checks['error'] = str(e)
            
        return checks
    
    def _generate_report(self, results):
        """Génère un rapport de diagnostic."""
        report = []
        report.append("=" * 60)
        report.append("🔍 RAPPORT DE DIAGNOSTIC RENDER")
        report.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)
        
        # Résumé général
        overall_status = 'OK'
        warnings = 0
        errors = 0
        
        for section, data in results.items():
            status = data.get('status', 'unknown')
            if status == 'warning':
                warnings += 1
            elif status == 'error':
                errors += 1
                overall_status = 'ERROR'
        
        if warnings > 0 and overall_status != 'ERROR':
            overall_status = 'WARNING'
            
        report.append(f"📊 STATUT GÉNÉRAL: {overall_status}")
        report.append(f"⚠️  Avertissements: {warnings}")
        report.append(f"❌ Erreurs: {errors}")
        report.append("")
        
        # Détails par section
        for section, data in results.items():
            report.append(f"[{section.upper()}]")
            status = data.get('status', 'unknown')
            status_icon = '✅' if status == 'ok' else '⚠️' if status == 'warning' else '❌'
            report.append(f"  Statut: {status_icon} {status}")
            
            for key, value in data.items():
                if key != 'status':
                    report.append(f"  {key}: {value}")
            report.append("")
        
        # Recommandations
        report.append("💡 RECOMMANDATIONS:")
        
        if results.get('discord_config', {}).get('status') != 'ok':
            report.append("  - Vérifier la connexion Discord et les permissions")
            
        if results.get('environment', {}).get('status') != 'ok':
            report.append("  - Vérifier les variables d'environnement")
            
        if results.get('resources', {}).get('status') == 'warning':
            report.append("  - Surveiller l'usage mémoire - considérer une optimisation")
            
        if results.get('network', {}).get('status') != 'ok':
            report.append("  - Vérifier la connectivité réseau")
            
        if results.get('activity', {}).get('restart_count', 0) > 3:
            report.append("  - Investiguer les causes de redémarrages multiples")
        
        report.append("=" * 60)
        
        return "\n".join(report)

# Fonction utilitaire pour utilisation simple
async def run_render_diagnostic(bot):
    """Exécute un diagnostic complet et retourne le rapport."""
    diagnostic = RenderDiagnostic(bot)
    return await diagnostic.run_full_diagnostic()