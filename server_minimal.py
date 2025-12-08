import os
import logging
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

logger = logging.getLogger('bot')

# État de santé avec plus de détails
_health_state = {
    'bot_healthy': True,
    'discord_connected': False,
    'last_activity': datetime.now(),
    'last_discord_check': None,
    'watchdog_status': None,
    'start_time': datetime.now()
}
_state_lock = threading.Lock()


def update_bot_health(healthy: bool = True, discord_connected: bool = None, watchdog_status: dict = None):
    """
    Mettre à jour l'état de santé du bot.

    Args:
        healthy: État général de santé
        discord_connected: État spécifique de la connexion Discord
        watchdog_status: Statut détaillé du watchdog
    """
    global _health_state
    with _state_lock:
        _health_state['bot_healthy'] = healthy
        _health_state['last_activity'] = datetime.now()

        if discord_connected is not None:
            _health_state['discord_connected'] = discord_connected
            _health_state['last_discord_check'] = datetime.now()

        if watchdog_status is not None:
            _health_state['watchdog_status'] = watchdog_status


def get_health_state() -> dict:
    """Retourne l'état de santé actuel."""
    with _state_lock:
        return _health_state.copy()


def is_truly_healthy() -> bool:
    """
    Vérifie si le bot est vraiment en bonne santé.
    Retourne True seulement si le serveur HTTP ET Discord sont OK.
    """
    with _state_lock:
        # Vérifier l'état de base
        if not _health_state['bot_healthy']:
            return False

        # Si on a un statut watchdog, l'utiliser
        if _health_state['watchdog_status']:
            return _health_state['watchdog_status'].get('is_healthy', False)

        # Sinon, vérifier la connexion Discord
        return _health_state['discord_connected']


class EnhancedHealthHandler(BaseHTTPRequestHandler):
    """Handler HTTP avec vérification de santé améliorée."""

    def log_message(self, format, *args):
        """Supprimer les logs HTTP verbeux."""
        pass

    def _send_json_response(self, data: dict, status: int = 200):
        """Envoie une réponse JSON."""
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_text_response(self, text: str, status: int = 200):
        """Envoie une réponse texte."""
        self.send_response(status)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(text.encode())

    def do_HEAD(self):
        """Support HEAD pour UptimeRobot et autres monitors."""
        is_healthy = is_truly_healthy()
        self.send_response(200 if is_healthy else 503)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def do_GET(self):
        """Endpoints de health check."""
        state = get_health_state()
        is_healthy = is_truly_healthy()

        if self.path == '/ping':
            # Ping simple pour UptimeRobot
            if is_healthy:
                self._send_text_response('pong', 200)
            else:
                self._send_text_response('discord_unhealthy', 503)

        elif self.path in ['/', '/health']:
            # Health check détaillé
            uptime_seconds = (datetime.now() - state['start_time']).total_seconds()

            response = {
                'status': 'healthy' if is_healthy else 'unhealthy',
                'uptime_seconds': int(uptime_seconds),
                'http_server': 'ok',
                'discord_connected': state['discord_connected'],
                'last_activity': state['last_activity'].isoformat() if state['last_activity'] else None,
            }

            # Ajouter le statut du watchdog si disponible
            if state['watchdog_status']:
                response['watchdog'] = state['watchdog_status']

            status_code = 200 if is_healthy else 503
            self._send_json_response(response, status_code)

        elif self.path == '/health/detailed':
            # Health check très détaillé (pour debugging)
            uptime_seconds = (datetime.now() - state['start_time']).total_seconds()

            response = {
                'status': 'healthy' if is_healthy else 'unhealthy',
                'uptime_seconds': int(uptime_seconds),
                'uptime_human': f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m",
                'http_server': 'ok',
                'discord': {
                    'connected': state['discord_connected'],
                    'last_check': state['last_discord_check'].isoformat() if state['last_discord_check'] else None,
                },
                'watchdog': state['watchdog_status'],
                'last_activity': state['last_activity'].isoformat() if state['last_activity'] else None,
                'start_time': state['start_time'].isoformat(),
            }

            self._send_json_response(response, 200)  # Toujours 200 pour le debugging

        elif self.path == '/health/discord':
            # Check spécifique Discord
            response = {
                'discord_connected': state['discord_connected'],
                'is_healthy': is_healthy,
            }
            if state['watchdog_status']:
                response.update(state['watchdog_status'])

            status_code = 200 if state['discord_connected'] else 503
            self._send_json_response(response, status_code)

        else:
            self.send_response(404)
            self.end_headers()


def start_minimal_server():
    """Serveur HTTP minimal et robuste."""
    port = int(os.environ.get("PORT", 10000))

    for attempt in range(5):  # Max 5 tentatives
        try:
            server = HTTPServer(('0.0.0.0', port), EnhancedHealthHandler)

            # Configuration socket robuste
            try:
                import socket
                server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except:
                pass  # Ignorer les erreurs de config socket

            logger.info(f"✅ Serveur HTTP démarré sur port {port}")
            logger.info(f"📍 Endpoints: /health, /health/detailed, /health/discord, /ping")
            server.serve_forever()

        except OSError as e:
            if attempt < 4:  # Retry sauf au dernier essai
                logger.warning(f"Tentative {attempt+1}/5 échouée: {e}")
                import time
                time.sleep(5)
            else:
                logger.error(f"❌ Impossible de démarrer serveur après 5 tentatives: {e}")
                break
        except Exception as e:
            logger.error(f"❌ Erreur serveur: {e}")
            break


def start_server_thread():
    """Démarrer le serveur dans un thread daemon."""
    server_thread = threading.Thread(target=start_minimal_server, daemon=True)
    server_thread.start()
    return server_thread
