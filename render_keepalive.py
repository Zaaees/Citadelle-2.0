"""
Module spécialement conçu pour maintenir le bot actif sur Render.
Résout les problèmes de déconnexion silencieuse.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger('bot')

class RenderKeepAlive:
    """Gestionnaire spécialisé pour maintenir la connexion sur Render."""
    
    def __init__(self, bot):
        self.bot = bot
        self.last_activity = datetime.now()
        self.activity_task = None
        self.is_running = False
        
    async def start_keepalive(self):
        """Démarre le système de keep-alive."""
        if self.is_running:
            return
            
        self.is_running = True
        self.activity_task = asyncio.create_task(self._activity_loop())
        logger.info("🔄 Render Keep-Alive activé")
        
    async def stop_keepalive(self):
        """Arrête le système de keep-alive."""
        self.is_running = False
        if self.activity_task and not self.activity_task.done():
            self.activity_task.cancel()
            try:
                await self.activity_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Render Keep-Alive arrêté")
        
    async def _activity_loop(self):
        """Boucle principale de maintien d'activité."""
        try:
            while self.is_running and not self.bot.is_closed():
                await asyncio.sleep(240)  # 4 minutes
                
                if not self.bot.is_ready():
                    continue
                    
                try:
                    # Activité légère : obtenir la latence
                    latency = self.bot.latency
                    self.last_activity = datetime.now()
                    
                    # Log périodique pour confirmer l'activité
                    if self.last_activity.minute % 10 == 0:
                        logger.info(f"💚 Keep-Alive: Bot actif (latence: {latency:.2f}s)")
                        
                    # Vérifier les guildes de manière asynchrone
                    if len(self.bot.guilds) > 0:
                        # Ping très léger sur la première guilde
                        guild = self.bot.guilds[0]
                        if guild.me:
                            # Simple vérification de présence
                            _ = guild.me.id
                            
                except Exception as e:
                    logger.warning(f"⚠️ Erreur dans keep-alive: {e}")
                    
        except asyncio.CancelledError:
            logger.info("🛑 Keep-Alive task cancelled")
        except Exception as e:
            logger.error(f"❌ Erreur critique dans Keep-Alive: {e}")
            
    def get_last_activity(self):
        """Retourne le timestamp de la dernière activité."""
        return self.last_activity

# Instance globale
_keepalive_instance = None

def setup_render_keepalive(bot):
    """Configure le keep-alive pour Render."""
    global _keepalive_instance
    if _keepalive_instance is None:
        _keepalive_instance = RenderKeepAlive(bot)
    return _keepalive_instance

def get_keepalive():
    """Récupère l'instance keep-alive."""
    return _keepalive_instance