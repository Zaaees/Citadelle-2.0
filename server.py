import os
import time
import json
import logging
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import threading

# Logger for this module
logger = logging.getLogger('bot')

# Global state for monitoring
bot_start_time = datetime.now()
last_heartbeat = datetime.now()
request_count = 0
state_lock = threading.Lock()


def increment_request_count():
    """Increment the HTTP request counter in a thread-safe manner."""
    global request_count
    with state_lock:
        request_count += 1
        return request_count


def update_last_heartbeat():
    """Update the last heartbeat timestamp in a thread-safe manner."""
    global last_heartbeat
    with state_lock:
        last_heartbeat = datetime.now()
        return last_heartbeat


def get_request_count():
    """Get the current request count with lock protection."""
    with state_lock:
        return request_count


def get_last_heartbeat():
    """Get the last heartbeat timestamp with lock protection."""
    with state_lock:
        return last_heartbeat


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        rc = increment_request_count()
        lh = update_last_heartbeat()

        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(b'Bot is running!')

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()

            uptime = datetime.now() - bot_start_time
            health_data = {
                'status': 'healthy',
                'uptime_seconds': int(uptime.total_seconds()),
                'uptime_human': str(uptime),
                'request_count': rc,
                'last_heartbeat': lh.isoformat(),
                'timestamp': datetime.now().isoformat()
            }

            # Ajouter les métriques avancées si disponibles
            try:
                from utils.health_monitor import health_monitor
                if health_monitor:
                    advanced_metrics = health_monitor.metrics.get_health_summary()
                    health_data.update(advanced_metrics)
            except Exception as e:
                health_data['advanced_metrics_error'] = str(e)

            self.wfile.write(json.dumps(health_data).encode())

        elif self.path == '/health/detailed':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()

            try:
                from utils.health_monitor import health_monitor
                if health_monitor:
                    report = health_monitor.get_health_report()
                    self.wfile.write(report.encode())
                else:
                    self.wfile.write(b'Monitoring avance non disponible')
            except Exception as e:
                self.wfile.write(f'Erreur: {str(e)}'.encode())

        elif self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'pong')

        else:
            self.send_response(404)
            self.end_headers()


def start_http_server():
    max_retries = 10
    retry_count = 0

    while retry_count < max_retries:
        try:
            port = int(os.environ.get("PORT", 10000))
            logger.info(
                f"Tentative de démarrage du serveur HTTP sur le port {port} (essai {retry_count + 1}/{max_retries})"
            )

            # Créer le serveur avec des options de socket améliorées
            server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
            server.socket.setsockopt(1, 2, 1)  # SO_REUSEADDR

            logger.info(f"✅ Serveur HTTP démarré avec succès sur le port {port}")
            logger.info("🌐 Endpoints disponibles:")
            logger.info("   - GET /      : Health check basique")
            logger.info("   - GET /health: Informations détaillées")
            logger.info("   - GET /ping  : Ping rapide")

            server.serve_forever()

        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning(f"Port {port} déjà utilisé, attente de 10 secondes...")
                time.sleep(10)
            else:
                logger.error(f"Erreur OS lors du démarrage du serveur : {e}")
                time.sleep(5)
        except Exception as e:
            logger.error(f"Erreur lors du démarrage du serveur : {e}")
            traceback.print_exc()
            time.sleep(5)

        retry_count += 1
        if retry_count < max_retries:
            logger.info("Nouvelle tentative dans 5 secondes...")
            time.sleep(5)

    logger.critical(
        f"❌ Impossible de démarrer le serveur HTTP après {max_retries} tentatives"
    )
