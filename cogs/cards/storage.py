"""
Gestion du stockage et du cache pour le système de cartes.
Gère les interactions avec Google Sheets et la mise en cache des données.
"""

import time
import threading
import logging
from typing import List, Dict, Any, Optional
import gspread

from .config import CACHE_VALIDITY_DURATION


class CardsStorage:
    """Gestionnaire de stockage et cache pour les cartes."""
    
    def __init__(self, gspread_client: gspread.Client, spreadsheet_id: str):
        self.gspread_client = gspread_client
        self.spreadsheet = gspread_client.open_by_key(spreadsheet_id)

        # Feuilles de calcul
        self.sheet_cards = self.spreadsheet.sheet1

        # Initialiser le logging manager à None par défaut
        self.logging_manager = None

        try:
            self._init_worksheets()
            logging.info("[STORAGE] ✅ Toutes les feuilles initialisées avec succès")
        except Exception as e:
            logging.error(f"[STORAGE] ❌ Erreur critique lors de l'initialisation des feuilles: {e}")
            import traceback
            logging.error(f"[STORAGE] Traceback: {traceback.format_exc()}")

        # Initialiser le gestionnaire de logging après les worksheets
        try:
            self._init_logging()
        except Exception as e:
            logging.error(f"[STORAGE] ❌ Erreur critique lors de l'initialisation du logging: {e}")
            import traceback
            logging.error(f"[STORAGE] Traceback: {traceback.format_exc()}")
        
        # Cache et verrous
        self.cards_cache = None
        self.cards_cache_time = 0
        self.vault_cache = None
        self.vault_cache_time = 0
        self.discoveries_cache = None
        self.discoveries_cache_time = 0
        
        # Verrous pour thread safety
        self._cards_lock = threading.RLock()
        self._vault_lock = threading.RLock()
        self._cache_lock = threading.RLock()
        self._discoveries_lock = threading.RLock()
    
    def _init_worksheets(self):
        """Initialise les feuilles de calcul nécessaires."""
        # Feuille de lancement
        try:
            self.sheet_lancement = self.spreadsheet.worksheet("Lancement")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_lancement = self.spreadsheet.add_worksheet(
                title="Lancement", rows="1000", cols="2"
            )
        
        # Feuille des tirages journaliers
        try:
            self.sheet_daily_draw = self.spreadsheet.worksheet("Tirages Journaliers")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_daily_draw = self.spreadsheet.add_worksheet(
                title="Tirages Journaliers", rows="1000", cols="2"
            )

        # Feuille des tirages sacrificiels
        try:
            self.sheet_sacrificial_draw = self.spreadsheet.worksheet("Tirages Sacrificiels")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_sacrificial_draw = self.spreadsheet.add_worksheet(
                title="Tirages Sacrificiels", rows="1000", cols="2"
            )
        
        # Feuille des découvertes
        try:
            self.sheet_discoveries = self.spreadsheet.worksheet("Découvertes")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_discoveries = self.spreadsheet.add_worksheet(
                title="Découvertes", rows="10000", cols="10"
            )
            # Initialiser l'en-tête
            self.sheet_discoveries.append_row([
                "category", "name", "discoverer_id", "discoverer_name", 
                "timestamp", "discovery_index"
            ])
        
        # Feuille du vault
        try:
            self.sheet_vault = self.spreadsheet.worksheet("Vault")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_vault = self.spreadsheet.add_worksheet(
                title="Vault", rows="1000", cols="20"
            )
            # Initialiser l'en-tête
            self.sheet_vault.append_row(["category", "name", "user_data..."])
        
        # Feuille des échanges hebdomadaires
        try:
            self.sheet_weekly_exchanges = self.spreadsheet.worksheet("Échanges Hebdomadaires")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_weekly_exchanges = self.spreadsheet.add_worksheet(
                title="Échanges Hebdomadaires", rows="1000", cols="3"
            )
            # Initialiser l'en-tête
            self.sheet_weekly_exchanges.append_row(["user_id", "week", "count"])

        # Feuille des bonus
        try:
            self.sheet_bonus = self.spreadsheet.worksheet("Bonus")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_bonus = self.spreadsheet.add_worksheet(
                title="Bonus", rows="1000", cols="3"
            )
            # Initialiser l'en-tête
            self.sheet_bonus.append_row(["user_id", "count", "source"])

        # Feuille des logs de surveillance
        logging.info("[STORAGE] 🔄 Initialisation de la feuille 'Logs'...")
        try:
            self.sheet_logs = self.spreadsheet.worksheet("Logs")
            logging.info("[STORAGE] ✅ Feuille 'Logs' trouvée")

            # Vérifier que l'en-tête existe
            try:
                all_values = self.sheet_logs.get_all_values()
                if not all_values or len(all_values) == 0:
                    logging.info("[STORAGE] Feuille 'Logs' vide, ajout de l'en-tête")
                    self.sheet_logs.append_row([
                        "timestamp", "action", "user_id", "user_name", "card_category",
                        "card_name", "quantity", "details", "source", "additional_data"
                    ])
                    logging.info("[STORAGE] ✅ En-tête ajouté à la feuille 'Logs'")
                elif all_values[0] != ["timestamp", "action", "user_id", "user_name", "card_category", "card_name", "quantity", "details", "source", "additional_data"]:
                    logging.warning("[STORAGE] ⚠️ En-tête de la feuille 'Logs' incorrect")
                    logging.warning(f"[STORAGE] En-tête actuel: {all_values[0]}")
                else:
                    logging.info(f"[STORAGE] ✅ Feuille 'Logs' correcte avec {len(all_values)} lignes")
            except Exception as e:
                logging.error(f"[STORAGE] ❌ Erreur lors de la vérification de l'en-tête: {e}")
                import traceback
                logging.error(f"[STORAGE] Traceback: {traceback.format_exc()}")

        except gspread.exceptions.WorksheetNotFound:
            logging.info("[STORAGE] Feuille 'Logs' non trouvée, création...")
            try:
                self.sheet_logs = self.spreadsheet.add_worksheet(
                    title="Logs", rows="10000", cols="10"
                )
                logging.info("[STORAGE] ✅ Feuille 'Logs' créée")

                # Initialiser l'en-tête
                self.sheet_logs.append_row([
                    "timestamp", "action", "user_id", "user_name", "card_category",
                    "card_name", "quantity", "details", "source", "additional_data"
                ])
                logging.info("[STORAGE] ✅ En-tête ajouté à la nouvelle feuille 'Logs'")
            except Exception as e:
                logging.error(f"[STORAGE] ❌ Erreur lors de la création de la feuille 'Logs': {e}")
                import traceback
                logging.error(f"[STORAGE] Traceback: {traceback.format_exc()}")
                self.sheet_logs = None

        except Exception as e:
            logging.error(f"[STORAGE] ❌ Erreur générale lors de l'initialisation de la feuille 'Logs': {e}")
            import traceback
            logging.error(f"[STORAGE] Traceback: {traceback.format_exc()}")
            self.sheet_logs = None
    
    def refresh_cards_cache(self):
        """Rafraîchit le cache des cartes."""
        with self._cache_lock:
            try:
                self.cards_cache = self.sheet_cards.get_all_values()
                self.cards_cache_time = time.time()
                logging.info("[CACHE] Cache des cartes rafraîchi")
            except Exception as e:
                logging.error(f"[CACHE] Erreur lors du rafraîchissement du cache des cartes: {e}")
    
    def refresh_vault_cache(self):
        """Rafraîchit le cache du vault."""
        with self._vault_lock:
            try:
                self.vault_cache = self.sheet_vault.get_all_values()
                self.vault_cache_time = time.time()
                logging.info("[CACHE] Cache du vault rafraîchi")
            except Exception as e:
                logging.error(f"[CACHE] Erreur lors du rafraîchissement du cache du vault: {e}")
    
    def refresh_discoveries_cache(self):
        """Rafraîchit le cache des découvertes."""
        with self._discoveries_lock:
            try:
                self.discoveries_cache = self.sheet_discoveries.get_all_values()
                self.discoveries_cache_time = time.time()
                logging.info("[CACHE] Cache des découvertes rafraîchi")
            except Exception as e:
                logging.error(f"[CACHE] Erreur lors du rafraîchissement du cache des découvertes: {e}")
    
    def get_cards_cache(self) -> Optional[List[List[str]]]:
        """Retourne le cache des cartes, le rafraîchit si nécessaire."""
        with self._cache_lock:
            now = time.time()
            if not self.cards_cache or now - self.cards_cache_time > CACHE_VALIDITY_DURATION:
                self.refresh_cards_cache()
            return self.cards_cache
    
    def get_vault_cache(self) -> Optional[List[List[str]]]:
        """Retourne le cache du vault, le rafraîchit si nécessaire."""
        with self._vault_lock:
            now = time.time()
            if not self.vault_cache or now - self.vault_cache_time > CACHE_VALIDITY_DURATION:
                self.refresh_vault_cache()
            return self.vault_cache
    
    def get_discoveries_cache(self) -> Optional[List[List[str]]]:
        """Retourne le cache des découvertes, le rafraîchit si nécessaire."""
        with self._discoveries_lock:
            now = time.time()
            if not self.discoveries_cache or now - self.discoveries_cache_time > CACHE_VALIDITY_DURATION:
                self.refresh_discoveries_cache()
            return self.discoveries_cache

    def _init_logging(self):
        """Initialise le gestionnaire de logging."""
        logging.info("[STORAGE] 🔄 Début de l'initialisation du logging manager...")

        try:
            # Vérifier que la feuille de logs existe avant d'initialiser le manager
            if not hasattr(self, 'sheet_logs') or self.sheet_logs is None:
                logging.error("[STORAGE] ❌ Feuille de logs non disponible pour l'initialisation du logging manager")
                self.logging_manager = None
                return

            logging.info("[STORAGE] 🔄 Importation du CardsLoggingManager...")
            try:
                from .logging import CardsLoggingManager
                logging.info("[STORAGE] ✅ CardsLoggingManager importé avec succès")
            except Exception as import_error:
                logging.error(f"[STORAGE] ❌ Erreur d'importation du CardsLoggingManager: {import_error}")
                import traceback
                logging.error(f"[STORAGE] Import Traceback: {traceback.format_exc()}")
                self.logging_manager = None
                return

            logging.info("[STORAGE] 🔄 Création de l'instance CardsLoggingManager...")
            try:
                self.logging_manager = CardsLoggingManager(self)
                logging.info("[STORAGE] ✅ Instance CardsLoggingManager créée avec succès")
            except Exception as instance_error:
                logging.error(f"[STORAGE] ❌ Erreur de création de l'instance CardsLoggingManager: {instance_error}")
                import traceback
                logging.error(f"[STORAGE] Instance Traceback: {traceback.format_exc()}")
                self.logging_manager = None
                return

            logging.info("[STORAGE] ✅ Gestionnaire de logging initialisé avec succès")

            # Test rapide d'écriture pour vérifier que tout fonctionne
            logging.info("[STORAGE] 🔄 Test d'écriture de logs...")
            try:
                test_success = self.logging_manager._log_action(
                    action="SYSTEM_TEST",
                    user_id=0,
                    user_name="System",
                    details="Test d'initialisation du système de logging",
                    source="storage_init"
                )

                if test_success:
                    logging.info("[STORAGE] ✅ Test d'écriture de logs réussi")
                else:
                    logging.warning("[STORAGE] ⚠️ Test d'écriture de logs échoué")
            except Exception as test_error:
                logging.error(f"[STORAGE] ❌ Erreur lors du test d'écriture: {test_error}")
                import traceback
                logging.error(f"[STORAGE] Test Traceback: {traceback.format_exc()}")

        except Exception as e:
            logging.error(f"[STORAGE] ❌ Erreur générale lors de l'initialisation du logging: {e}")
            import traceback
            logging.error(f"[STORAGE] General Traceback: {traceback.format_exc()}")
            self.logging_manager = None
