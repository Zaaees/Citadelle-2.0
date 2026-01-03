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

        logger.info(f"🚀 Démarrage du serveur unifié (Bot + API) sur le port {self.port}")
        
        try:
            # Configuration Uvicorn
            config = uvicorn.Config(
                app=fastapi_app,
                host=self.host,
                port=self.port,
                log_level="info",
                loop="asyncio"
            )
            self.server = uvicorn.Server(config)
            
            # Forcer l'utilisation de la boucle d'événements existante si nécessaire
            # Mais ici on est dans un thread séparé, donc on peut laisser uvicorn gérer sa boucle
            self.server.run()
            
        except Exception as e:
            logger.error(f"❌ Erreur critique serveur Web: {e}")

def start_unified_server():
    """Démarre le serveur FastAPI dans un thread séparé"""
    port = int(os.environ.get("PORT", 10000))
    
    server_thread = UnifiedServerThread(port=port)
    server_thread.start()
    
    logger.info("✅ Thread API démarré")
    return server_thread
