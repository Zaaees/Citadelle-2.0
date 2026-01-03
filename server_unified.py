import os
import sys
import threading
import logging
import uvicorn
from datetime import datetime

# Configuration du logging
logger = logging.getLogger('bot')

# Ajouter le chemin du backend pour l'import des dépendances
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(current_dir, 'Site', 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

# Charger les variables d'environnement AVANT d'importer le backend
try:
    from dotenv import load_dotenv
    env_path = os.path.join(backend_path, '.env')
    print(f"🔄 [UnifiedServer] Loading .env from {env_path}")
    load_dotenv(env_path)
except ImportError:
    print("⚠️ [UnifiedServer] python-dotenv not installed, assuming env vars are set")
except Exception as e:
    print(f"⚠️ [UnifiedServer] Error loading .env: {e}")

try:
    # Utilisation de importlib pour éviter le conflit de nom avec 'main.py' racine
    import importlib.util
    
    print(f"🔄 [UnifiedServer] Loading backend from {backend_path}...")
    
    # On doit charger le module principal du backend avec un nom différent
    spec = importlib.util.spec_from_file_location("backend_app", os.path.join(backend_path, "main.py"))
    if spec and spec.loader:
        backend_module = importlib.util.module_from_spec(spec)
        sys.modules["backend_app"] = backend_module
        spec.loader.exec_module(backend_module)
        fastapi_app = backend_module.app
        print("✅ [UnifiedServer] Backend app loaded successfully")
    else:
        print("❌ [UnifiedServer] Failed to load spec (file not found?)")
        fastapi_app = None

except Exception as e:
    logger.critical(f"❌ [UnifiedServer] Erreur CRITIQUE import API: {e}")
    # Fallback debug print
    print(f"❌ [UnifiedServer] Erreur CRITIQUE import API: {e}")
    import traceback
    traceback.print_exc()
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
