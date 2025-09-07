import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

logger = logging.getLogger('bot')

# État minimal pour health check
bot_healthy = True
last_activity = datetime.now()

def update_bot_health(healthy=True):
    """Mettre à jour l'état de santé du bot."""
    global bot_healthy, last_activity
    bot_healthy = healthy
    last_activity = datetime.now()

class MinimalHealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Supprimer les logs HTTP verbeux."""
        pass
    
    def do_HEAD(self):
        """Support HEAD pour UptimeRobot."""
        self.send_response(200 if bot_healthy else 503)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
    
    def do_GET(self):
        """Health check minimal."""
        if self.path == '/ping':
            status = 200 if bot_healthy else 503
            self.send_response(status)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            
            if bot_healthy:
                self.wfile.write(b'pong')
            else:
                self.wfile.write(b'bot_unhealthy')
        
        elif self.path in ['/', '/health']:
            self.send_response(200 if bot_healthy else 503)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            uptime = (datetime.now() - last_activity).total_seconds()
            response = f'{{"status": "{"healthy" if bot_healthy else "unhealthy"}", "uptime": {uptime}}}'
            self.wfile.write(response.encode())
        
        else:
            self.send_response(404)
            self.end_headers()

def start_minimal_server():
    """Serveur HTTP minimal et robuste."""
    port = int(os.environ.get("PORT", 10000))
    
    for attempt in range(5):  # Max 5 tentatives
        try:
            server = HTTPServer(('0.0.0.0', port), MinimalHealthHandler)
            
            # Configuration socket robuste
            try:
                import socket
                server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except:
                pass  # Ignorer les erreurs de config socket
            
            logger.info(f"✅ Serveur minimal démarré sur port {port}")
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