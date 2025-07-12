"""
Gestionnaire de connexions pour optimiser les ressources et éviter les fuites.
"""
import logging
import threading
import time
from typing import Dict, Optional
import gspread
from google.oauth2.service_account import Credentials
import json
import os

logger = logging.getLogger(__name__)

class GoogleSheetsConnectionManager:
    """Gestionnaire singleton pour les connexions Google Sheets."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._client = None
        self._last_auth_time = 0
        self._auth_lock = threading.RLock()
        self._connection_cache = {}
        self._cache_lock = threading.RLock()
        self._max_cache_age = 300  # 5 minutes
        
        logger.info("🔧 GoogleSheetsConnectionManager initialisé")
    
    def get_client(self) -> Optional[gspread.Client]:
        """Obtient un client Google Sheets authentifié."""
        current_time = time.time()
        
        with self._auth_lock:
            # Réauthentifier si nécessaire (toutes les 30 minutes)
            if not self._client or (current_time - self._last_auth_time) > 1800:
                try:
                    scopes = [
                        'https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive'
                    ]
                    
                    creds = Credentials.from_service_account_info(
                        json.loads(os.getenv('SERVICE_ACCOUNT_JSON')),
                        scopes=scopes
                    )
                    
                    self._client = gspread.authorize(creds)
                    self._last_auth_time = current_time
                    logger.info("✅ Client Google Sheets authentifié")
                    
                except Exception as e:
                    logger.error(f"❌ Erreur lors de l'authentification Google Sheets: {e}")
                    return None
        
        return self._client
    
    def get_spreadsheet(self, sheet_id: str, force_refresh: bool = False):
        """Obtient un spreadsheet avec mise en cache."""
        current_time = time.time()
        
        with self._cache_lock:
            # Vérifier le cache
            if not force_refresh and sheet_id in self._connection_cache:
                cached_data = self._connection_cache[sheet_id]
                if (current_time - cached_data['timestamp']) < self._max_cache_age:
                    return cached_data['spreadsheet']
            
            # Obtenir le spreadsheet
            client = self.get_client()
            if not client:
                return None
            
            try:
                spreadsheet = client.open_by_key(sheet_id)
                
                # Mettre en cache
                self._connection_cache[sheet_id] = {
                    'spreadsheet': spreadsheet,
                    'timestamp': current_time
                }
                
                logger.debug(f"📊 Spreadsheet {sheet_id} obtenu et mis en cache")
                return spreadsheet
                
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'ouverture du spreadsheet {sheet_id}: {e}")
                return None
    
    def clear_cache(self):
        """Vide le cache des connexions."""
        with self._cache_lock:
            self._connection_cache.clear()
            logger.info("🧹 Cache des connexions Google Sheets vidé")
    
    def cleanup_old_cache_entries(self):
        """Nettoie les entrées de cache expirées."""
        current_time = time.time()
        
        with self._cache_lock:
            expired_keys = []
            for sheet_id, cached_data in self._connection_cache.items():
                if (current_time - cached_data['timestamp']) > self._max_cache_age:
                    expired_keys.append(sheet_id)
            
            for key in expired_keys:
                del self._connection_cache[key]
            
            if expired_keys:
                logger.info(f"🧹 {len(expired_keys)} entrées de cache expirées supprimées")

class ResourceMonitor:
    """Moniteur des ressources système."""
    
    def __init__(self):
        self.logger = logging.getLogger('resource_monitor')
        self._last_cleanup = time.time()
    
    def check_and_cleanup(self):
        """Vérifie et nettoie les ressources si nécessaire."""
        current_time = time.time()
        
        # Nettoyer toutes les 10 minutes
        if (current_time - self._last_cleanup) > 600:
            try:
                # Nettoyer le cache Google Sheets
                connection_manager = GoogleSheetsConnectionManager()
                connection_manager.cleanup_old_cache_entries()
                
                self._last_cleanup = current_time
                self.logger.info("✅ Nettoyage des ressources effectué")
                
            except Exception as e:
                self.logger.error(f"❌ Erreur lors du nettoyage des ressources: {e}")

# Instance globale du moniteur de ressources
resource_monitor = ResourceMonitor()
