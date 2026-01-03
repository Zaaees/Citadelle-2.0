import os
import sys
import threading
import logging
import uvicorn
from datetime import datetime

# Configuration du logging
logger = logging.getLogger('bot')

# Ajouter le chemin du backend pour l'import
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(current_dir, 'Site', 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

try:
    # Importer l'app FastAPI depuis le backend
    # Note: On suppose que Site/backend/main.py expose 'app'
    from main import app as fastapi_app
except ImportError as e:
    logger.critical(f"❌ Impossible d'importer l'API FastAPI: {e}")
    fastapi_app = None

class UnifiedServerThread(threading.Thread):
    def __init__(self, host="0.0.0.0", port=10000):
        super().__init__()
        self.host = host
        self.port = port
        self.daemon = True
        self.server = None

    def run(self):
        if not fastapi_app:
            logger.error("🛑 API non chargée, serveur web annulé")
            return

        logger.info(f"🚀 [UnifiedServer] Tentative de démarrage sur {self.host}:{self.port}")
        
        try:
            # Vérifier que le port est libre (optionnel mais utile pour debug)
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self.host, self.port))
            if result == 0:
                logger.warning(f"⚠️ [UnifiedServer] Le port {self.port} semble déjà utilisé !")
            sock.close()

            # Configuration Uvicorn
            # On utilise uvicorn.run directement qui est plus simple pour un thread dédié
            # plutôt que Server(config).run()
            logger.info(f"🚀 [UnifiedServer] Lancement de uvicorn.run()...")
            uvicorn.run(
                fastapi_app,
                host=self.host,
                port=self.port,
                log_level="info",
                use_colors=False
            )
            logger.info(f"✅ [UnifiedServer] uvicorn.run() terminé (ceci ne devrait pas arriver tout de suite)")
            
        except Exception as e:
            logger.error(f"❌ [UnifiedServer] Erreur critique lors du lancement: {e}")
            import traceback
            logger.error(traceback.format_exc())

def start_unified_server():
    """Démarre le serveur FastAPI dans un thread séparé"""
    port = int(os.environ.get("PORT", 10000))
    
    server_thread = UnifiedServerThread(port=port)
    server_thread.start()
    
    logger.info("✅ Thread API démarré")
    return server_thread
