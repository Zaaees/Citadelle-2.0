"""
Service de stockage - Réutilise les Google Sheets existants du bot Discord
Ce module s'interface directement avec les mêmes données que le bot
"""

import json
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from typing import List, Tuple, Dict, Optional, Set, Any
from datetime import datetime, timedelta
from threading import RLock
import hashlib
import random
import io
import logging

from config import get_settings, RARITY_CONFIG, RARITY_ORDER

logger = logging.getLogger(__name__)

# Scopes Google API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]


class CardsStorageService:
    """
    Service de stockage des cartes - S'interface avec les mêmes Google Sheets que le bot Discord
    """

    def __init__(self):
        self.settings = get_settings()
        self._init_google_clients()
        self._init_sheets()
        self._init_locks()
        self._init_cache()
        self._load_card_files()

    def _init_sheets(self):
        """Initialise les feuilles de calcul pour un accès public (requis par Bazaar)"""
        try:
            # Sheets principales
            self.sheet_cards = self.spreadsheet.sheet1
            
            # Helper pour safely get worksheet
            def get_or_create(title, rows="1000", cols="10"):
                try:
                    return self.spreadsheet.worksheet(title)
                except gspread.exceptions.WorksheetNotFound:
                    return self.spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

            self.sheet_lancement = get_or_create("Lancement")
            self.sheet_daily_draw = get_or_create("Tirages Journaliers")
            self.sheet_sacrificial_draw = get_or_create("Tirages Sacrificiels")
            self.sheet_discoveries = get_or_create("Découvertes")
            self.sheet_vault = get_or_create("Vault")
            self.sheet_weekly_exchanges = get_or_create("Échanges Hebdomadaires")
            self.sheet_bonus = get_or_create("Bonus")
            self.sheet_notifications = get_or_create("Notifications")
            
            self._init_exchange_sheet()
            
        except Exception as e:
            logger.error(f"Error initializing sheets: {e}")
            raise

    def _init_google_clients(self):
        """Initialise les clients Google API"""
        try:
            creds_data = json.loads(self.settings.service_account_json)
            self.credentials = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
            self.gc = gspread.authorize(self.credentials)
            self.spreadsheet = self.gc.open_by_key(self.settings.google_sheet_id_cartes)
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            logger.info("Google clients initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google clients: {e}")
            raise

    def _init_locks(self):
        """Initialise les verrous pour la thread-safety"""
        self._cards_lock = RLock()
        self._vault_lock = RLock()
        self._cache_lock = RLock()
        self._board_lock = RLock()

    def _init_cache(self):
        """Initialise le cache"""
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_validity = 5  # secondes

    def _is_cache_valid(self, key: str) -> bool:
        """Vérifie si le cache est valide"""
        if key not in self._cache_timestamps:
            return False
        age = (datetime.now() - self._cache_timestamps[key]).total_seconds()
        return age < self._cache_validity

    def _get_cached(self, key: str):
        """Récupère une valeur du cache"""
        with self._cache_lock:
            if self._is_cache_valid(key):
                return self._cache.get(key)
        return None

    def _set_cached(self, key: str, value):
        """Met en cache une valeur"""
        with self._cache_lock:
            self._cache[key] = value
            self._cache_timestamps[key] = datetime.now()

    def _load_card_files(self):
        """Charge la liste des fichiers de cartes depuis Google Drive"""
        self.cards_by_category: Dict[str, List[dict]] = {}
        self.full_cards_by_category: Dict[str, List[dict]] = {}

        folder_mapping = {
            "Élèves": self.settings.folder_eleves_id,
            "Autre": self.settings.folder_autre_id,
            "Professeurs": self.settings.folder_professeurs_id,
            "Architectes": self.settings.folder_architectes_id,
            "Black Hole": self.settings.folder_blackhole_id,
            "Maître": self.settings.folder_maitre_id,
            "Historique": self.settings.folder_historique_id,
            "Fondateur": self.settings.folder_fondateur_id,
            "Secrète": self.settings.folder_secrete_id,
        }

        full_folder_mapping = {
            "Élèves": self.settings.folder_eleves_full_id,
            "Autre": self.settings.folder_autre_full_id,
            "Professeurs": self.settings.folder_professeurs_full_id,
            "Architectes": self.settings.folder_architectes_full_id,
            "Black Hole": self.settings.folder_blackhole_full_id,
            "Maître": self.settings.folder_maitre_full_id,
            "Historique": self.settings.folder_historique_full_id,
            "Fondateur": self.settings.folder_fondateur_full_id,
            "Secrète": self.settings.folder_secrete_full_id,
        }

        for category, folder_id in folder_mapping.items():
            if folder_id:
                try:
                    results = self.drive_service.files().list(
                        q=f"'{folder_id}' in parents and mimeType contains 'image/'",
                        fields="files(id, name, mimeType)"
                    ).execute()
                    self.cards_by_category[category] = results.get('files', [])
                    logger.info(f"Loaded {len(self.cards_by_category[category])} cards for {category}")
                except Exception as e:
                    logger.error(f"Error loading cards for {category}: {e}")
                    self.cards_by_category[category] = []

        for category, folder_id in full_folder_mapping.items():
            if folder_id:
                try:
                    results = self.drive_service.files().list(
                        q=f"'{folder_id}' in parents and mimeType contains 'image/'",
                        fields="files(id, name, mimeType)"
                    ).execute()
                    self.full_cards_by_category[category] = results.get('files', [])
                except Exception as e:
                    logger.error(f"Error loading full cards for {category}: {e}")
                    self.full_cards_by_category[category] = []

    # ============== Gestion de l'inventaire ==============

    def get_user_cards(self, user_id: str) -> List[Tuple[str, str, int]]:
        """
        Récupère les cartes d'un utilisateur
        Returns: Liste de (category, name, count)
        """
        cache_key = f"user_cards_{user_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        with self._cards_lock:
            try:
                sheet = self.spreadsheet.sheet1
                all_data = sheet.get_all_values()

                if not all_data:
                    return []

                header = all_data[0]
                user_col_idx = None

                # Chercher la colonne de l'utilisateur
                for idx, cell in enumerate(header):
                    if cell.startswith(f"{user_id}:"):
                        user_col_idx = idx
                        break

                if user_col_idx is None:
                    return []

                cards = []
                for row in all_data[1:]:
                    if len(row) > user_col_idx and row[user_col_idx]:
                        try:
                            count = int(row[user_col_idx].split(":")[-1]) if ":" in row[user_col_idx] else int(row[user_col_idx])
                            if count > 0:
                                category = row[0] if len(row) > 0 else ""
                                name = row[1] if len(row) > 1 else ""
                                cards.append((category, name, count))
                        except (ValueError, IndexError):
                            continue

                self._set_cached(cache_key, cards)
                return cards

            except Exception as e:
                logger.error(f"Error getting user cards: {e}")
                return []

    def add_card_to_user(self, user_id: str, category: str, name: str, count: int = 1) -> bool:
        """Ajoute une carte à l'inventaire d'un utilisateur"""
        with self._cards_lock:
            try:
                sheet = self.spreadsheet.sheet1
                all_data = sheet.get_all_values()

                if not all_data:
                    return False

                header = all_data[0]
                user_col_idx = None

                # Chercher ou créer la colonne utilisateur
                for idx, cell in enumerate(header):
                    if cell.startswith(f"{user_id}:"):
                        user_col_idx = idx
                        break

                if user_col_idx is None:
                    # Créer une nouvelle colonne
                    user_col_idx = len(header)
                    sheet.update_cell(1, user_col_idx + 1, f"{user_id}:0")
                    header.append(f"{user_id}:0")

                # Chercher la ligne de la carte
                card_row_idx = None
                for idx, row in enumerate(all_data[1:], start=2):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        card_row_idx = idx
                        break

                if card_row_idx is None:
                    # La carte n'existe pas encore dans le sheet
                    return False

                # Mettre à jour le compteur
                current_count = 0
                if len(all_data[card_row_idx - 1]) > user_col_idx:
                    cell_value = all_data[card_row_idx - 1][user_col_idx]
                    if cell_value:
                        try:
                            current_count = int(cell_value.split(":")[-1]) if ":" in cell_value else int(cell_value)
                        except ValueError:
                            current_count = 0

                new_count = current_count + count
                sheet.update_cell(card_row_idx, user_col_idx + 1, str(new_count))

                # Invalider le cache
                self._cache.pop(f"user_cards_{user_id}", None)

                return True

            except Exception as e:
                logger.error(f"Error adding card to user: {e}")
                return False

    def remove_card_from_user(self, user_id: str, category: str, name: str, count: int = 1) -> bool:
        """Retire une carte de l'inventaire d'un utilisateur"""
        with self._cards_lock:
            try:
                sheet = self.spreadsheet.sheet1
                all_data = sheet.get_all_values()

                if not all_data:
                    return False

                header = all_data[0]
                user_col_idx = None

                for idx, cell in enumerate(header):
                    if cell.startswith(f"{user_id}:"):
                        user_col_idx = idx
                        break

                if user_col_idx is None:
                    return False

                # Chercher la ligne de la carte
                card_row_idx = None
                for idx, row in enumerate(all_data[1:], start=2):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        card_row_idx = idx
                        break

                if card_row_idx is None:
                    return False

                # Vérifier le compteur actuel
                current_count = 0
                if len(all_data[card_row_idx - 1]) > user_col_idx:
                    cell_value = all_data[card_row_idx - 1][user_col_idx]
                    if cell_value:
                        try:
                            current_count = int(cell_value.split(":")[-1]) if ":" in cell_value else int(cell_value)
                        except ValueError:
                            return False

                if current_count < count:
                    return False

                new_count = current_count - count
                sheet.update_cell(card_row_idx, user_col_idx + 1, str(new_count) if new_count > 0 else "")

                # Invalider le cache
                self._cache.pop(f"user_cards_{user_id}", None)

                return True

            except Exception as e:
                logger.error(f"Error removing card from user: {e}")
                return False

    def get_user_card_count(self, user_id: str, category: str, name: str) -> int:
        """Retourne le nombre d'exemplaires d'une carte pour un utilisateur"""
        cards = self.get_user_cards(user_id)
        for cat, card_name, count in cards:
            if cat == category and card_name == name:
                return count
        return 0

    # ============== Tirage journalier ==============

    def can_perform_daily_draw(self, user_id: str) -> bool:
        """Vérifie si l'utilisateur peut faire son tirage journalier"""
        try:
            sheet = self.sheet_lancement
            all_data = sheet.get_all_values()

            today = datetime.now().strftime("%Y-%m-%d")

            for row in all_data:
                if len(row) >= 2 and row[0] == str(user_id) and row[1] == today:
                    return False

            return True
        except Exception as e:
            logger.error(f"Error checking daily draw: {e}")
            return False

    def record_daily_draw(self, user_id: str) -> bool:
        """Enregistre un tirage journalier"""
        try:
            sheet = self.sheet_lancement
            today = datetime.now().strftime("%Y-%m-%d")
            sheet.append_row([str(user_id), today])
            return True
        except Exception as e:
            logger.error(f"Error recording daily draw: {e}")
            return False

    # ============== Tirage sacrificiel ==============

    def can_perform_sacrificial_draw(self, user_id: str) -> bool:
        """Vérifie si l'utilisateur peut faire un tirage sacrificiel"""
        try:
            sheet = self.sheet_sacrificial_draw
            all_data = sheet.get_all_values()

            today = datetime.now().strftime("%Y-%m-%d")

            for row in all_data:
                if len(row) >= 2 and row[0] == str(user_id) and row[1] == today:
                    return False

            return True
        except Exception as e:
            logger.error(f"Error checking sacrificial draw: {e}")
            return False

    def record_sacrificial_draw(self, user_id: str) -> bool:
        """Enregistre un tirage sacrificiel"""
        try:
            sheet = self.sheet_sacrificial_draw
            today = datetime.now().strftime("%Y-%m-%d")
            sheet.append_row([str(user_id), today])
            return True
        except Exception as e:
            logger.error(f"Error recording sacrificial draw: {e}")
            return False

    def get_sacrificial_cards(self, user_id: str) -> List[Tuple[str, str]]:
        """
        Retourne les 5 cartes sacrificielles du jour pour un utilisateur
        Utilise le même algorithme déterministe que le bot
        """
        user_cards = self.get_user_cards(user_id)
        if not user_cards:
            return []

        # Filtrer les cartes Full
        eligible = [(cat, name, count) for cat, name, count in user_cards if "(Full)" not in name]

        if len(eligible) < 5:
            return []

        # Sélection déterministe basée sur user_id + date
        today = datetime.now().strftime("%Y-%m-%d")
        seed_str = f"{user_id}-{today}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)

        # Créer une liste pondérée par le count
        weighted_cards = []
        for cat, name, count in eligible:
            weighted_cards.extend([(cat, name)] * count)

        # Sélectionner 5 cartes uniques
        selected = []
        available = weighted_cards.copy()
        while len(selected) < 5 and available:
            card = rng.choice(available)
            if card not in selected:
                selected.append(card)
            available = [c for c in available if c != card]

        return selected

    # ============== Bonus ==============

    def get_user_bonus_count(self, user_id: str) -> int:
        """Retourne le nombre de tirages bonus disponibles"""
        try:
            sheet = self.sheet_bonus
            all_data = sheet.get_all_values()

            total = 0
            for row in all_data:
                if len(row) >= 2 and row[0] == str(user_id):
                    try:
                        total += int(row[1])
                    except ValueError:
                        continue

            return total
        except Exception as e:
            logger.error(f"Error getting bonus count: {e}")
            return 0

    def use_bonus_draw(self, user_id: str) -> bool:
        """Utilise un tirage bonus"""
        try:
            sheet = self.sheet_bonus
            all_data = sheet.get_all_values()

            for idx, row in enumerate(all_data, start=1):
                if len(row) >= 2 and row[0] == str(user_id):
                    try:
                        current = int(row[1])
                        if current > 0:
                            sheet.update_cell(idx, 2, str(current - 1))
                            return True
                    except ValueError:
                        continue

            return False
        except Exception as e:
            logger.error(f"Error using bonus draw: {e}")
            return False

    # ============== Découvertes ==============

    def get_discovered_cards(self) -> Set[Tuple[str, str]]:
        """Retourne l'ensemble des cartes découvertes"""
        cache_key = "discovered_cards"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            sheet = self.sheet_discoveries
            all_data = sheet.get_all_values()

            discovered = set()
            for row in all_data[1:]:  # Skip header
                if len(row) >= 2:
                    discovered.add((row[0], row[1]))

            self._set_cached(cache_key, discovered)
            return discovered
        except Exception as e:
            logger.error(f"Error getting discoveries: {e}")
            return set()

    def log_discovery(self, category: str, name: str, user_id: str, user_name: str) -> int:
        """Enregistre une nouvelle découverte"""
        try:
            sheet = self.sheet_discoveries
            all_data = sheet.get_all_values()

            # Calculer l'index de découverte
            discovery_index = len(all_data)  # Header + existing rows

            timestamp = datetime.now().isoformat()
            sheet.append_row([category, name, str(user_id), user_name, timestamp, str(discovery_index)])

            # Invalider le cache
            self._cache.pop("discovered_cards", None)

            return discovery_index
        except Exception as e:
            logger.error(f"Error logging discovery: {e}")
            return -1

    def is_card_discovered(self, category: str, name: str) -> bool:
        """Vérifie si une carte a été découverte"""
        discovered = self.get_discovered_cards()
        return (category, name) in discovered

    def get_discovery_info(self, category: str, name: str) -> Optional[dict]:
        """Retourne les informations de découverte d'une carte"""
        try:
            sheet = self.sheet_discoveries
            all_data = sheet.get_all_values()

            for row in all_data[1:]:
                if len(row) >= 6 and row[0] == category and row[1] == name:
                    return {
                        "category": row[0],
                        "name": row[1],
                        "discoverer_id": row[2],
                        "discoverer_name": row[3],
                        "timestamp": row[4],
                        "discovery_index": int(row[5]) if row[5].isdigit() else 0
                    }

            return None
        except Exception as e:
            logger.error(f"Error getting discovery info: {e}")
            return None

    # ============== Coffre (Vault) ==============

    def get_user_vault(self, user_id: str) -> List[Tuple[str, str, int]]:
        """Récupère le contenu du coffre d'un utilisateur"""
        cache_key = f"vault_{user_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        with self._vault_lock:
            try:
                sheet = self.sheet_vault
                all_data = sheet.get_all_values()

                if not all_data:
                    return []

                header = all_data[0]
                user_col_idx = None

                for idx, cell in enumerate(header):
                    if cell.startswith(f"{user_id}:"):
                        user_col_idx = idx
                        break

                if user_col_idx is None:
                    return []

                cards = []
                for row in all_data[1:]:
                    if len(row) > user_col_idx and row[user_col_idx]:
                        try:
                            count = int(row[user_col_idx].split(":")[-1]) if ":" in row[user_col_idx] else int(row[user_col_idx])
                            if count > 0:
                                category = row[0] if len(row) > 0 else ""
                                name = row[1] if len(row) > 1 else ""
                                cards.append((category, name, count))
                        except (ValueError, IndexError):
                            continue

                self._set_cached(cache_key, cards)
                return cards

            except Exception as e:
                logger.error(f"Error getting user vault: {e}")
                return []

    def add_to_vault(self, user_id: str, category: str, name: str) -> bool:
        """Ajoute une carte au coffre (la retire de l'inventaire)"""
        # Vérifier que l'utilisateur a la carte
        if self.get_user_card_count(user_id, category, name) < 1:
            return False

        # Vérifier que ce n'est pas une Full
        if "(Full)" in name:
            return False

        with self._vault_lock:
            # Retirer de l'inventaire
            if not self.remove_card_from_user(user_id, category, name):
                return False

            # Ajouter au coffre (logique similaire à add_card_to_user mais sur Vault sheet)
            try:
                sheet = self.sheet_vault
                all_data = sheet.get_all_values()

                if not all_data:
                    sheet.append_row([category, name, f"{user_id}:1"])
                    self._cache.pop(f"vault_{user_id}", None)
                    return True

                header = all_data[0]
                user_col_idx = None

                for idx, cell in enumerate(header):
                    if cell.startswith(f"{user_id}:"):
                        user_col_idx = idx
                        break

                if user_col_idx is None:
                    user_col_idx = len(header)
                    sheet.update_cell(1, user_col_idx + 1, f"{user_id}:0")

                # Chercher la ligne de la carte
                card_row_idx = None
                for idx, row in enumerate(all_data[1:], start=2):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        card_row_idx = idx
                        break

                if card_row_idx is None:
                    # Ajouter une nouvelle ligne
                    new_row = [category, name] + [""] * (user_col_idx - 1) + ["1"]
                    sheet.append_row(new_row)
                else:
                    current_count = 0
                    if len(all_data[card_row_idx - 1]) > user_col_idx:
                        cell_value = all_data[card_row_idx - 1][user_col_idx]
                        if cell_value:
                            try:
                                current_count = int(cell_value)
                            except ValueError:
                                pass
                    sheet.update_cell(card_row_idx, user_col_idx + 1, str(current_count + 1))

                self._cache.pop(f"vault_{user_id}", None)
                return True

            except Exception as e:
                logger.error(f"Error adding to vault: {e}")
                # Rollback: remettre la carte dans l'inventaire
                self.add_card_to_user(user_id, category, name)
                return False

    def remove_from_vault(self, user_id: str, category: str, name: str) -> bool:
        """Retire une carte du coffre (la remet dans l'inventaire)"""
        # Implémentation similaire à add_to_vault mais inversée
        pass  # TODO: implémenter

    # ============== Tableau d'échanges (Bazaar) ==============

    def _init_exchange_sheet(self):
        """Initialise la feuille du tableau d'échanges."""
        try:
            self.sheet_exchange = self.spreadsheet.worksheet("Tableau Echanges")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_exchange = self.spreadsheet.add_worksheet(
                title="Tableau Echanges", rows="1000", cols="6"
            )
            self.sheet_exchange.append_row([
                "id", "owner", "cat", "name", "timestamp", "comment"
            ])
            return

        # Gérer les anciennes feuilles sans la colonne comment
        try:
            all_values = self.sheet_exchange.get_all_values()
            header = all_values[0] if all_values else []
            if "comment" not in header:
                current_cols = len(header)
                if current_cols < 6:
                    self.sheet_exchange.add_cols(6 - current_cols)
                self.sheet_exchange.update_cell(1, current_cols + 1, "comment")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à niveau de la feuille d'échanges: {e}")

    def create_exchange_entry(self, owner: int, cat: str, name: str,
                              timestamp: str, comment: Optional[str] = None) -> Optional[int]:
        """Crée une entrée sur le tableau d'échanges."""
        try:
            with self._board_lock:
                all_values = self.sheet_exchange.get_all_values()
                next_id = 1
                if len(all_values) > 1:
                    ids = [int(r[0]) for r in all_values[1:] if r and r[0].isdigit()]
                    if ids:
                        next_id = max(ids) + 1
                self.sheet_exchange.append_row([
                    str(next_id), str(owner), cat, name, timestamp, comment or ""
                ])
                return next_id
        except Exception as e:
            logger.error(f"Erreur lors de la création d'une entrée d'échange: {e}")
            return None

    def get_exchange_entries(self) -> List[Dict[str, Any]]:
        """Retourne toutes les entrées du tableau d'échanges."""
        try:
            with self._board_lock:
                records = self.sheet_exchange.get_all_records()
                for r in records:
                    if "comment" not in r:
                        r["comment"] = None
                    elif r["comment"] == "":
                        r["comment"] = None
                return records
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du tableau d'échanges: {e}")
            return []

    def get_exchange_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Récupère une entrée spécifique par son ID."""
        entries = self.get_exchange_entries()
        for entry in entries:
            if str(entry.get("id")) == str(entry_id):
                return entry
        return None

    def update_exchange_entry(self, entry_id: int, **fields) -> bool:
        """Met à jour une entrée existante."""
        col_map = {"id": 1, "owner": 2, "cat": 3, "name": 4, "timestamp": 5, "comment": 6}
        try:
            with self._board_lock:
                cell = self.sheet_exchange.find(str(entry_id))
                if not cell:
                    return False
                for key, value in fields.items():
                    if key in col_map:
                        self.sheet_exchange.update_cell(cell.row, col_map[key], str(value))
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour d'une entrée d'échange: {e}")
            return False

    def delete_exchange_entry(self, entry_id: int) -> bool:
        """Supprime une entrée du tableau d'échanges."""
        try:
            with self._board_lock:
                cell = self.sheet_exchange.find(str(entry_id))
                if not cell:
                    return False
                self.sheet_exchange.delete_rows(cell.row)
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression d'une entrée d'échange: {e}")
            return False

    # ============== Échanges hebdomadaires ==============

    def get_weekly_trades_count(self, user_id: str) -> int:
        """Retourne le nombre d'échanges effectués cette semaine"""
        try:
            sheet = self.sheet_weekly_exchanges
            all_data = sheet.get_all_values()

            # Calculer la clé de semaine actuelle
            now = datetime.now()
            week_key = now.strftime("%Y-W%W")

            for row in all_data:
                if len(row) >= 3 and row[0] == str(user_id) and row[1] == week_key:
                    try:
                        return int(row[2])
                    except ValueError:
                        return 0

            return 0
        except Exception as e:
            logger.error(f"Error getting weekly trades: {e}")
            return 0

    def can_perform_weekly_trade(self, user_id: str) -> bool:
        """Vérifie si l'utilisateur peut encore échanger cette semaine"""
        return self.get_weekly_trades_count(user_id) < 3

    def record_weekly_trade(self, user_id: str) -> bool:
        """Enregistre un échange hebdomadaire"""
        try:
            sheet = self.sheet_weekly_exchanges
            all_data = sheet.get_all_values()

            now = datetime.now()
            week_key = now.strftime("%Y-W%W")

            # Chercher si une entrée existe déjà
            for idx, row in enumerate(all_data, start=1):
                if len(row) >= 2 and row[0] == str(user_id) and row[1] == week_key:
                    current = int(row[2]) if len(row) >= 3 and row[2].isdigit() else 0
                    sheet.update_cell(idx, 3, str(current + 1))
                    return True

            # Nouvelle entrée
            sheet.append_row([str(user_id), week_key, "1"])
            return True
        except Exception as e:
            logger.error(f"Error recording weekly trade: {e}")
            return False

    # ============== Images des cartes ==============

    def get_card_image(self, file_id: str) -> Optional[bytes]:
        """Télécharge l'image d'une carte depuis Google Drive"""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            return buffer.getvalue()
        except Exception as e:
            logger.error(f"Error downloading card image: {e}")
            return None

    def find_card_file(self, category: str, name: str) -> Optional[dict]:
        """Trouve le fichier d'une carte par catégorie et nom"""
        cards = self.cards_by_category.get(category, [])
        for card in cards:
            if card['name'] == name:
                return card

        # Chercher dans les Full
        full_cards = self.full_cards_by_category.get(category, [])
        for card in full_cards:
            if card['name'] == name:
                return card

        return None

    def get_all_cards(self) -> Dict[str, List[dict]]:
        """Retourne toutes les cartes par catégorie"""
        return self.cards_by_category

    def get_all_full_cards(self) -> Dict[str, List[dict]]:
        """Retourne toutes les cartes Full par catégorie"""
        return self.full_cards_by_category


# Instance singleton
_storage_service: Optional[CardsStorageService] = None


def get_storage_service() -> CardsStorageService:
    """Retourne l'instance singleton du service de stockage"""
    global _storage_service
    if _storage_service is None:
        _storage_service = CardsStorageService()
    return _storage_service
