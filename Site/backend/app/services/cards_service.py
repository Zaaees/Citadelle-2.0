"""
Service principal pour le système de cartes.
Réutilise le code existant du bot Discord en l'important depuis cogs/cards/
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio

# Ajouter le chemin vers le code du bot
BOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../'))
sys.path.insert(0, BOT_PATH)

# Importer les modules du bot
from cogs.cards.storage import CardsStorage
from cogs.cards.drawing import DrawingManager
from cogs.cards.trading import TradingManager
from cogs.cards.vault import VaultManager
from cogs.cards.config import ALL_CATEGORIES, RARITY_WEIGHTS, DAILY_SACRIFICIAL_CARDS_COUNT

from ..core.config import settings

logger = logging.getLogger(__name__)


class CardSystemService:
    """
    Service singleton pour accéder au système de cartes.
    Réutilise la logique du bot Discord.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialise le service (une seule fois grâce au singleton)."""
        if not CardSystemService._initialized:
            self._initialize()
            CardSystemService._initialized = True

    def _initialize(self):
        """Initialise la connexion Google Sheets et les managers."""
        try:
            logger.info("🔄 Initialisation du CardSystemService...")

            # Connexion à Google Sheets
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                settings.SERVICE_ACCOUNT_INFO,
                scope
            )

            self.gspread_client = gspread.authorize(creds)

            # Initialiser Google Drive service
            from google.oauth2.service_account import Credentials as GoogleCredentials
            from googleapiclient.discovery import build

            google_creds = GoogleCredentials.from_service_account_info(
                settings.SERVICE_ACCOUNT_INFO,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            self.drive_service = build('drive', 'v3', credentials=google_creds)

            # Initialiser le storage
            self.storage = CardsStorage(
                self.gspread_client,
                settings.GOOGLE_SHEET_ID
            )

            # Charger les cartes depuis Google Drive
            self.cards_by_category, self.upgrade_cards_by_category = self._load_cards_from_drive()

            # Initialiser les managers
            self.drawing_manager = DrawingManager(
                self.storage,
                self.cards_by_category,
                self.upgrade_cards_by_category
            )

            self.vault_manager = VaultManager(self.storage)

            self.trading_manager = TradingManager(
                self.storage,
                self.vault_manager
            )

            # Injecter les méthodes nécessaires dans le trading manager
            self.trading_manager._user_has_card = self._user_has_card
            self.trading_manager._add_card_to_user = self._add_card_to_user
            self.trading_manager._remove_card_from_user = self._remove_card_from_user

            logger.info("✅ CardSystemService initialisé avec succès")

        except Exception as e:
            logger.error(f"❌ Erreur lors de l'initialisation du CardSystemService: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _load_cards_from_drive(self) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
        """
        Charge les cartes depuis Google Drive (comme le bot Discord).

        Returns:
            Tuple de (cards_by_category, upgrade_cards_by_category)
        """
        try:
            # Dictionnaire des dossiers par catégorie (IDs Google Drive)
            FOLDER_IDS = {
                "Historique": settings.FOLDER_PERSONNAGE_HISTORIQUE_ID,
                "Fondateur": settings.FOLDER_FONDATEUR_ID,
                "Black Hole": settings.FOLDER_BLACKHOLE_ID,
                "Maître": settings.FOLDER_MAITRE_ID,
                "Architectes": settings.FOLDER_ARCHITECTES_ID,
                "Professeurs": settings.FOLDER_PROFESSEURS_ID,
                "Autre": settings.FOLDER_AUTRE_ID,
                "Élèves": settings.FOLDER_ELEVES_ID,
                "Secrète": settings.FOLDER_SECRETE_ID
            }

            # Dossiers des cartes Full (optionnels)
            FULL_FOLDER_IDS = {
                "Historique": settings.FOLDER_HISTORIQUE_FULL_ID,
                "Fondateur": settings.FOLDER_FONDATEUR_FULL_ID,
                "Black Hole": settings.FOLDER_BLACKHOLE_FULL_ID,
                "Maître": settings.FOLDER_MAITRE_FULL_ID,
                "Architectes": settings.FOLDER_ARCHITECTES_FULL_ID,
                "Professeurs": settings.FOLDER_PROFESSEURS_FULL_ID,
                "Autre": settings.FOLDER_AUTRE_FULL_ID,
                "Élèves": settings.FOLDER_ELEVES_FULL_ID,
                "Secrète": settings.FOLDER_SECRETE_FULL_ID
            }

            cards_by_category = {cat: [] for cat in ALL_CATEGORIES}
            upgrade_cards_by_category = {cat: [] for cat in ALL_CATEGORIES}

            logger.info("🔄 Chargement des cartes depuis Google Drive...")

            for category, folder_id in FOLDER_IDS.items():
                if not folder_id:
                    cards_by_category[category] = []
                    upgrade_cards_by_category[category] = []
                    continue

                try:
                    # Cartes normales
                    results = self.drive_service.files().list(
                        q=f"'{folder_id}' in parents",
                        fields="files(id, name, mimeType)"
                    ).execute()

                    files = [
                        f for f in results.get('files', [])
                        if f.get('mimeType', '').startswith('image/')
                        and f['name'].lower().endswith('.png')
                    ]

                    cards_by_category[category] = [
                        {
                            "name": f['name'].removesuffix('.png'),
                            "category": category,
                            "file_id": f['id'],
                            "is_full": False
                        }
                        for f in files
                    ]

                    # Charger les cartes Full si le dossier est configuré
                    full_folder_id = FULL_FOLDER_IDS.get(category)
                    if full_folder_id:
                        try:
                            full_results = self.drive_service.files().list(
                                q=f"'{full_folder_id}' in parents",
                                fields="files(id, name, mimeType)"
                            ).execute()

                            full_files = [
                                f for f in full_results.get('files', [])
                                if f.get('mimeType', '').startswith('image/')
                                and f['name'].lower().endswith('.png')
                            ]

                            upgrade_cards_by_category[category] = [
                                {
                                    "name": f['name'].removesuffix('.png'),
                                    "category": category,
                                    "file_id": f['id'],
                                    "is_full": True
                                }
                                for f in full_files
                            ]
                            logger.info(f"✅ {len(full_files)} cartes Full chargées pour {category}")
                        except Exception as e:
                            logger.warning(f"⚠️ Erreur lors du chargement des cartes Full pour {category}: {e}")
                            upgrade_cards_by_category[category] = []
                    else:
                        upgrade_cards_by_category[category] = []

                except Exception as e:
                    logger.error(f"❌ Erreur lors du chargement de {category}: {e}")
                    cards_by_category[category] = []
                    upgrade_cards_by_category[category] = []

            total_cards = sum(len(cards) for cards in cards_by_category.values())
            total_full = sum(len(cards) for cards in upgrade_cards_by_category.values())

            logger.info(f"✅ Cartes chargées depuis Drive: {total_cards} cartes normales, {total_full} cartes Full")

            return cards_by_category, upgrade_cards_by_category

        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement des cartes depuis Drive: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}, {}

    # ----------------------------------------------------------------
    # Méthodes pour interagir avec la collection de l'utilisateur
    # ----------------------------------------------------------------

    def _user_has_card(self, user_id: int, category: str, name: str) -> bool:
        """
        Vérifie si un utilisateur possède une carte.
        Format: category | name | user_id:count | user_id:count | ...
        """
        try:
            cards_cache = self.storage.get_cards_cache()
            if not cards_cache:
                return False

            user_id_str = str(user_id)

            # Parcourir les lignes (skip header)
            for row in cards_cache[1:]:
                if len(row) < 3:
                    continue

                row_category, row_name = row[0], row[1]

                # Si c'est la bonne carte
                if row_category == category and row_name == name:
                    # Vérifier dans les cellules user_id:count
                    for cell in row[2:]:
                        if not cell:
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            if uid.strip() == user_id_str and int(count) > 0:
                                return True
                        except (ValueError, IndexError):
                            continue

            return False

        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification de possession: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _add_card_to_user(self, user_id: int, category: str, name: str) -> bool:
        """
        Ajoute une carte à la collection d'un utilisateur.
        Format: category | name | user_id:count | user_id:count | ...
        """
        try:
            with self.storage._cards_lock:
                cards_cache = self.storage.sheet_cards.get_all_values()
                if not cards_cache:
                    return False

                user_id_str = str(user_id)

                # Chercher si la carte existe déjà
                for i, row in enumerate(cards_cache):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        # Carte trouvée, chercher l'utilisateur dans les cellules
                        user_found = False
                        for j, cell in enumerate(row[2:], start=2):
                            if not cell:
                                continue
                            try:
                                uid, count = cell.split(":", 1)
                                if uid.strip() == user_id_str:
                                    # Utilisateur trouvé, incrémenter
                                    new_count = int(count) + 1
                                    row[j] = f"{user_id}:{new_count}"
                                    self.storage.sheet_cards.update(f"A{i+1}", [row])
                                    self.storage.refresh_cards_cache()
                                    logger.info(f"✅ Carte {category}/{name} ajoutée pour {user_id} (quantité: {new_count})")
                                    user_found = True
                                    return True
                            except (ValueError, IndexError):
                                continue

                        if not user_found:
                            # Utilisateur pas trouvé, l'ajouter
                            row.append(f"{user_id}:1")
                            self.storage.sheet_cards.update(f"A{i+1}", [row])
                            self.storage.refresh_cards_cache()
                            logger.info(f"✅ Nouvelle carte {category}/{name} ajoutée pour {user_id}")
                            return True

                # Si la carte n'existe pas du tout, créer une nouvelle ligne
                new_row = [category, name, f"{user_id}:1"]
                self.storage.sheet_cards.append_row(new_row)
                self.storage.refresh_cards_cache()
                logger.info(f"✅ Nouvelle ligne de carte {category}/{name} créée pour {user_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Erreur lors de l'ajout de carte: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
        """
        Retire une carte de la collection d'un utilisateur.
        Format: category | name | user_id:count | user_id:count | ...
        """
        try:
            with self.storage._cards_lock:
                cards_cache = self.storage.sheet_cards.get_all_values()
                if not cards_cache:
                    return False

                user_id_str = str(user_id)

                # Chercher la carte
                for i, row in enumerate(cards_cache):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        for j, cell in enumerate(row[2:], start=2):
                            if not cell:
                                continue
                            try:
                                uid, count = cell.split(":", 1)
                                if uid.strip() == user_id_str:
                                    count_int = int(count)
                                    if count_int > 1:
                                        # Décrémenter
                                        row[j] = f"{user_id}:{count_int - 1}"
                                    else:
                                        # Supprimer l'entrée (mettre vide)
                                        row[j] = ""

                                    self.storage.sheet_cards.update(f"A{i+1}", [row])
                                    self.storage.refresh_cards_cache()
                                    logger.info(f"✅ Carte {category}/{name} retirée pour {user_id}")
                                    return True
                            except (ValueError, IndexError):
                                continue

                logger.warning(f"⚠️ Carte {category}/{name} non trouvée pour {user_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Erreur lors du retrait de carte: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def get_user_collection(self, user_id: int) -> Dict[str, Any]:
        """
        Récupère la collection complète d'un utilisateur.
        Format: category | name | user_id:count | user_id:count | ...

        Returns:
            Dict avec cards (list), total_cards (int), unique_cards (int), completion_percentage (float)
        """
        try:
            # Utiliser la méthode du bot (en async)
            user_cards_tuples = await asyncio.to_thread(self._get_user_cards_internal, user_id)

            # Compter les cartes
            from collections import Counter
            card_counts = Counter(user_cards_tuples)

            user_cards = []
            total_cards = 0
            unique_cards = 0

            for (category, name), count in card_counts.items():
                # Determiner si c'est une carte Full (basé sur le nom)
                is_full = "(Full)" in name

                # Chercher la carte pour obtenir file_id
                card_info = None
                if is_full:
                    # Chercher dans les cartes Full
                    for card in self.upgrade_cards_by_category.get(category, []):
                        if card["name"] == name:
                            card_info = card
                            break
                else:
                    # Chercher dans les cartes normales
                    for card in self.cards_by_category.get(category, []):
                        if card["name"] == name:
                            card_info = card
                            break

                user_cards.append({
                    "category": category,
                    "name": name,
                    "count": count,
                    "acquired_date": "",  # Non disponible dans ce format
                    "file_id": card_info.get("file_id") if card_info else None,
                    "is_full": is_full
                })
                total_cards += count
                unique_cards += 1

            # Calculer le pourcentage de complétion
            total_available_cards = sum(
                len(self.cards_by_category.get(cat, []))
                for cat in ALL_CATEGORIES
            )

            completion_percentage = (unique_cards / total_available_cards * 100) if total_available_cards > 0 else 0.0
            # Plafonner à 100% maximum (peut dépasser si cartes Full comptées séparément ou doublons)
            completion_percentage = min(completion_percentage, 100.0)

            return {
                "cards": user_cards,
                "total_cards": total_cards,
                "unique_cards": unique_cards,
                "completion_percentage": round(completion_percentage, 2)
            }

        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération de la collection: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "cards": [],
                "total_cards": 0,
                "unique_cards": 0,
                "completion_percentage": 0.0
            }

    def _get_user_cards_internal(self, user_id: int) -> list[tuple[str, str]]:
        """
        Récupère les cartes d'un utilisateur (copie de la logique du bot).
        Retourne une liste de tuples (category, name) avec répétitions selon le count.
        """
        cards_cache = self.storage.get_cards_cache()
        if not cards_cache:
            return []

        user_cards = []
        for row in cards_cache[1:]:  # Skip header
            if len(row) < 3:
                continue
            cat, name = row[0], row[1]
            for cell in row[2:]:
                if not cell:
                    continue
                try:
                    uid, count = cell.split(":", 1)
                    uid = uid.strip()
                    if int(uid) == user_id:
                        user_cards.extend([(cat, name)] * int(count))
                except (ValueError, IndexError):
                    continue
        return user_cards

    # ----------------------------------------------------------------
    # Méthodes utilitaires
    # ----------------------------------------------------------------

    def get_all_cards(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Récupère toutes les cartes, optionnellement filtrées par catégorie."""
        try:
            all_cards = []

            categories_to_check = [category] if category else ALL_CATEGORIES

            for cat in categories_to_check:
                # Cartes normales
                for card in self.cards_by_category.get(cat, []):
                    all_cards.append({
                        "category": cat,
                        "name": card["name"].removesuffix(".png"),
                        "file_id": card.get("file_id"),
                        "is_full": False,
                        "rarity_weight": RARITY_WEIGHTS.get(cat, 0)
                    })

                # Cartes Full
                for card in self.upgrade_cards_by_category.get(cat, []):
                    all_cards.append({
                        "category": cat,
                        "name": card["name"].removesuffix(".png"),
                        "file_id": card.get("file_id"),
                        "is_full": True,
                        "rarity_weight": RARITY_WEIGHTS.get(cat, 0)
                    })

            return all_cards

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des cartes: {e}")
            return []

    def get_categories_info(self) -> List[Dict[str, Any]]:
        """Recupere les informations sur les categories de cartes."""
        categories_info = []

        total_cards = sum(
            len(self.cards_by_category.get(cat, []))
            for cat in ALL_CATEGORIES
        )

        for category in ALL_CATEGORIES:
            card_count = len(self.cards_by_category.get(category, []))
            categories_info.append({
                "category": category,
                "weight": RARITY_WEIGHTS.get(category, 0),
                "total_cards": card_count,
                "percentage": (card_count / total_cards * 100) if total_cards > 0 else 0
            })

        return categories_info

    # ----------------------------------------------------------------
    # Methodes pour les bonus
    # ----------------------------------------------------------------

    def get_user_bonus_count(self, user_id: int) -> int:
        """
        Recupere le nombre de tirages bonus disponibles pour un utilisateur.
        Format de la feuille Bonus: user_id | count | source

        Args:
            user_id: ID de l'utilisateur

        Returns:
            int: Nombre total de tirages bonus disponibles
        """
        user_id_str = str(user_id)

        try:
            all_rows = self.storage.sheet_bonus.get_all_values()[1:]  # skip header

            user_bonus = 0

            for row in all_rows:
                if len(row) >= 2 and row[0] == user_id_str:
                    try:
                        user_bonus += int(row[1])
                    except (ValueError, IndexError):
                        continue

            return user_bonus

        except Exception as e:
            logger.error(f"Erreur lors de la lecture des bonus: {e}")
            return 0

    def consume_user_bonus(self, user_id: int) -> bool:
        """
        Consomme un tirage bonus pour un utilisateur.
        Decremente le premier bonus trouve ou le supprime s'il n'en reste qu'un.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            bool: True si un bonus a ete consomme avec succes
        """
        user_id_str = str(user_id)

        try:
            all_data = self.storage.sheet_bonus.get_all_values()
            if not all_data:
                return False

            # Chercher la premiere ligne avec des bonus pour cet utilisateur
            for i, row in enumerate(all_data[1:], start=2):  # start=2 car row 1 est header
                if len(row) >= 2 and row[0] == user_id_str:
                    try:
                        current_count = int(row[1])
                        if current_count > 1:
                            # Decrementer
                            self.storage.sheet_bonus.update_cell(i, 2, str(current_count - 1))
                            logger.info(f"Bonus decremente pour {user_id}: {current_count} -> {current_count - 1}")
                            return True
                        elif current_count == 1:
                            # Supprimer la ligne
                            self.storage.sheet_bonus.delete_rows(i)
                            logger.info(f"Bonus supprime pour {user_id}")
                            return True
                    except (ValueError, IndexError):
                        continue

            logger.warning(f"Aucun bonus trouve pour {user_id}")
            return False

        except Exception as e:
            logger.error(f"Erreur lors de la consommation du bonus: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # ----------------------------------------------------------------
    # Statistiques utilisateur
    # ----------------------------------------------------------------

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Recupere les statistiques completes d'un utilisateur.

        Returns:
            Dict avec toutes les stats (collection, tirages, echanges, decouvertes)
        """
        try:
            # Collection
            collection_data = await self.get_user_collection(user_id)

            # Stats par categorie
            cards_by_rarity = {}
            for cat in ALL_CATEGORIES:
                cards_by_rarity[cat] = sum(
                    1 for card in collection_data["cards"]
                    if card["category"] == cat
                )

            # Cartes Full
            full_cards_count = sum(
                1 for card in collection_data["cards"]
                if card.get("is_full", False)
            )

            # Bonus disponibles
            bonus_count = self.get_user_bonus_count(user_id)

            # Tirages disponibles
            can_daily = self.drawing_manager.can_perform_daily_draw(user_id, check_only=True)
            # can_perform_sacrificial_draw n'a pas de parametre check_only
            can_sacrificial = self.drawing_manager.can_perform_sacrificial_draw(user_id)

            # Echanges hebdomadaires
            weekly_exchanges = self._get_user_weekly_exchange_count(user_id)

            # Decouvertes de l'utilisateur
            discoveries_count = self._count_user_discoveries(user_id)

            # Calculer le total de cartes disponibles dans le jeu
            total_available = sum(
                len(self.cards_by_category.get(cat, []))
                for cat in ALL_CATEGORIES
            )

            # Calculer le nombre de cartes disponibles PAR categorie
            available_by_category = {}
            for cat in ALL_CATEGORIES:
                available_by_category[cat] = len(self.cards_by_category.get(cat, []))

            # Recalculer le pourcentage de completion correctement
            real_completion = (collection_data["unique_cards"] / total_available * 100) if total_available > 0 else 0.0

            return {
                "total_cards": collection_data["total_cards"],
                "unique_cards": collection_data["unique_cards"],
                "full_cards": full_cards_count,
                "completion_percentage": round(real_completion, 2),
                "total_available_cards": total_available,
                "cards_by_rarity": cards_by_rarity,
                "available_by_category": available_by_category,
                "bonus_available": bonus_count,
                "can_daily_draw": can_daily,
                "can_sacrificial_draw": can_sacrificial,
                "weekly_exchanges_used": weekly_exchanges,
                "weekly_exchanges_remaining": 3 - weekly_exchanges,
                "discoveries_count": discoveries_count
            }

        except Exception as e:
            logger.error(f"Erreur lors de la recuperation des stats: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def _count_user_discoveries(self, user_id: int) -> int:
        """Compte le nombre de decouvertes faites par l'utilisateur."""
        try:
            user_id_str = str(user_id)
            discoveries = self.storage.sheet_discoveries.get_all_values()[1:]  # skip header

            count = 0
            for row in discoveries:
                if len(row) >= 3 and row[2] == user_id_str:  # discoverer_id is column 3
                    count += 1

            return count

        except Exception as e:
            logger.error(f"Erreur lors du comptage des decouvertes: {e}")
            return 0

    def _get_user_weekly_exchange_count(self, user_id: int) -> int:
        """
        Compte le nombre d'echanges hebdomadaires effectues par l'utilisateur cette semaine.
        La semaine commence le lundi.
        """
        try:
            import pytz
            from datetime import datetime, timedelta

            # Calculer la semaine actuelle (lundi = debut de semaine, timezone Paris)
            paris_tz = pytz.timezone("Europe/Paris")
            now = datetime.now(paris_tz)
            monday = now - timedelta(days=now.weekday())
            week_key = monday.strftime("%Y-W%U")

            user_id_str = str(user_id)

            # Verifier dans la feuille des echanges hebdomadaires
            all_rows = self.storage.sheet_weekly_exchanges.get_all_values()

            for row in all_rows:
                if len(row) >= 3 and row[0] == user_id_str and row[1] == week_key:
                    return int(row[2])

            return 0  # Aucun echange cette semaine

        except Exception as e:
            logger.error(f"Erreur lors du comptage des echanges hebdomadaires: {e}")
            return 0

    # ----------------------------------------------------------------
    # Cache des utilisateurs (pour afficher les pseudos Discord)
    # ----------------------------------------------------------------

    def update_user_cache(self, user_id: int, username: str, global_name: Optional[str] = None) -> None:
        """
        Met a jour le cache des utilisateurs avec le pseudo Discord.
        Cree ou met a jour une feuille 'UserCache' dans Google Sheets.
        Format: user_id | username | global_name | last_seen
        """
        try:
            # Obtenir ou creer la feuille UserCache
            try:
                sheet_users = self.storage.spreadsheet.worksheet("UserCache")
            except Exception:
                sheet_users = self.storage.spreadsheet.add_worksheet(
                    title="UserCache", rows="1000", cols="4"
                )
                sheet_users.append_row(["user_id", "username", "global_name", "last_seen"])

            user_id_str = str(user_id)
            from datetime import datetime
            import pytz
            now = datetime.now(pytz.timezone("Europe/Paris")).isoformat()

            # Chercher si l'utilisateur existe deja
            all_rows = sheet_users.get_all_values()
            for i, row in enumerate(all_rows[1:], start=2):
                if len(row) >= 1 and row[0] == user_id_str:
                    # Mettre a jour
                    sheet_users.update(f"A{i}", [[user_id_str, username, global_name or "", now]])
                    logger.info(f"Cache utilisateur mis a jour: {username} ({user_id})")
                    return

            # Ajouter nouvel utilisateur
            sheet_users.append_row([user_id_str, username, global_name or "", now])
            logger.info(f"Nouvel utilisateur dans le cache: {username} ({user_id})")

        except Exception as e:
            logger.error(f"Erreur lors de la mise a jour du cache utilisateur: {e}")

    def get_username(self, user_id: int) -> Optional[str]:
        """
        Recupere le pseudo Discord d'un utilisateur depuis le cache.

        Returns:
            Le global_name si disponible, sinon le username, sinon None
        """
        try:
            try:
                sheet_users = self.storage.spreadsheet.worksheet("UserCache")
            except Exception:
                return None

            user_id_str = str(user_id)
            all_rows = sheet_users.get_all_values()

            for row in all_rows[1:]:
                if len(row) >= 2 and row[0] == user_id_str:
                    # Retourner global_name si present, sinon username
                    if len(row) >= 3 and row[2]:
                        return row[2]
                    return row[1]

            return None

        except Exception as e:
            logger.error(f"Erreur lors de la recuperation du pseudo: {e}")
            return None


# Instance globale du service
card_system = CardSystemService()
