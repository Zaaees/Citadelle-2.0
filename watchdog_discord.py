"""
Watchdog Discord - Surveillance robuste de la connexion Discord.
Détecte les connexions "zombie" et force la reconnexion si nécessaire.
"""
import asyncio
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger('watchdog_discord')


@dataclass
class ConnectionState:
    """État de la connexion Discord."""
    last_successful_heartbeat: float = field(default_factory=time.time)
    last_message_received: float = field(default_factory=time.time)
    last_gateway_response: float = field(default_factory=time.time)
    consecutive_heartbeat_failures: int = 0
    total_reconnections: int = 0
    is_zombie: bool = False
    last_latency: float = 0.0
    latency_history: list = field(default_factory=list)


class DiscordWatchdog:
    """
    Watchdog avancé pour détecter et récupérer des déconnexions Discord.

    Contrairement au simple health check HTTP, ce watchdog vérifie
    réellement si la connexion WebSocket Discord est fonctionnelle.
    """

    def __init__(self, bot, health_callback: Optional[Callable[[bool], None]] = None):
        self.bot = bot
        self.health_callback = health_callback
        self.state = ConnectionState()
        self._running = False
        self._watchdog_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Configuration
        self.config = {
            'check_interval': 30,           # Vérifier toutes les 30 secondes
            'heartbeat_timeout': 120,       # Timeout heartbeat: 2 minutes
            'zombie_threshold': 300,        # Considérer zombie après 5 min sans activité
            'max_latency': 15.0,            # Latence max acceptable: 15 secondes
            'max_consecutive_failures': 5,  # Failures avant action
            'force_reconnect_interval': 3600 * 6,  # Reconnexion forcée toutes les 6h
            'latency_history_size': 60,     # Garder 60 mesures de latence
        }

        self._last_force_reconnect = time.time()

    async def start(self):
        """Démarre le watchdog."""
        if self._running:
            logger.warning("Watchdog déjà en cours d'exécution")
            return

        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.info("🐕 Watchdog Discord démarré")

    async def stop(self):
        """Arrête le watchdog."""
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        logger.info("🐕 Watchdog Discord arrêté")

    def record_activity(self):
        """Enregistre une activité (message reçu, etc.)."""
        self.state.last_message_received = time.time()
        self.state.is_zombie = False

    def record_gateway_response(self):
        """Enregistre une réponse du gateway Discord."""
        self.state.last_gateway_response = time.time()
        self.state.consecutive_heartbeat_failures = 0
        self.state.is_zombie = False

    async def _watchdog_loop(self):
        """Boucle principale du watchdog."""
        # Attendre que le bot soit prêt
        await self._wait_for_ready()

        while self._running:
            try:
                await self._check_connection_health()
                await asyncio.sleep(self.config['check_interval'])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Erreur dans le watchdog: {e}")
                await asyncio.sleep(60)  # Attendre plus longtemps en cas d'erreur

    async def _wait_for_ready(self):
        """Attend que le bot soit prêt."""
        logger.info("⏳ Watchdog: Attente de la connexion initiale...")
        timeout = 120  # 2 minutes max
        start = time.time()

        while not self.bot.is_ready() and (time.time() - start) < timeout:
            await asyncio.sleep(5)

        if self.bot.is_ready():
            logger.info("✅ Watchdog: Bot connecté, surveillance active")
            self.state.last_successful_heartbeat = time.time()
            self.state.last_gateway_response = time.time()
        else:
            logger.warning("⚠️ Watchdog: Timeout d'attente, surveillance démarrée quand même")

    async def _check_connection_health(self):
        """Vérifie la santé de la connexion Discord."""
        current_time = time.time()
        is_healthy = True
        issues = []

        # 1. Vérifier si le bot est fermé
        if self.bot.is_closed():
            logger.critical("💀 Bot fermé détecté!")
            is_healthy = False
            issues.append("bot_closed")

        # 2. Vérifier si le bot est prêt
        elif not self.bot.is_ready():
            logger.warning("⚠️ Bot non prêt")
            is_healthy = False
            issues.append("not_ready")
            self.state.consecutive_heartbeat_failures += 1

        else:
            # 3. Vérifier la latence (indicateur clé de santé WebSocket)
            latency = self.bot.latency
            self.state.last_latency = latency
            self._record_latency(latency)

            if latency > self.config['max_latency']:
                logger.warning(f"⚠️ Latence très élevée: {latency:.2f}s")
                issues.append("high_latency")
                self.state.consecutive_heartbeat_failures += 1
            elif latency == float('inf') or latency < 0:
                logger.warning("⚠️ Latence invalide (connexion probablement morte)")
                issues.append("invalid_latency")
                self.state.consecutive_heartbeat_failures += 1
                is_healthy = False
            else:
                # Latence OK = heartbeat réussi
                self.state.last_successful_heartbeat = current_time
                self.state.consecutive_heartbeat_failures = 0

            # 4. Vérifier le temps depuis le dernier heartbeat réussi
            time_since_heartbeat = current_time - self.state.last_successful_heartbeat
            if time_since_heartbeat > self.config['heartbeat_timeout']:
                logger.warning(f"⚠️ Pas de heartbeat depuis {time_since_heartbeat:.0f}s")
                issues.append("heartbeat_timeout")
                is_healthy = False

            # 5. Détecter les connexions zombie
            time_since_activity = current_time - self.state.last_message_received
            if time_since_activity > self.config['zombie_threshold']:
                # Pas d'activité depuis longtemps - tester la connexion
                is_zombie = await self._test_connection_alive()
                if is_zombie:
                    logger.warning(f"🧟 Connexion zombie détectée (pas d'activité depuis {time_since_activity:.0f}s)")
                    self.state.is_zombie = True
                    issues.append("zombie_connection")
                    is_healthy = False

        # 6. Vérifier si on doit forcer une reconnexion périodique
        time_since_reconnect = current_time - self._last_force_reconnect
        if time_since_reconnect > self.config['force_reconnect_interval']:
            logger.info("🔄 Reconnexion préventive planifiée")
            await self._force_reconnect("preventive")

        # 7. Agir si trop de failures consécutifs
        if self.state.consecutive_heartbeat_failures >= self.config['max_consecutive_failures']:
            logger.error(f"❌ {self.state.consecutive_heartbeat_failures} échecs consécutifs - Reconnexion forcée")
            await self._force_reconnect("consecutive_failures")

        # 8. Mettre à jour le statut de santé
        if self.health_callback:
            self.health_callback(is_healthy)

        # Log périodique
        if is_healthy and not issues:
            logger.debug(f"💚 Connexion saine (latence: {self.state.last_latency:.2f}s)")
        elif issues:
            logger.warning(f"⚠️ Problèmes détectés: {', '.join(issues)}")

        return is_healthy

    async def _test_connection_alive(self) -> bool:
        """
        Teste si la connexion est vraiment vivante.
        Retourne True si la connexion est zombie (morte).
        """
        try:
            # Essayer de changer la présence - opération légère qui teste le gateway
            await asyncio.wait_for(
                self.bot.change_presence(
                    activity=None,
                    status=self.bot.status if hasattr(self.bot, 'status') else None
                ),
                timeout=10.0
            )
            self.state.last_gateway_response = time.time()
            return False  # Connexion vivante
        except asyncio.TimeoutError:
            logger.warning("⏱️ Timeout lors du test de connexion")
            return True  # Probablement zombie
        except Exception as e:
            logger.warning(f"⚠️ Erreur lors du test de connexion: {e}")
            return True  # Probablement zombie

    async def _force_reconnect(self, reason: str):
        """Force une reconnexion au gateway Discord."""
        async with self._lock:
            logger.warning(f"🔄 Reconnexion forcée (raison: {reason})")

            try:
                # Méthode 1: Fermer et reconnecter le WebSocket
                if hasattr(self.bot, 'ws') and self.bot.ws:
                    logger.info("🔌 Fermeture du WebSocket...")
                    await self.bot.ws.close(code=1000)

                # Attendre que Discord.py reconnecte automatiquement
                logger.info("⏳ Attente de la reconnexion automatique...")

                # Attendre jusqu'à 60 secondes pour la reconnexion
                for i in range(12):
                    await asyncio.sleep(5)
                    if self.bot.is_ready():
                        logger.info(f"✅ Reconnexion réussie après {(i+1)*5}s")
                        break
                else:
                    logger.warning("⚠️ Reconnexion automatique lente, mais Discord.py devrait gérer")

                # Mettre à jour les compteurs
                self._last_force_reconnect = time.time()
                self.state.total_reconnections += 1
                self.state.consecutive_heartbeat_failures = 0
                self.state.is_zombie = False

            except Exception as e:
                logger.error(f"❌ Erreur lors de la reconnexion forcée: {e}")

    def _record_latency(self, latency: float):
        """Enregistre une mesure de latence."""
        self.state.latency_history.append({
            'timestamp': time.time(),
            'latency': latency
        })
        # Garder seulement les N dernières mesures
        if len(self.state.latency_history) > self.config['latency_history_size']:
            self.state.latency_history = self.state.latency_history[-self.config['latency_history_size']:]

    def get_status(self) -> dict:
        """Retourne le statut actuel du watchdog."""
        current_time = time.time()
        avg_latency = 0.0
        if self.state.latency_history:
            recent = [h['latency'] for h in self.state.latency_history[-10:] if h['latency'] != float('inf')]
            avg_latency = sum(recent) / len(recent) if recent else 0.0

        return {
            'is_healthy': not self.state.is_zombie and self.state.consecutive_heartbeat_failures < self.config['max_consecutive_failures'],
            'is_zombie': self.state.is_zombie,
            'last_latency': self.state.last_latency,
            'avg_latency_10': round(avg_latency, 3),
            'consecutive_failures': self.state.consecutive_heartbeat_failures,
            'total_reconnections': self.state.total_reconnections,
            'seconds_since_heartbeat': round(current_time - self.state.last_successful_heartbeat, 0),
            'seconds_since_activity': round(current_time - self.state.last_message_received, 0),
        }


# Instance globale du watchdog
_watchdog_instance: Optional[DiscordWatchdog] = None


def get_watchdog() -> Optional[DiscordWatchdog]:
    """Retourne l'instance globale du watchdog."""
    return _watchdog_instance


def create_watchdog(bot, health_callback=None) -> DiscordWatchdog:
    """Crée et retourne une nouvelle instance du watchdog."""
    global _watchdog_instance
    _watchdog_instance = DiscordWatchdog(bot, health_callback)
    return _watchdog_instance
