"""
Cog principal pour le système de cartes à collectionner.
Version refactorisée avec modules séparés.
"""

from discord import app_commands
from discord.ext import commands
import discord
import os
import json
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread

# Imports des modules du système de cartes
from .cards.storage import CardsStorage
from .cards.discovery import DiscoveryManager
from .cards.vault import VaultManager
from .cards.drawing import DrawingManager
from .cards.trading import TradingManager
from .cards.forum import ForumManager
from .cards.config import *
from .cards.utils import *
from .cards.models import *
from .cards.views import *

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class Cards(commands.Cog):
    """Cog principal pour le système de cartes à collectionner."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Initialiser les credentials Google
        creds_info = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
        creds = Credentials.from_service_account_info(creds_info, scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ])
        
        # Client Google Sheets
        self.gspread_client = gspread.authorize(creds)
        
        # Service Google Drive pour accéder aux images des cartes
        self.drive_service = build('drive', 'v3', credentials=creds)
        
        # Initialiser le système de stockage
        self.storage = CardsStorage(self.gspread_client, os.getenv('GOOGLE_SHEET_ID_CARTES'))
        
        # Dictionnaire des dossiers par rareté (IDs des dossiers Google Drive depuis .env)
        self.FOLDER_IDS = {
            "Historique": os.getenv("FOLDER_PERSONNAGE_HISTORIQUE_ID"),
            "Fondateur": os.getenv("FOLDER_FONDATEUR_ID"),
            "Black Hole": os.getenv("FOLDER_BLACKHOLE_ID"),
            "Maître": os.getenv("FOLDER_MAITRE_ID"),
            "Architectes": os.getenv("FOLDER_ARCHITECTES_ID"),
            "Professeurs": os.getenv("FOLDER_PROFESSEURS_ID"),
            "Autre": os.getenv("FOLDER_AUTRE_ID"),
            "Élèves": os.getenv("FOLDER_ELEVES_ID"),
            "Secrète": os.getenv("FOLDER_SECRETE_ID")
        }
        
        # Pré-charger la liste des fichiers (cartes) dans chaque dossier de rareté
        self.cards_by_category = {}
        self.upgrade_cards_by_category = {}
        self._load_card_files()
        
        # Initialiser les gestionnaires
        self.discovery_manager = DiscoveryManager(self.storage)
        self.vault_manager = VaultManager(self.storage)
        self.drawing_manager = DrawingManager(self.storage, self.cards_by_category, self.upgrade_cards_by_category)
        self.trading_manager = TradingManager(self.storage, self.vault_manager)
        self.forum_manager = ForumManager(self.bot, self.discovery_manager)
        
        # Connecter les méthodes manquantes du trading manager
        self.trading_manager._user_has_card = self._user_has_card
        self.trading_manager._add_card_to_user = self.add_card_to_user
        self.trading_manager._remove_card_from_user = self.remove_card_from_user

        # Ajouter une référence au cog dans le storage pour les vérifications d'upgrade
        self.storage._cog_ref = self

        # Initialiser le système de vérification automatique des upgrades
        self._users_needing_upgrade_check = set()

    def _normalize_category_for_env_var(self, category: str) -> str:
        """
        Normalise un nom de catégorie pour les variables d'environnement.
        Supprime les accents et caractères spéciaux.
        """
        # Remplacer les accents courants
        normalized = category.replace('é', 'e').replace('è', 'e').replace('à', 'a').replace('ù', 'u').replace('ç', 'c')
        normalized = normalized.replace('É', 'E').replace('È', 'E').replace('À', 'A').replace('Ù', 'U').replace('Ç', 'C')
        # Remplacer espaces par underscores et mettre en majuscules
        return normalized.upper().replace(' ', '_')
    
    def _load_card_files(self):
        """Charge les fichiers de cartes depuis Google Drive."""
        for category, folder_id in self.FOLDER_IDS.items():
            if folder_id:
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
                self.cards_by_category[category] = files
                
                # Cartes Full (variantes)
                normalized_category = self._normalize_category_for_env_var(category)
                full_folder_var = f"FOLDER_{normalized_category}_FULL_ID"
                full_folder_id = os.getenv(full_folder_var)

                if full_folder_id:
                    logging.info(f"[CARDS] Chargement des cartes Full pour {category} depuis le dossier {full_folder_id}")
                    full_results = self.drive_service.files().list(
                        q=f"'{full_folder_id}' in parents",
                        fields="files(id, name, mimeType)"
                    ).execute()

                    full_files = [
                        f for f in full_results.get('files', [])
                        if f.get('mimeType', '').startswith('image/')
                        and f['name'].lower().endswith('.png')
                    ]
                    self.upgrade_cards_by_category[category] = full_files
                    logging.info(f"[CARDS] {len(full_files)} cartes Full chargées pour {category}")
                else:
                    logging.warning(f"[CARDS] Variable d'environnement {full_folder_var} non définie - aucune carte Full pour {category}")
                    self.upgrade_cards_by_category[category] = []
    
    # ========== MÉTHODES D'INTERFACE POUR LES GESTIONNAIRES ==========
    
    def get_user_cards(self, user_id: int) -> list[tuple[str, str]]:
        """Récupère les cartes d'un utilisateur."""
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
                except (ValueError, IndexError) as e:
                    logging.warning(f"[SECURITY] Données corrompues dans get_user_cards: {cell}, erreur: {e}")
                    continue
        return user_cards
    
    def add_card_to_user(self, user_id: int, category: str, name: str,
                        user_name: str = None, source: str = None) -> bool:
        """Ajoute une carte à l'inventaire d'un utilisateur."""
        with self.storage._cards_lock:
            try:
                if not validate_card_data(category, name, user_id):
                    return False
                
                cards_cache = self.storage.get_cards_cache()
                if not cards_cache:
                    return False
                
                # Chercher si la carte existe déjà
                for i, row in enumerate(cards_cache):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        # Carte trouvée, ajouter l'utilisateur ou incrémenter
                        original_len = len(row)
                        for j, cell in enumerate(row[2:], start=2):
                            if not cell:
                                continue
                            try:
                                uid, count = cell.split(":", 1)
                                uid = uid.strip()
                                if int(uid) == user_id:
                                    # Utilisateur trouvé, incrémenter
                                    new_count = int(count) + 1
                                    row[j] = f"{user_id}:{new_count}"
                                    cleaned_row = merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.storage.sheet_cards.update(f"A{i+1}", [cleaned_row])
                                    self.storage.refresh_cards_cache()

                                    # Marquer cet utilisateur pour vérification d'upgrade automatique
                                    self._mark_user_for_upgrade_check(user_id)

                                    # Logger l'ajout de carte
                                    if self.storage.logging_manager:
                                        self.storage.logging_manager.log_card_add(
                                            user_id=user_id,
                                            user_name=user_name or f"User_{user_id}",
                                            category=category,
                                            name=name,
                                            quantity=1,
                                            source=source or "add_card_to_user"
                                        )

                                    return True
                            except (ValueError, IndexError):
                                continue
                        
                        # Utilisateur pas trouvé, l'ajouter
                        row.append(f"{user_id}:1")
                        cleaned_row = merge_cells(row)
                        pad = max(original_len + 1, len(cleaned_row)) - len(cleaned_row)
                        cleaned_row += [""] * pad
                        self.storage.sheet_cards.update(f"A{i+1}", [cleaned_row])
                        self.storage.refresh_cards_cache()

                        # Marquer cet utilisateur pour vérification d'upgrade automatique
                        self._mark_user_for_upgrade_check(user_id)

                        # Logger l'ajout de carte
                        if self.storage.logging_manager:
                            self.storage.logging_manager.log_card_add(
                                user_id=user_id,
                                user_name=user_name or f"User_{user_id}",
                                category=category,
                                name=name,
                                quantity=1,
                                source=source or "add_card_to_user"
                            )

                        return True
                
                # Si la carte n'existe pas encore
                new_row = [category, name, f"{user_id}:1"]
                self.storage.sheet_cards.append_row(new_row)
                self.storage.refresh_cards_cache()

                # Marquer cet utilisateur pour vérification d'upgrade automatique
                self._mark_user_for_upgrade_check(user_id)

                # Logger l'ajout de carte
                if self.storage.logging_manager:
                    self.storage.logging_manager.log_card_add(
                        user_id=user_id,
                        user_name=user_name or f"User_{user_id}",
                        category=category,
                        name=name,
                        quantity=1,
                        source=source or "add_card_to_user"
                    )

                return True

            except Exception as e:
                logging.error(f"[CARDS] Erreur lors de l'ajout de carte: {e}")
                return False
    
    def remove_card_from_user(self, user_id: int, category: str, name: str,
                             user_name: str = None, source: str = None) -> bool:
        """Retire une carte de l'inventaire d'un utilisateur."""
        with self.storage._cards_lock:
            try:
                if not validate_card_data(category, name, user_id):
                    return False
                
                cards_cache = self.storage.get_cards_cache()
                if not cards_cache:
                    return False
                
                for i, row in enumerate(cards_cache):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        original_len = len(row)
                        for j, cell in enumerate(row[2:], start=2):
                            if not cell:
                                continue
                            try:
                                uid, count = cell.split(":", 1)
                                uid = uid.strip()
                                if int(uid) == user_id:
                                    count = int(count)
                                    if count > 1:
                                        # Décrémenter
                                        row[j] = f"{user_id}:{count-1}"
                                    else:
                                        # Supprimer l'entrée
                                        row[j] = ""
                                    
                                    cleaned_row = merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.storage.sheet_cards.update(f"A{i+1}", [cleaned_row])
                                    self.storage.refresh_cards_cache()

                                    # Logger le retrait de carte
                                    if self.storage.logging_manager:
                                        self.storage.logging_manager.log_card_remove(
                                            user_id=user_id,
                                            user_name=user_name or f"User_{user_id}",
                                            category=category,
                                            name=name,
                                            quantity=1,
                                            source=source or "remove_card_from_user"
                                        )

                                    return True
                            except (ValueError, IndexError):
                                continue
                
                return False
                
            except Exception as e:
                logging.error(f"[CARDS] Erreur lors du retrait de carte: {e}")
                return False

    def batch_remove_cards_from_user(self, user_id: int, cards_to_remove: list[tuple[str, str]]) -> bool:
        """
        Supprime plusieurs cartes pour un utilisateur en une seule opération batch.
        OPTIMISÉ pour le tirage sacrificiel.

        Args:
            user_id: ID de l'utilisateur
            cards_to_remove: Liste de tuples (category, name) des cartes à supprimer

        Returns:
            bool: True si toutes les suppressions ont réussi, False sinon
        """
        with self.storage._cards_lock:
            try:
                # Validation des paramètres d'entrée
                if user_id <= 0 or not cards_to_remove:
                    logging.error(f"[SECURITY] Paramètres invalides pour batch_remove_cards_from_user: user_id={user_id}, cards={len(cards_to_remove)}")
                    return False

                # Compter les cartes à supprimer
                from collections import Counter
                cards_counter = Counter(cards_to_remove)

                # Vérifier que l'utilisateur possède toutes ces cartes
                user_cards = self.get_user_cards(user_id)
                user_cards_counter = Counter(user_cards)

                for (cat, name), count_needed in cards_counter.items():
                    if user_cards_counter.get((cat, name), 0) < count_needed:
                        logging.error(f"[SECURITY] Tentative de suppression batch d'une carte non possédée en quantité suffisante: user_id={user_id}, carte=({cat}, {name}), besoin={count_needed}, possédé={user_cards_counter.get((cat, name), 0)}")
                        return False

                # Effectuer les suppressions en batch
                cards_cache = self.storage.get_cards_cache()
                if not cards_cache:
                    return False

                updates_to_make = []  # Liste des mises à jour à effectuer

                for i, row in enumerate(cards_cache):
                    if len(row) < 2:
                        continue

                    card_key = (row[0], row[1])
                    if card_key in cards_counter:
                        cards_to_remove_count = cards_counter[card_key]
                        original_len = len(row)
                        row_modified = False

                        for j in range(2, len(row)):
                            cell = row[j].strip()
                            if cell.startswith(f"{user_id}:"):
                                try:
                                    uid, count = cell.split(":", 1)
                                    uid = uid.strip()
                                    current_count = int(count)
                                    new_count = current_count - cards_to_remove_count

                                    if new_count > 0:
                                        row[j] = f"{uid}:{new_count}"
                                    else:
                                        row[j] = ""

                                    row_modified = True
                                    break
                                except (ValueError, IndexError) as e:
                                    logging.error(f"[SECURITY] Données corrompues dans batch_remove_cards_from_user: {cell}, erreur: {e}")
                                    return False

                        if row_modified:
                            cleaned_row = merge_cells(row)
                            pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                            cleaned_row += [""] * pad
                            updates_to_make.append((i+1, cleaned_row))

                # Effectuer toutes les mises à jour
                for row_num, cleaned_row in updates_to_make:
                    self.storage.sheet_cards.update(f"A{row_num}", [cleaned_row])

                # Rafraîchir le cache une seule fois
                self.storage.refresh_cards_cache()
                logging.info(f"[BATCH] Suppression batch réussie: {len(cards_to_remove)} cartes pour l'utilisateur {user_id}")
                return True

            except Exception as e:
                logging.error(f"[SECURITY] Erreur lors de la suppression batch de cartes: {e}")
                return False

    def batch_add_cards_to_user(self, user_id: int, cards_to_add: list[tuple[str, str]]) -> bool:
        """
        Ajoute plusieurs cartes pour un utilisateur en une seule opération batch.
        OPTIMISÉ pour le tirage sacrificiel.

        Args:
            user_id: ID de l'utilisateur
            cards_to_add: Liste de tuples (category, name) des cartes à ajouter

        Returns:
            bool: True si tous les ajouts ont réussi, False sinon
        """
        with self.storage._cards_lock:
            try:
                # Validation des paramètres d'entrée
                if user_id <= 0 or not cards_to_add:
                    logging.error(f"[SECURITY] Paramètres invalides pour batch_add_cards_to_user: user_id={user_id}, cards={len(cards_to_add)}")
                    return False

                # Compter les cartes à ajouter
                from collections import Counter
                cards_counter = Counter(cards_to_add)

                # Vérifier que toutes les cartes existent
                all_files = {}
                for cat, files in self.cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)
                for cat, files in self.upgrade_cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)

                for (cat, name), _ in cards_counter.items():
                    card_exists = any(
                        f['name'].removesuffix('.png') == name
                        for f in all_files.get(cat, [])
                    )
                    if not card_exists:
                        logging.error(f"[SECURITY] Tentative d'ajout batch d'une carte inexistante: ({cat}, {name})")
                        return False

                # Effectuer les ajouts en batch
                cards_cache = self.storage.get_cards_cache()
                if not cards_cache:
                    return False

                updates_to_make = []  # Liste des mises à jour à effectuer
                new_rows_to_add = []  # Liste des nouvelles lignes à ajouter

                for (cat, name), count_to_add in cards_counter.items():
                    card_found = False

                    # Chercher si la carte existe déjà
                    for i, row in enumerate(cards_cache):
                        if len(row) >= 2 and row[0] == cat and row[1] == name:
                            card_found = True
                            original_len = len(row)
                            user_found = False

                            # Chercher l'utilisateur dans cette ligne
                            for j in range(2, len(row)):
                                cell = row[j].strip()
                                if cell.startswith(f"{user_id}:"):
                                    try:
                                        uid, current_count = cell.split(":", 1)
                                        new_count = int(current_count) + count_to_add
                                        row[j] = f"{uid}:{new_count}"
                                        user_found = True
                                        break
                                    except (ValueError, IndexError) as e:
                                        logging.error(f"[SECURITY] Données corrompues dans batch_add_cards_to_user: {cell}, erreur: {e}")
                                        return False

                            if not user_found:
                                # Ajouter l'utilisateur à cette ligne
                                row.append(f"{user_id}:{count_to_add}")

                            cleaned_row = merge_cells(row)
                            pad = max(original_len + (0 if user_found else 1), len(cleaned_row)) - len(cleaned_row)
                            cleaned_row += [""] * pad
                            updates_to_make.append((i+1, cleaned_row))
                            break

                    if not card_found:
                        # Créer une nouvelle ligne pour cette carte
                        new_rows_to_add.append([cat, name, f"{user_id}:{count_to_add}"])

                # Effectuer toutes les mises à jour
                for row_num, cleaned_row in updates_to_make:
                    self.storage.sheet_cards.update(f"A{row_num}", [cleaned_row])

                # Ajouter les nouvelles lignes
                for new_row in new_rows_to_add:
                    self.storage.sheet_cards.append_row(new_row)

                # Rafraîchir le cache une seule fois
                self.storage.refresh_cards_cache()
                logging.info(f"[BATCH] Ajout batch réussi: {len(cards_to_add)} cartes pour l'utilisateur {user_id}")
                return True

            except Exception as e:
                logging.error(f"[SECURITY] Erreur lors de l'ajout batch de cartes: {e}")
                return False

    def build_card_embed(self, cat: str, name: str, file_bytes: bytes, user: discord.User = None,
                         show_inventory_info: bool = True) -> tuple[discord.Embed, discord.File]:
        """Construit un embed et le fichier attaché pour une carte.

        Le fichier utilise toujours le nom constant ``card.png`` afin que
        l'URL ``attachment://card.png`` reste stable et ne dépende pas du nom
        de la carte fourni par l'utilisateur.

        Args:
            cat: Catégorie de la carte
            name: Nom de la carte
            file_bytes: Données binaires de l'image
            user: Utilisateur qui a effectué le tirage (optionnel)
            show_inventory_info: Si True, affiche les informations d'inventaire (défaut: True)
        """
        import io
        file = discord.File(io.BytesIO(file_bytes), filename="card.png")

        description = f"Catégorie : **{cat}**"
        if user:
            description += f"\n🎯 Tiré par : **{user.display_name}**"

        # Ajouter les informations d'inventaire si demandé et si un utilisateur est fourni
        if show_inventory_info and user:
            try:
                # Compter le nombre d'exemplaires actuels (avant ajout de cette carte)
                current_count = self.get_user_card_count(user.id, cat, name)

                if current_count == 0:
                    description += f"\n✨ **NOUVELLE CARTE !**"
                else:
                    # Afficher le nombre total après ajout de cette carte
                    total_count = current_count + 1
                    description += f"\n📊 Vous en avez maintenant : **{total_count}**"

                # Vérifier le statut Full pour les cartes qui peuvent en avoir
                if self.can_have_full_version(cat, name):
                    has_full = self.user_has_full_version(user.id, cat, name)
                    if has_full:
                        description += f"\n⭐ Vous possédez déjà la version **Full** !"
                    else:
                        description += f"\n💫 Version **Full** pas encore obtenue"
            except Exception as e:
                logging.error(f"[EMBED] Erreur lors de l'ajout des informations d'inventaire: {e}")
                # Continuer sans les informations d'inventaire en cas d'erreur

        embed = discord.Embed(
            title=name,
            description=description,
            color=0x4E5D94,
        )
        embed.set_image(url="attachment://card.png")
        return embed, file

    async def _handle_announce_and_wall(self, interaction: discord.Interaction, drawn_cards: list[tuple[str, str]]):
        """Gère les annonces publiques et le mur des cartes."""
        # Le système forum est maintenant toujours activé
        await self._handle_forum_posting(interaction, drawn_cards)

    async def _handle_forum_posting(self, interaction: discord.Interaction, drawn_cards: list[tuple[str, str]]):
        """Nouvelle méthode pour poster les cartes dans le système forum."""
        try:
            # 1) Charger toutes les cartes déjà découvertes
            discovered_cards = self.discovery_manager.get_discovered_cards()

            # 2) Fusionner les fichiers "normaux" et "Full"
            all_files = {}
            for cat, files in self.cards_by_category.items():
                all_files.setdefault(cat, []).extend(files)
            for cat, files in self.upgrade_cards_by_category.items():
                all_files.setdefault(cat, []).extend(files)

            # 3) Identifier les nouvelles cartes (non découvertes)
            new_draws = [card for card in drawn_cards if card not in discovered_cards]
            if not new_draws:
                return

            # 4) Poster chaque nouvelle carte dans son thread de catégorie
            for cat, name in new_draws:
                file_id = next(
                    (f['id'] for f in all_files.get(cat, [])
                    if f['name'].removesuffix(".png") == name),
                    None
                )
                if not file_id:
                    continue

                # Enregistrer la découverte et obtenir l'index
                discovery_index = self.discovery_manager.log_discovery(cat, name, interaction.user.id, interaction.user.display_name)

                # Télécharger l'image
                file_bytes = self.download_drive_file(file_id)
                if not file_bytes:
                    logging.error(f"[FORUM] Impossible de télécharger l'image pour {name} ({cat})")
                    continue

                # Poster dans le forum (la méthode gère la création de thread si nécessaire)
                success = await self.forum_manager.post_card_to_forum(
                    cat, name, file_bytes,
                    interaction.user.display_name, discovery_index
                )

                if not success:
                    logging.error(f"[FORUM] Échec du post de la carte {name} ({cat}) dans le forum")

            # 5) Mettre à jour le message de progression dans le canal principal
            await self._update_progress_message(discovered_cards, new_draws)

        except Exception as e:
            logging.error(f"[FORUM] Erreur lors du posting forum: {e}")

    async def _update_progress_message(self, discovered_cards: set, new_draws: list):
        """Met à jour le message de progression des découvertes dans le forum."""
        try:
            # Pour le système forum, mettre à jour les headers des threads
            forum_channel = self.bot.get_channel(CARD_FORUM_CHANNEL_ID)
            if forum_channel and isinstance(forum_channel, discord.ForumChannel):
                # Mettre à jour les headers des threads concernés par les nouvelles cartes
                updated_categories = set()
                for cat, name in new_draws:
                    # Déterminer la catégorie du thread
                    if name.removesuffix('.png').endswith(' (Full)'):
                        updated_categories.add("Full")
                    else:
                        updated_categories.add(cat)

                # Mettre à jour les headers des catégories concernées
                for category in updated_categories:
                    try:
                        await self.forum_manager.update_category_thread_header(forum_channel, category)
                    except Exception as e:
                        logging.error(f"[FORUM] Erreur mise à jour header {category}: {e}")
        except Exception as e:
            logging.error(f"[PROGRESS] Erreur lors de la mise à jour du message de progression: {e}")

    def download_drive_file(self, file_id: str) -> bytes | None:
        """Télécharge un fichier depuis Google Drive."""
        try:
            logging.debug(f"[DRIVE] Téléchargement du fichier {file_id}")
            request = self.drive_service.files().get_media(fileId=file_id)
            file_bytes = request.execute()
            logging.debug(f"[DRIVE] Fichier téléchargé avec succès: {len(file_bytes)} bytes")
            return file_bytes
        except Exception as e:
            logging.error(f"[DRIVE] Erreur lors du téléchargement du fichier {file_id}: {e}")
            return None

    async def check_for_upgrades(self, interaction: discord.Interaction, user_id: int, drawn_cards: list[tuple[str, str]]):
        """
        Pour chaque carte normale où l'utilisateur a atteint le seuil de
        doublons, on échange les N doublons contre la version Full,
        on notifie l'utilisateur et on met à jour le mur.
        """
        await self.check_for_upgrades_with_channel(interaction, user_id, drawn_cards, None)

    def _mark_user_for_upgrade_check(self, user_id: int):
        """
        Marque un utilisateur pour vérification d'upgrade automatique.

        Args:
            user_id: ID de l'utilisateur
        """
        self._users_needing_upgrade_check.add(user_id)
        logging.debug(f"[AUTO_UPGRADE] Utilisateur {user_id} marqué pour vérification d'upgrade")

    async def auto_check_upgrades(self, interaction: discord.Interaction, user_id: int, notification_channel_id: int = None):
        """
        Vérification automatique des conversions vers les cartes Full.
        Cette méthode doit être appelée après chaque opération qui modifie l'inventaire d'un utilisateur.

        Args:
            interaction: L'interaction Discord
            user_id: ID de l'utilisateur
            notification_channel_id: ID du salon où envoyer les notifications (optionnel)
        """
        try:
            await self.check_for_upgrades_with_channel(interaction, user_id, [], notification_channel_id)
            logging.info(f"[AUTO_UPGRADE] Vérification automatique des conversions terminée pour l'utilisateur {user_id}")
        except Exception as e:
            logging.error(f"[AUTO_UPGRADE] Erreur lors de la vérification automatique des conversions pour l'utilisateur {user_id}: {e}")

    async def process_all_pending_upgrade_checks(self, interaction: discord.Interaction, notification_channel_id: int = None):
        """
        Traite toutes les vérifications d'upgrade en attente.

        Args:
            interaction: L'interaction Discord
            notification_channel_id: ID du salon où envoyer les notifications (optionnel)
        """
        if not self._users_needing_upgrade_check:
            return

        users_to_check = self._users_needing_upgrade_check.copy()
        self._users_needing_upgrade_check.clear()

        for user_id in users_to_check:
            try:
                await self.auto_check_upgrades(interaction, user_id, notification_channel_id)
            except Exception as e:
                logging.error(f"[AUTO_UPGRADE] Erreur lors de la vérification des upgrades pour l'utilisateur {user_id}: {e}")

    async def check_for_upgrades_with_channel(self, interaction: discord.Interaction, user_id: int, drawn_cards: list[tuple[str, str]], notification_channel_id: int = None):
        """
        Pour chaque carte normale où l'utilisateur a atteint le seuil de
        doublons, on échange les N doublons contre la version Full,
        on notifie l'utilisateur et on met à jour le mur.

        Args:
            interaction: L'interaction Discord
            user_id: ID de l'utilisateur
            drawn_cards: Liste des cartes tirées (pour compatibilité)
            notification_channel_id: ID du salon où envoyer les notifications (optionnel)
        """
        try:
            # Seuils de conversion (nombre de cartes normales pour obtenir une Full)
            # Toutes les catégories peuvent être échangées avec un seuil de 5 cartes
            upgrade_thresholds = {
                "Secrète": 5,
                "Fondateur": 5,
                "Historique": 5,
                "Maître": 5,
                "Black Hole": 5,
                "Architectes": 5,
                "Professeurs": 5,
                "Autre": 5,
                "Élèves": 5
            }

            # 1) Récupérer tous les doublons de l'utilisateur
            user_cards = self.get_user_cards(user_id)
            # Compter les occurrences par (catégorie, nom)
            counts: dict[tuple[str,str], int] = {}
            for cat, name in user_cards:
                counts[(cat, name)] = counts.get((cat, name), 0) + 1

            # 2) Pour chaque carte où count >= seuil, effectuer l'upgrade
            for (cat, name), count in counts.items():
                if cat not in upgrade_thresholds:
                    continue
                seuil = upgrade_thresholds[cat]
                if count >= seuil:
                    # NOUVELLE LOGIQUE: Vérifier d'abord si la carte Full existe avant de retirer les cartes
                    full_name = f"{name} (Full)"

                    # Chercher la carte Full correspondante dans toutes les catégories
                    file_id = None

                    # D'abord chercher dans la catégorie d'origine
                    available_full_cards = self.upgrade_cards_by_category.get(cat, [])
                    logging.info(f"[UPGRADE] Recherche de {full_name} dans {cat}. Cartes Full disponibles: {len(available_full_cards)}")

                    if available_full_cards:
                        for f in available_full_cards:
                            card_file_name = f['name'].removesuffix(".png")
                            logging.debug(f"[UPGRADE] Comparaison: '{self.normalize_name(card_file_name)}' vs '{self.normalize_name(full_name)}'")
                            if self.normalize_name(card_file_name) == self.normalize_name(full_name):
                                file_id = f['id']
                                logging.info(f"[UPGRADE] Carte Full trouvée dans {cat}: {card_file_name} (ID: {file_id})")
                                break

                    # Si pas trouvée dans la catégorie d'origine, chercher dans toutes les autres catégories
                    if not file_id:
                        logging.info(f"[UPGRADE] Carte {full_name} non trouvée dans {cat}, recherche dans toutes les catégories...")
                        for search_cat, full_cards in self.upgrade_cards_by_category.items():
                            if search_cat == cat:  # Déjà cherché
                                continue
                            for f in full_cards:
                                card_file_name = f['name'].removesuffix(".png")
                                if self.normalize_name(card_file_name) == self.normalize_name(full_name):
                                    file_id = f['id']
                                    logging.info(f"[UPGRADE] Carte Full trouvée dans {search_cat}: {card_file_name} (ID: {file_id})")
                                    break
                            if file_id:  # Trouvée, sortir de la boucle externe
                                break

                    # Si aucune carte Full n'existe, ne pas effectuer l'upgrade
                    if not file_id:
                        logging.warning(f"[UPGRADE] Carte Full {full_name} introuvable dans toutes les catégories. Upgrade ignoré pour éviter la perte de cartes.")
                        continue

                    # Maintenant que nous savons que la carte Full existe, retirer les cartes normales
                    removed = 0
                    for _ in range(seuil):
                        if self.remove_card_from_user(user_id, cat, name):
                            removed += 1
                        else:
                            logging.error(
                                f"[UPGRADE] Échec suppression {name} pour {user_id}. Rollback"
                            )
                            for _ in range(removed):
                                self.add_card_to_user(user_id, cat, name)
                            break
                    else:
                        # Toutes les cartes ont été retirées avec succès, procéder à l'ajout de la carte Full
                        file_bytes = self.download_drive_file(file_id)
                        if not file_bytes:
                            logging.error(f"[UPGRADE] Impossible de télécharger l'image pour {full_name}")
                            # Rollback: remettre les cartes retirées
                            for _ in range(removed):
                                self.add_card_to_user(user_id, cat, name)
                            continue

                        # Désactiver les infos d'inventaire pour les notifications d'upgrade
                        embed, image_file = self.build_card_embed(cat, full_name, file_bytes, show_inventory_info=False)
                        embed.title = f"🎉 Carte Full obtenue : {full_name}"
                        embed.description = (
                            f"<@{user_id}> a échangé **{seuil}× {name}** "
                            f"contre **{full_name}** !"
                        )
                        embed.color = discord.Color.gold()

                        # Envoyer la notification dans le salon spécifié ou via followup
                        if notification_channel_id:
                            try:
                                channel = self.bot.get_channel(notification_channel_id)
                                if channel:
                                    await channel.send(embed=embed, file=image_file)
                                    logging.info(f"[UPGRADE] Notification envoyée dans le salon {notification_channel_id} pour {full_name}")
                                else:
                                    logging.error(f"[UPGRADE] Salon {notification_channel_id} introuvable")
                                    # Fallback vers followup si le salon n'existe pas
                                    embed.description = (
                                        f"Vous avez échangé **{seuil}× {name}** "
                                        f"contre **{full_name}** !"
                                    )
                                    await interaction.followup.send(embed=embed, file=image_file)
                            except Exception as e:
                                logging.error(f"[UPGRADE] Erreur envoi notification salon {notification_channel_id}: {e}")
                                # Fallback vers followup en cas d'erreur
                                embed.description = (
                                    f"Vous avez échangé **{seuil}× {name}** "
                                    f"contre **{full_name}** !"
                                )
                                await interaction.followup.send(embed=embed, file=image_file)
                        else:
                            embed.description = (
                                f"Vous avez échangé **{seuil}× {name}** "
                                f"contre **{full_name}** !"
                            )
                            await interaction.followup.send(embed=embed, file=image_file)

                        # Ajouter la carte Full à l'inventaire
                        if not self.add_card_to_user(user_id, cat, full_name):
                            logging.error(
                                f"[UPGRADE] Échec ajout {full_name} pour {user_id}. Rollback"
                            )
                            for _ in range(seuil):
                                self.add_card_to_user(user_id, cat, name)
                        else:
                            # Mettre à jour le mur des cartes avec la nouvelle carte Full
                            await self._handle_announce_and_wall(interaction, [(cat, full_name)])
                            logging.info(f"[UPGRADE] Upgrade réussi: {seuil}× {name} -> {full_name} pour utilisateur {user_id}")

        except Exception as e:
            logging.error(f"[UPGRADE] Erreur lors de la vérification des upgrades: {e}")
    
    def _user_has_card(self, user_id: int, category: str, name: str) -> bool:
        """Vérifie si un utilisateur possède une carte spécifique."""
        user_cards = self.get_user_cards(user_id)
        return (category, name) in user_cards

    def get_user_card_count(self, user_id: int, category: str, name: str) -> int:
        """Retourne le nombre d'exemplaires d'une carte spécifique possédée par un utilisateur."""
        try:
            user_cards = self.get_user_cards(user_id)
            return user_cards.count((category, name))
        except Exception as e:
            logging.error(f"[EMBED] Erreur dans get_user_card_count: {e}")
            return 0

    def is_new_card_for_user(self, user_id: int, category: str, name: str) -> bool:
        """Vérifie si c'est une nouvelle carte pour l'utilisateur (première fois qu'il l'obtient)."""
        try:
            return not self._user_has_card(user_id, category, name)
        except Exception as e:
            logging.error(f"[EMBED] Erreur dans is_new_card_for_user: {e}")
            return False

    def user_has_full_version(self, user_id: int, category: str, name: str) -> bool:
        """Vérifie si l'utilisateur possède la version Full d'une carte."""
        try:
            # Construire le nom de la carte Full
            full_name = f"{name} (Full)"
            return self._user_has_card(user_id, category, full_name)
        except Exception as e:
            logging.error(f"[EMBED] Erreur dans user_has_full_version: {e}")
            return False

    def can_have_full_version(self, category: str, name: str) -> bool:
        """Vérifie si une carte peut avoir une version Full."""
        try:
            full_name = f"{name} (Full)"
            # Vérifier si la carte Full existe dans les fichiers
            for f in self.upgrade_cards_by_category.get(category, []):
                if normalize_name(f['name'].removesuffix(".png")) == normalize_name(full_name):
                    return True
            return False
        except Exception as e:
            logging.error(f"[EMBED] Erreur dans can_have_full_version: {e}")
            return False



    # ========== MÉTHODES DE CLASSEMENT ==========

    def get_unique_card_counts(self) -> dict[int, int]:
        """Retourne un dictionnaire {user_id: nombre de cartes différentes}."""
        cards_cache = self.storage.get_cards_cache()
        if not cards_cache:
            return {}

        rows = cards_cache[1:]
        user_sets: dict[int, set[tuple[str, str]]] = {}
        for row in rows:
            if len(row) < 3:
                continue
            cat, name = row[0], row[1]
            card_key = (cat, name)
            for cell in row[2:]:
                cell = cell.strip()
                if not cell or ":" not in cell:
                    continue
                uid_str, _ = cell.split(":", 1)
                try:
                    uid = int(uid_str)
                except ValueError:
                    continue
                user_sets.setdefault(uid, set()).add(card_key)

        return {uid: len(cards) for uid, cards in user_sets.items()}

    def get_unique_card_counts_excluding_full(self) -> dict[int, int]:
        """Retourne un dictionnaire {user_id: nombre de cartes différentes} en excluant les cartes Full."""
        cards_cache = self.storage.get_cards_cache()
        if not cards_cache:
            return {}

        rows = cards_cache[1:]
        user_sets: dict[int, set[tuple[str, str]]] = {}
        for row in rows:
            if len(row) < 3:
                continue
            cat, name = row[0], row[1]
            # Skip full cards
            if name.removesuffix('.png').endswith(' (Full)'):
                continue
            card_key = (cat, name)
            for cell in row[2:]:
                cell = cell.strip()
                if not cell or ":" not in cell:
                    continue
                uid_str, _ = cell.split(":", 1)
                try:
                    uid = int(uid_str)
                except ValueError:
                    continue
                user_sets.setdefault(uid, set()).add(card_key)

        return {uid: len(cards) for uid, cards in user_sets.items()}

    def get_leaderboard(self, top_n: int = 5) -> list[tuple[int, int]]:
        """Renvoie la liste triée des (user_id, compte unique) pour les `top_n` meilleurs."""
        counts = self.get_unique_card_counts()
        leaderboard = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return leaderboard[:top_n]

    def get_leaderboard_excluding_full(self, top_n: int = 5) -> list[tuple[int, int]]:
        """Renvoie la liste triée des (user_id, compte unique hors Full) pour les `top_n` meilleurs."""
        counts = self.get_unique_card_counts_excluding_full()
        leaderboard = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return leaderboard[:top_n]

    def get_user_rank(self, user_id: int) -> tuple[int | None, int]:
        """Renvoie (rang, nombre de cartes uniques) de l'utilisateur."""
        counts = self.get_unique_card_counts()
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        rank = None
        for idx, (uid, _) in enumerate(sorted_counts, start=1):
            if uid == user_id:
                rank = idx
                break
        return rank, counts.get(user_id, 0)

    def get_user_rank_excluding_full(self, user_id: int) -> tuple[int | None, int]:
        """Renvoie (rang, nombre de cartes uniques hors Full) de l'utilisateur."""
        counts = self.get_unique_card_counts_excluding_full()
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        rank = None
        for idx, (uid, _) in enumerate(sorted_counts, start=1):
            if uid == user_id:
                rank = idx
                break
        return rank, counts.get(user_id, 0)

    def total_unique_cards_available(self) -> int:
        """Nombre total de cartes différentes existantes."""
        total = 0
        for lst in (*self.cards_by_category.values(), *self.upgrade_cards_by_category.values()):
            total += len(lst)
        return total

    def total_unique_cards_available_excluding_full(self) -> int:
        """Nombre total de cartes différentes existantes (hors Full)."""
        total = 0
        for lst in self.cards_by_category.values():
            total += len(lst)
        return total

    # ========== MÉTHODES UTILITAIRES ==========

    def find_user_card_by_input(self, user_id: int, input_text: str) -> tuple[str, str] | None:
        """Recherche une carte dans l'inventaire d'un utilisateur par nom ou ID."""
        input_text = input_text.strip()
        logging.debug(f"[CARD_SEARCH] Recherche pour utilisateur {user_id}: '{input_text}'")

        # Vérifier si c'est un identifiant (C1, C2, etc.)
        if input_text.upper().startswith('C') and input_text[1:].isdigit():
            # Recherche par identifiant
            discovery_index = int(input_text[1:])
            logging.debug(f"[CARD_SEARCH] Recherche par identifiant: C{discovery_index}")

            try:
                discoveries_cache = self.discovery_manager.storage.get_discoveries_cache()
                if not discoveries_cache:
                    logging.warning("[CARD_SEARCH] Cache des découvertes non disponible")
                    return None

                for row in discoveries_cache[1:]:  # Skip header
                    if len(row) >= 6:
                        try:
                            if int(row[5]) == discovery_index:
                                category, name = row[0], row[1]
                                logging.debug(f"[CARD_SEARCH] Carte trouvée par ID: {category}/{name}")

                                # Vérifier que l'utilisateur possède cette carte
                                owned_cards = self.get_user_cards(user_id)
                                if any(cat == category and n == name for cat, n in owned_cards):
                                    logging.debug(f"[CARD_SEARCH] Utilisateur possède la carte")
                                    return (category, name)
                                else:
                                    logging.debug(f"[CARD_SEARCH] Utilisateur ne possède pas la carte")
                                    return None
                        except (ValueError, IndexError) as e:
                            logging.warning(f"[CARD_SEARCH] Erreur dans les données de découverte: {e}")
                            continue

                logging.debug(f"[CARD_SEARCH] Aucune carte trouvée avec l'ID C{discovery_index}")
                return None

            except Exception as e:
                logging.error(f"[CARD_SEARCH] Erreur lors de la recherche par ID: {e}")
                return None

        # Recherche par nom
        logging.debug(f"[CARD_SEARCH] Recherche par nom: '{input_text}'")

        # Normaliser l'input pour la recherche
        search_input = input_text
        if not search_input.lower().endswith(".png"):
            search_input += ".png"

        normalized_input = normalize_name(search_input.removesuffix(".png"))
        owned_cards = self.get_user_cards(user_id)

        logging.debug(f"[CARD_SEARCH] Input normalisé: '{normalized_input}', cartes possédées: {len(owned_cards)}")

        for cat, name in owned_cards:
            normalized_card_name = normalize_name(name.removesuffix(".png"))
            if normalized_card_name == normalized_input:
                logging.debug(f"[CARD_SEARCH] Carte trouvée par nom: {cat}/{name}")
                return (cat, name)

        logging.debug(f"[CARD_SEARCH] Aucune carte trouvée par nom")
        return None

    def get_user_card_suggestions(self, user_id: int, input_text: str, max_suggestions: int = 5) -> list[str]:
        """Retourne des suggestions de cartes similaires pour aider l'utilisateur."""
        try:
            input_text = input_text.strip()
            normalized_input = normalize_name(input_text.removesuffix(".png"))
            owned_cards = self.get_user_cards(user_id)

            suggestions = []
            for cat, name in owned_cards:
                normalized_card_name = normalize_name(name.removesuffix(".png"))
                # Recherche de correspondances partielles
                if normalized_input in normalized_card_name or normalized_card_name in normalized_input:
                    display_name = name.removesuffix(".png")
                    card_id = self.get_card_identifier(cat, name)
                    if card_id:
                        suggestions.append(f"{display_name} ({card_id})")
                    else:
                        suggestions.append(display_name)

                    if len(suggestions) >= max_suggestions:
                        break

            return suggestions
        except Exception as e:
            logging.error(f"[CARD_SEARCH] Erreur lors de la génération de suggestions: {e}")
            return []



    def find_card_by_name(self, input_name: str) -> tuple[str, str, str] | None:
        """
        Recherche une carte par nom dans toutes les catégories.
        Retourne (catégorie, nom exact avec extension, file_id) ou None.
        """
        logging.debug(f"[FIND_CARD] Recherche du fichier pour: '{input_name}'")
        normalized_input = normalize_name(input_name.removesuffix(".png"))
        logging.debug(f"[FIND_CARD] Input normalisé: '{normalized_input}'")

        # Chercher dans les cartes normales et Full
        all_files = {}
        for cat, files in self.cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)
        for cat, files in self.upgrade_cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)

        logging.debug(f"[FIND_CARD] Catégories disponibles: {list(all_files.keys())}")
        total_files = sum(len(files) for files in all_files.values())
        logging.debug(f"[FIND_CARD] Total de fichiers à rechercher: {total_files}")

        for category, files in all_files.items():
            for file_info in files:
                file_name = file_info['name']
                normalized_file = normalize_name(file_name.removesuffix(".png"))
                if normalized_file == normalized_input:
                    logging.debug(f"[FIND_CARD] Fichier trouvé: {category}/{file_name} (ID: {file_info['id']})")
                    # Retourner le nom avec extension pour correspondre au format de l'inventaire
                    return category, file_name, file_info['id']

        logging.debug(f"[FIND_CARD] Aucun fichier trouvé pour '{input_name}'")
        return None



    def get_card_id(self, category: str, name: str) -> str | None:
        """Récupère l'ID d'une carte (sera implémenté avec le système d'ID)."""
        # Placeholder pour le système d'ID de cartes
        return None

    def get_card_identifier(self, category: str, name: str) -> str | None:
        """Récupère l'identifiant de carte (ex: 'C1', 'C150') basé sur l'index de découverte."""
        discovery_info = self.discovery_manager.get_discovery_info(category, name)
        if discovery_info and discovery_info['discovery_index'] > 0:
            return f"C{discovery_info['discovery_index']}"
        return None

    def generate_complete_gallery_embeds(self, user: discord.abc.User) -> list[discord.Embed] | None:
        """Génère une galerie complète avec tous les embeds nécessaires (format lisible)."""
        try:
            user_cards = self.get_user_cards(user.id)
            if not user_cards:
                return None

            # Configuration pour affichage complet
            MAX_EMBEDS = 10  # Limite Discord
            MAX_FIELDS_PER_EMBED = 25  # Limite Discord
            MAX_CHARS_PER_FIELD = 1000  # Limite Discord (1024 avec marge)

            cards_by_cat: dict[str, list[str]] = {}
            for cat, name in user_cards:
                cards_by_cat.setdefault(cat, []).append(name)

            # Préparer les catégories triées par taille décroissante
            categories_data = []
            for cat, noms in cards_by_cat.items():
                normales = [n for n in noms if not n.endswith(" (Full)")]
                fulls = [n for n in noms if n.endswith(" (Full)")]

                normal_counts = {}
                for n in normales:
                    normal_counts[n] = normal_counts.get(n, 0) + 1

                full_counts = {}
                for n in fulls:
                    full_counts[n] = full_counts.get(n, 0) + 1

                sorted_normal_cards = sorted(normal_counts.items(), key=lambda x: normalize_name(x[0].removesuffix('.png')))
                sorted_full_cards = sorted(full_counts.items(), key=lambda x: normalize_name(x[0].removesuffix('.png')))

                total_unique_cards = len(normal_counts) + len(full_counts)

                categories_data.append({
                    'name': cat,
                    'normal_cards': sorted_normal_cards,
                    'full_cards': sorted_full_cards,
                    'total_unique_cards': total_unique_cards
                })

            # Trier par ordre de rareté (comme avant)
            rarity_order = {
                "Secrète": 0,
                "Fondateur": 1,
                "Historique": 2,
                "Maître": 3,
                "Black Hole": 4,
                "Architectes": 5,
                "Professeurs": 6,
                "Autre": 7,
                "Élèves": 8,
            }
            categories_data.sort(key=lambda x: rarity_order.get(x['name'], 9))

            # Créer les embeds avec le format original lisible
            embeds = []
            current_embed_normal = discord.Embed(
                title=f"🎴 Collection complète de {user.display_name}",
                color=discord.Color.blue()
            )
            current_embed_full = discord.Embed(
                title=f"✨ Cartes Full de {user.display_name}",
                color=discord.Color.gold()
            )

            current_fields_normal = 0
            current_fields_full = 0
            embed_count = 1

            for cat_data in categories_data:
                cat = cat_data['name']

                # Traiter les cartes normales avec le format original
                if cat_data['normal_cards']:
                    lines = []
                    for n, c in cat_data['normal_cards']:
                        try:
                            card_name = n.removesuffix('.png')
                            identifier = self.get_card_identifier(cat, n)
                            identifier_text = f" ({identifier})" if identifier else ""
                            count_text = f' (x{c})' if c > 1 else ''
                            lines.append(f"- **{card_name}**{identifier_text}{count_text}")
                        except Exception as e:
                            logging.error(f"[GALLERY] Erreur lors du traitement de la carte {n}: {e}")
                            continue

                    if lines:
                        field_value = "\n".join(lines)

                        # Vérifier si le field rentre dans la limite de caractères
                        if len(field_value) > MAX_CHARS_PER_FIELD:
                            # Diviser en plusieurs fields si nécessaire
                            chunks = []
                            current_chunk = []
                            current_length = 0

                            for line in lines:
                                if current_length + len(line) + 1 > MAX_CHARS_PER_FIELD:
                                    if current_chunk:
                                        chunks.append("\n".join(current_chunk))
                                    current_chunk = [line]
                                    current_length = len(line)
                                else:
                                    current_chunk.append(line)
                                    current_length += len(line) + 1

                            if current_chunk:
                                chunks.append("\n".join(current_chunk))

                            # Ajouter chaque chunk comme un field séparé
                            for i, chunk in enumerate(chunks):
                                try:
                                    total_available = len({
                                        f['name'].removesuffix('.png')
                                        for f in self.cards_by_category.get(cat, [])
                                    })
                                    owned_unique = len(cat_data['normal_cards'])

                                    field_name = f"{cat} : {owned_unique}/{total_available}" if i == 0 else f"{cat} (suite {i+1})"

                                    # Vérifier si on a de la place dans l'embed actuel
                                    if current_fields_normal >= MAX_FIELDS_PER_EMBED:
                                        embeds.append(current_embed_normal)
                                        embed_count += 1
                                        current_embed_normal = discord.Embed(
                                            title=f"🎴 Collection de {user.display_name} (partie {embed_count})",
                                            color=discord.Color.blue()
                                        )
                                        current_fields_normal = 0

                                    current_embed_normal.add_field(
                                        name=field_name,
                                        value=chunk,
                                        inline=False
                                    )
                                    current_fields_normal += 1

                                except Exception as e:
                                    logging.error(f"[GALLERY] Erreur lors de l'ajout du champ pour {cat}: {e}")
                                    continue
                        else:
                            # Le field rentre dans la limite
                            try:
                                total_available = len({
                                    f['name'].removesuffix('.png')
                                    for f in self.cards_by_category.get(cat, [])
                                })
                                owned_unique = len(cat_data['normal_cards'])

                                # Vérifier si on a de la place dans l'embed actuel
                                if current_fields_normal >= MAX_FIELDS_PER_EMBED:
                                    embeds.append(current_embed_normal)
                                    embed_count += 1
                                    current_embed_normal = discord.Embed(
                                        title=f"🎴 Collection de {user.display_name} (partie {embed_count})",
                                        color=discord.Color.blue()
                                    )
                                    current_fields_normal = 0

                                current_embed_normal.add_field(
                                    name=f"{cat} : {owned_unique}/{total_available}",
                                    value=field_value,
                                    inline=False
                                )
                                current_fields_normal += 1

                            except Exception as e:
                                logging.error(f"[GALLERY] Erreur lors de l'ajout du champ pour {cat}: {e}")
                                continue

                # Traiter les cartes Full avec le format original
                if cat_data['full_cards']:
                    lines = []
                    for n, c in cat_data['full_cards']:
                        try:
                            card_name = n.removesuffix('.png')
                            count_text = f' (x{c})' if c > 1 else ''
                            lines.append(f"- **{card_name}**{count_text}")
                        except Exception as e:
                            logging.error(f"[GALLERY] Erreur lors du traitement de la carte Full {n}: {e}")
                            continue

                    if lines:
                        field_value = "\n".join(lines)

                        # Vérifier si le field rentre dans la limite de caractères
                        if len(field_value) > MAX_CHARS_PER_FIELD:
                            # Diviser en plusieurs fields si nécessaire
                            chunks = []
                            current_chunk = []
                            current_length = 0

                            for line in lines:
                                if current_length + len(line) + 1 > MAX_CHARS_PER_FIELD:
                                    if current_chunk:
                                        chunks.append("\n".join(current_chunk))
                                    current_chunk = [line]
                                    current_length = len(line)
                                else:
                                    current_chunk.append(line)
                                    current_length += len(line) + 1

                            if current_chunk:
                                chunks.append("\n".join(current_chunk))

                            # Ajouter chaque chunk comme un field séparé
                            for i, chunk in enumerate(chunks):
                                try:
                                    total_full = len({
                                        f['name'].removesuffix('.png')
                                        for f in self.upgrade_cards_by_category.get(cat, [])
                                    })
                                    owned_full = len(cat_data['full_cards'])

                                    field_name = f"{cat} (Full) : {owned_full}/{total_full}" if i == 0 else f"{cat} (Full) (suite {i+1})"

                                    # Vérifier si on a de la place dans l'embed actuel
                                    if current_fields_full >= MAX_FIELDS_PER_EMBED:
                                        if current_fields_full > 0:  # Seulement si l'embed a du contenu
                                            embeds.append(current_embed_full)
                                        embed_count += 1
                                        current_embed_full = discord.Embed(
                                            title=f"✨ Cartes Full de {user.display_name} (partie {embed_count})",
                                            color=discord.Color.gold()
                                        )
                                        current_fields_full = 0

                                    current_embed_full.add_field(
                                        name=field_name,
                                        value=chunk,
                                        inline=False
                                    )
                                    current_fields_full += 1

                                except Exception as e:
                                    logging.error(f"[GALLERY] Erreur lors de l'ajout du champ Full pour {cat}: {e}")
                                    continue
                        else:
                            # Le field rentre dans la limite
                            try:
                                total_full = len({
                                    f['name'].removesuffix('.png')
                                    for f in self.upgrade_cards_by_category.get(cat, [])
                                })
                                owned_full = len(cat_data['full_cards'])

                                # Vérifier si on a de la place dans l'embed actuel
                                if current_fields_full >= MAX_FIELDS_PER_EMBED:
                                    if current_fields_full > 0:  # Seulement si l'embed a du contenu
                                        embeds.append(current_embed_full)
                                    embed_count += 1
                                    current_embed_full = discord.Embed(
                                        title=f"✨ Cartes Full de {user.display_name} (partie {embed_count})",
                                        color=discord.Color.gold()
                                    )
                                    current_fields_full = 0

                                current_embed_full.add_field(
                                    name=f"{cat} (Full) : {owned_full}/{total_full}",
                                    value=field_value,
                                    inline=False
                                )
                                current_fields_full += 1

                            except Exception as e:
                                logging.error(f"[GALLERY] Erreur lors de l'ajout du champ Full pour {cat}: {e}")
                                continue

            # Finaliser les embeds
            if current_fields_normal > 0:
                embeds.append(current_embed_normal)
            if current_fields_full > 0:
                embeds.append(current_embed_full)

            return embeds if embeds else None

        except Exception as e:
            logging.error(f"[GALLERY] Erreur dans generate_complete_gallery_embeds: {e}")
            return None

    def generate_gallery_embeds(self, user: discord.abc.User) -> list[discord.Embed] | None:
        """Génère la galerie complète pour l'utilisateur donné (remplace la pagination)."""
        # Utiliser directement la méthode de galerie complète
        return self.generate_complete_gallery_embeds(user)

    def get_all_card_categories(self) -> list[str]:
        """Retourne la liste complète des catégories de cartes."""
        return self.forum_manager.get_all_card_categories()

    def compute_total_medals(self, user_id: int, students: dict, user_character_names: set) -> int:
        """Calcule le total de médailles d'un utilisateur (placeholder)."""
        # Cette méthode sera connectée avec le système d'inventaire
        return 0

    async def ensure_card_collector_role(self, interaction: discord.Interaction):
        """Assigne automatiquement le rôle de collectionneur de cartes."""
        if not interaction.guild:
            return

        try:
            role = interaction.guild.get_role(CARD_COLLECTOR_ROLE_ID)
            if role and role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                logging.info(f"[ROLE] Rôle collectionneur assigné à {interaction.user.display_name}")
        except Exception as e:
            logging.error(f"[ROLE] Erreur lors de l'assignation du rôle: {e}")

    async def update_character_ownership(self, user: discord.User):
        """Met à jour la propriété des personnages (placeholder)."""
        # Cette méthode sera connectée avec le système d'inventaire
        pass

    async def update_all_character_owners(self):
        """Met à jour tous les propriétaires de personnages (placeholder)."""
        # Cette méthode sera connectée avec le système d'inventaire
        pass

    async def _handle_announce_and_wall(self, interaction: discord.Interaction, drawn_cards: list[tuple[str, str]]):
        """Gère les annonces publiques et le mur des cartes."""
        try:
            discovered_cards = self.discovery_manager.get_discovered_cards()
            new_cards = [card for card in drawn_cards if card not in discovered_cards]

            if not new_cards:
                return

            # Poster les nouvelles cartes dans le forum
            all_files = {}
            for cat, files in self.cards_by_category.items():
                all_files.setdefault(cat, []).extend(files)
            for cat, files in self.upgrade_cards_by_category.items():
                all_files.setdefault(cat, []).extend(files)

            for cat, name in new_cards:
                file_id = next(
                    (f['id'] for f in all_files.get(cat, [])
                     if f['name'].removesuffix(".png") == name),
                    None
                )
                if not file_id:
                    continue

                # Enregistrer la découverte
                discovery_index = self.discovery_manager.log_discovery(
                    cat, name, interaction.user.id, interaction.user.display_name
                )

                # Télécharger l'image
                file_bytes = self.download_drive_file(file_id)
                if file_bytes:
                    # Poster dans le forum
                    await self.forum_manager.post_card_to_forum(
                        cat, name, file_bytes,
                        interaction.user.display_name, discovery_index
                    )

        except Exception as e:
            logging.error(f"[ANNOUNCE] Erreur lors de l'annonce: {e}")

    # ========== COMMANDES DISCORD ==========

    @app_commands.command(name="cartes", description="Gérer vos cartes à collectionner")
    async def cartes(self, interaction: discord.Interaction):
        """Commande principale du système de cartes optimisée."""
        logging.info("[DEBUG] Commande /cartes déclenchée")

        await interaction.response.defer(ephemeral=True)

        # Assigner automatiquement le rôle de collectionneur de cartes
        await self.ensure_card_collector_role(interaction)

        await self.update_character_ownership(interaction.user)

        view = CardsMenuView(self, interaction.user)

        # Calcul optimisé des statistiques de l'utilisateur
        user_cards = self.get_user_cards(interaction.user.id)
        drawn_count = len(user_cards)

        # Statistiques de cartes uniques (optimisé avec une seule itération)
        unique_cards = set(user_cards)
        unique_count = len(unique_cards)
        unique_count_excluding_full = len(set([(cat, name) for cat, name in unique_cards if not "(Full)" in name]))

        # Totaux disponibles (mise en cache)
        total_unique = self.total_unique_cards_available()
        total_unique_excluding_full = self.total_unique_cards_available_excluding_full()

        # Classements (optimisé avec cache)
        rank, _ = self.get_user_rank(interaction.user.id)
        rank_excluding_full, _ = self.get_user_rank_excluding_full(interaction.user.id)

        rank_text = f"#{rank}" if rank else "Non classé"
        rank_text_excluding_full = f"#{rank_excluding_full}" if rank_excluding_full else "Non classé"

        # Vérifier les tirages disponibles (optimisé avec cache)
        can_draw_today = self.drawing_manager.can_perform_daily_draw(interaction.user.id)
        can_sacrificial_today = self.drawing_manager.can_perform_sacrificial_draw(interaction.user.id)

        tirage_status = "✅ Disponible" if can_draw_today else "❌ Déjà effectué"
        sacrificial_status = "✅ Disponible" if can_sacrificial_today else "❌ Déjà effectué"

        # Créer l'embed principal optimisé
        embed = discord.Embed(
            title="🎴 Menu des Cartes",
            description=(
                f"**Bienvenue {interaction.user.display_name} !**\n\n"
                f"🌅 **Tirage journalier :** {tirage_status}\n"
                f"⚔️ **Tirage sacrificiel :** {sacrificial_status}\n"
                f"📈 **Cartes différentes :** {unique_count}/{total_unique} | Hors Full : {unique_count_excluding_full}/{total_unique_excluding_full}\n"
                f"🥇 **Classement :** {rank_text} | Hors Full : {rank_text_excluding_full}\n"
                f"🎴 **Total possédé :** {drawn_count} cartes"
            ),
            color=0x3498db
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# Commande /tirage_journalier supprimée - intégrée dans le bouton "Tirer une carte" du menu /cartes

# Commande /tirage_sacrificiel supprimée - intégrée dans le bouton du menu /cartes

    @app_commands.command(name="carte_info", description="Obtenir des informations sur une carte par nom ou identifiant")
    async def carte_info(self, interaction: discord.Interaction, carte: str):
        """Affiche les informations d'une carte par nom ou identifiant."""
        await interaction.response.defer(ephemeral=True)

        # Assigner automatiquement le rôle de collectionneur de cartes
        await self.ensure_card_collector_role(interaction)

        carte = carte.strip()

        try:
            # Vérifier si c'est un identifiant (C1, C2, etc.)
            if carte.upper().startswith('C') and carte[1:].isdigit():
                # Recherche par identifiant
                discovery_index = int(carte[1:])
                discoveries_cache = self.discovery_manager.storage.get_discoveries_cache()

                if discoveries_cache:
                    for row in discoveries_cache[1:]:  # Skip header
                        if len(row) >= 6 and int(row[5]) == discovery_index:
                            category, name = row[0], row[1]
                            break
                    else:
                        await interaction.followup.send(
                            f"❌ Aucune carte trouvée avec l'identifiant '{carte.upper()}'.",
                            ephemeral=True
                        )
                        return
                else:
                    await interaction.followup.send(
                        "❌ Système de découvertes non disponible.",
                        ephemeral=True
                    )
                    return
            else:
                # Recherche par nom
                card_info = self.find_card_by_name(carte)
                if not card_info:
                    await interaction.followup.send(
                        f"❌ Aucune carte trouvée avec le nom '{carte}'.",
                        ephemeral=True
                    )
                    return
                category, name, file_id = card_info

            # Récupérer les informations de découverte
            discovery_info = self.discovery_manager.get_discovery_info(category, name)

            # Créer l'embed d'information
            embed = discord.Embed(
                title=f"🎴 {name.removesuffix('.png')}",
                color=0x3498db
            )

            embed.add_field(name="📂 Catégorie", value=category, inline=True)

            if discovery_info:
                embed.add_field(
                    name="🔍 Identifiant",
                    value=f"C{discovery_info['discovery_index']}",
                    inline=True
                )
                embed.add_field(
                    name="👤 Découvreur",
                    value=discovery_info['discoverer_name'],
                    inline=True
                )
                embed.add_field(
                    name="📅 Date de découverte",
                    value=discovery_info['timestamp'],
                    inline=False
                )
            else:
                embed.add_field(name="🔍 Statut", value="Non découverte", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"[CARTE_INFO] Erreur: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la recherche.",
                ephemeral=True
            )

# Commande /decouvertes_recentes supprimée selon demande utilisateur

    def get_user_unclaimed_bonus_count(self, user_id: int) -> int:
        """
        Vérifie et retourne le nombre total de tirages bonus non réclamés pour un utilisateur.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            int: Nombre total de tirages bonus disponibles
        """
        user_id_str = str(user_id)

        try:
            # Lecture des bonus
            all_rows = self.storage.sheet_bonus.get_all_values()[1:]  # skip header

            user_bonus = 0

            for row in all_rows:
                if len(row) >= 3 and row[0] == user_id_str:
                    try:
                        count = int(row[1])
                        user_bonus += count
                    except ValueError:
                        continue

            return user_bonus

        except Exception as e:
            logging.error(f"[BONUS] Erreur lors de la vérification des bonus: {e}")
            return 0

    @app_commands.command(name="analyse_cartes", description="Analyse les statistiques réelles de drop de chaque carte")
    async def analyse_cartes(self, interaction: discord.Interaction):
        """Commande d'analyse des statistiques de drop des cartes."""
        await interaction.response.defer()

        try:
            # Calculer les statistiques pour chaque catégorie
            analysis_data = []

            for category in ALL_CATEGORIES:
                # Nombre de cartes dans cette catégorie
                normal_cards = self.cards_by_category.get(category, [])
                full_cards = self.upgrade_cards_by_category.get(category, [])

                normal_count = len(normal_cards)
                full_count = len(full_cards)
                total_cards_in_category = normal_count + full_count

                if total_cards_in_category == 0:
                    continue

                # Probabilité de base de la catégorie
                category_probability = RARITY_WEIGHTS.get(category, 0)

                # Probabilité réelle par carte normale
                if normal_count > 0:
                    normal_card_probability = (category_probability / total_cards_in_category) * (1 - self.drawing_manager._calculate_variant_chance(category))
                else:
                    normal_card_probability = 0

                # Probabilité réelle par carte Full (si tirée directement)
                if full_count > 0:
                    full_card_probability = (category_probability / total_cards_in_category) * self.drawing_manager._calculate_variant_chance(category)
                else:
                    full_card_probability = 0

                analysis_data.append({
                    'category': category,
                    'normal_count': normal_count,
                    'full_count': full_count,
                    'total_count': total_cards_in_category,
                    'category_probability': category_probability * 100,  # En pourcentage
                    'normal_card_probability': normal_card_probability * 100,  # En pourcentage
                    'full_card_probability': full_card_probability * 100,  # En pourcentage
                    'variant_chance': self.drawing_manager._calculate_variant_chance(category) * 100  # En pourcentage
                })

            # Créer l'embed avec les résultats
            embed = discord.Embed(
                title="📊 Analyse des statistiques de drop",
                description="Probabilités réelles de drop par carte individuelle",
                color=0x3498db
            )

            for data in analysis_data:
                field_value = (
                    f"**Cartes normales :** {data['normal_count']}\n"
                    f"**Cartes Full :** {data['full_count']}\n"
                    f"**Total catégorie :** {data['total_count']}\n"
                    f"**Prob. catégorie :** {data['category_probability']:.3f}%\n"
                    f"**Prob. par carte normale :** {data['normal_card_probability']:.4f}%\n"
                    f"**Prob. par carte Full :** {data['full_card_probability']:.4f}%\n"
                    f"**Chance variante Full :** {data['variant_chance']:.1f}%"
                )

                embed.add_field(
                    name=f"🎴 {data['category']}",
                    value=field_value,
                    inline=True
                )

            # Ajouter un résumé
            total_normal_cards = sum(data['normal_count'] for data in analysis_data)
            total_full_cards = sum(data['full_count'] for data in analysis_data)
            total_all_cards = total_normal_cards + total_full_cards

            embed.add_field(
                name="📈 Résumé global",
                value=(
                    f"**Total cartes normales :** {total_normal_cards}\n"
                    f"**Total cartes Full :** {total_full_cards}\n"
                    f"**Total général :** {total_all_cards}"
                ),
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"[ANALYSE] Erreur lors de l'analyse des cartes: {e}")
            await interaction.followup.send("❌ Erreur lors de l'analyse des statistiques.", ephemeral=True)

    async def claim_user_bonuses(self, interaction: discord.Interaction) -> bool:
        """
        Réclame tous les bonus disponibles pour un utilisateur.

        Args:
            interaction: L'interaction Discord

        Returns:
            bool: True si des bonus ont été réclamés avec succès
        """
        user_id_str = str(interaction.user.id)

        try:
            # Lecture des bonus
            all_rows = self.storage.sheet_bonus.get_all_values()[1:]  # skip header

            user_bonus = 0
            bonus_sources = []

            for row in all_rows:
                if len(row) >= 3 and row[0] == user_id_str:
                    try:
                        count = int(row[1])
                        source = row[2] if len(row) > 2 else "Non spécifié"
                        user_bonus += count
                        bonus_sources.append(f"• {count} tirage(s) - {source}")
                    except ValueError:
                        continue

            if user_bonus <= 0:
                return False

            # Effectuer les tirages bonus
            drawn_cards = self.drawing_manager.draw_cards(user_bonus)

            # Logger l'utilisation des bonus
            if self.storage.logging_manager:
                self.storage.logging_manager.log_bonus_used(
                    user_id=interaction.user.id,
                    user_name=interaction.user.display_name,
                    count=user_bonus,
                    cards=drawn_cards,
                    source="reclamation_bonus"
                )

            # Ajouter les cartes à l'inventaire
            for cat, name in drawn_cards:
                self.add_card_to_user(interaction.user.id, cat, name,
                                    user_name=interaction.user.display_name,
                                    source="tirage_bonus")

            # Supprimer les bonus réclamés
            # Récupérer toutes les lignes et filtrer
            all_data = self.storage.sheet_bonus.get_all_values()
            header = all_data[0] if all_data else ["user_id", "count", "source"]
            filtered_data = [header]

            for i, row in enumerate(all_data[1:], start=1):
                if len(row) >= 1 and row[0] != user_id_str:
                    filtered_data.append(row)

            # Réécrire la feuille
            self.storage.sheet_bonus.clear()
            if filtered_data:
                self.storage.sheet_bonus.update('A1', filtered_data)

            # Créer l'embed de résultat
            embed = discord.Embed(
                title="🎁 Tirages bonus réclamés !",
                description=f"Vous avez réclamé **{user_bonus}** tirage(s) bonus !",
                color=0xffd700
            )

            # Afficher les sources des bonus
            if bonus_sources:
                embed.add_field(
                    name="📋 Sources des bonus",
                    value="\n".join(bonus_sources),
                    inline=False
                )

            # Afficher les cartes tirées
            if drawn_cards:
                cards_text = []
                for i, (cat, name) in enumerate(drawn_cards, 1):
                    display_name = name.removesuffix('.png')
                    cards_text.append(f"{i}. **{display_name}** ({cat})")

                embed.add_field(
                    name="🎴 Cartes obtenues",
                    value="\n".join(cards_text),
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Annonce publique si nouvelles cartes
            await self._handle_announce_and_wall(interaction, drawn_cards)

            return True

        except Exception as e:
            logging.error(f"[BONUS] Erreur lors de la réclamation des bonus: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la réclamation des bonus.",
                ephemeral=True
            )
            return False

    @commands.command(name="initialiser_forum_cartes", help="Initialise la structure forum pour les cartes")
    @commands.has_permissions(administrator=True)
    async def initialiser_forum_cartes(self, ctx: commands.Context):
        """Commande pour initialiser la structure forum des cartes."""
        await ctx.send("🔧 Initialisation de la structure forum des cartes en cours...")

        try:
            created_threads, existing_threads = await self.forum_manager.initialize_forum_structure()

            if created_threads:
                await ctx.send(f"✅ Threads créés: {', '.join(created_threads)}")
            if existing_threads:
                await ctx.send(f"ℹ️ Threads existants: {', '.join(existing_threads)}")

            await ctx.send("🎉 Initialisation du forum des cartes terminée avec succès!")

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de l'initialisation: {e}")
            logging.error(f"[FORUM_INIT] Erreur: {e}")

    @commands.command(name="galerie", help="Affiche la galerie de cartes d'un utilisateur")
    @commands.has_permissions(administrator=True)
    async def galerie_admin(self, ctx: commands.Context, member: discord.Member = None):
        """Commande admin pour afficher la galerie d'un utilisateur."""
        if member is None:
            member = ctx.author

        try:
            # Utiliser la méthode de galerie complète
            gallery_embeds = self.generate_gallery_embeds(member)

            if not gallery_embeds:
                await ctx.send(f"❌ {member.display_name} n'a aucune carte dans sa collection.")
                return

            # Créer la vue de galerie admin
            from .cards.views.gallery_views import AdminGalleryView
            gallery_view = AdminGalleryView(self, member)
            await ctx.send(embeds=gallery_embeds, view=gallery_view)

        except Exception as e:
            logging.error(f"[ADMIN_GALLERY] Erreur: {e}")
            await ctx.send("❌ Une erreur est survenue lors de l'affichage de la galerie.")

    @commands.command(name="give_bonus")
    @commands.has_permissions(administrator=True)
    async def give_bonus(self, ctx: commands.Context, member: discord.Member, count: int = 1, *, source: str):
        """
        Donne un nombre de bonus de tirage à un joueur.
        Usage : !give_bonus @joueur [nombre] raison du bonus
        """
        try:
            # Ajouter le bonus à la feuille
            self.storage.sheet_bonus.append_row([str(member.id), str(count), source])

            # Logger l'attribution du bonus
            if self.storage.logging_manager:
                self.storage.logging_manager.log_bonus_granted(
                    user_id=member.id,
                    user_name=member.display_name,
                    count=count,
                    source=source,
                    granted_by=ctx.author.display_name
                )

            embed = discord.Embed(
                title="🎁 Bonus accordé",
                description=f"**{count}** tirage(s) bonus accordé(s) à {member.mention}",
                color=0x00ff00
            )
            embed.add_field(name="Raison", value=source, inline=False)

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de l'attribution du bonus: {e}")

    @commands.command(name="clear_sacrificial_cache")
    @commands.has_permissions(administrator=True)
    async def clear_sacrificial_cache(self, ctx: commands.Context, member: discord.Member = None):
        """
        Nettoie le cache du tirage sacrificiel.
        Usage : !clear_sacrificial_cache [@joueur]
        """
        try:
            if member:
                self.drawing_manager.clear_sacrificial_cache(member.id)
                await ctx.send(f"✅ Cache sacrificiel nettoyé pour {member.mention}")
            else:
                self.drawing_manager.clear_sacrificial_cache()
                await ctx.send("✅ Cache sacrificiel entièrement nettoyé")

        except Exception as e:
            logging.error(f"[GIVE_BONUS] Erreur: {e}")
            await ctx.send(f"❌ Erreur lors de l'attribution du bonus: {e}")

    @commands.command(name="logs_cartes")
    @commands.has_permissions(administrator=True)
    async def view_cards_logs(self, ctx: commands.Context, user_id: int = None, limit: int = 50):
        """
        Affiche les logs de surveillance des cartes.
        Usage : !logs_cartes [user_id] [limit]
        """
        try:
            if not self.storage.logging_manager:
                await ctx.send("❌ Le système de logging n'est pas initialisé.")
                return

            # Récupérer les logs depuis Google Sheets
            all_logs = self.storage.sheet_logs.get_all_values()

            if len(all_logs) <= 1:  # Seulement l'en-tête
                await ctx.send("📋 Aucun log trouvé.")
                return

            # Filtrer par utilisateur si spécifié
            logs_data = all_logs[1:]  # Exclure l'en-tête
            if user_id:
                logs_data = [log for log in logs_data if len(log) >= 3 and log[2] == str(user_id)]

            # Limiter le nombre de résultats
            logs_data = logs_data[-limit:]  # Prendre les plus récents

            if not logs_data:
                await ctx.send(f"📋 Aucun log trouvé{f' pour l\'utilisateur {user_id}' if user_id else ''}.")
                return

            # Créer l'embed
            embed = discord.Embed(
                title="📋 Logs de surveillance des cartes",
                description=f"Affichage des {len(logs_data)} logs les plus récents{f' pour l\'utilisateur {user_id}' if user_id else ''}",
                color=0x3498db
            )

            # Ajouter les logs à l'embed (maximum 25 champs)
            for i, log in enumerate(logs_data[-25:]):
                if len(log) >= 6:
                    timestamp = log[0][:19] if log[0] else "N/A"  # Tronquer le timestamp
                    action = log[1] or "N/A"
                    user_name = log[3] or f"User_{log[2]}" if len(log) > 2 else "N/A"
                    card_info = f"{log[5]} ({log[4]})" if len(log) > 5 and log[4] and log[5] else "N/A"
                    quantity = log[6] if len(log) > 6 and log[6] else "N/A"
                    details = log[7] if len(log) > 7 and log[7] else "N/A"

                    embed.add_field(
                        name=f"#{len(logs_data) - len(logs_data[-25:]) + i + 1} - {timestamp}",
                        value=f"**Action:** {action}\n**Utilisateur:** {user_name}\n**Carte:** {card_info}\n**Quantité:** {quantity}\n**Détails:** {details}",
                        inline=False
                    )

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"[LOGS] Erreur lors de l'affichage des logs: {e}")
            await ctx.send(f"❌ Erreur lors de l'affichage des logs: {e}")

    @commands.command(name="stats_logs")
    @commands.has_permissions(administrator=True)
    async def view_logs_stats(self, ctx: commands.Context):
        """
        Affiche les statistiques des logs de surveillance.
        Usage : !stats_logs
        """
        try:
            if not self.storage.logging_manager:
                await ctx.send("❌ Le système de logging n'est pas initialisé.")
                return

            # Récupérer les logs depuis Google Sheets
            all_logs = self.storage.sheet_logs.get_all_values()

            if len(all_logs) <= 1:  # Seulement l'en-tête
                await ctx.send("📊 Aucun log trouvé pour les statistiques.")
                return

            logs_data = all_logs[1:]  # Exclure l'en-tête

            # Compter les actions par type
            action_counts = {}
            user_counts = {}

            for log in logs_data:
                if len(log) >= 3:
                    action = log[1] or "UNKNOWN"
                    user_id = log[2] or "UNKNOWN"

                    action_counts[action] = action_counts.get(action, 0) + 1
                    user_counts[user_id] = user_counts.get(user_id, 0) + 1

            # Créer l'embed des statistiques
            embed = discord.Embed(
                title="📊 Statistiques des logs de surveillance",
                description=f"Total des logs: **{len(logs_data)}**",
                color=0xe74c3c
            )

            # Top 10 des actions
            top_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if top_actions:
                actions_text = "\n".join([f"**{action}:** {count}" for action, count in top_actions])
                embed.add_field(
                    name="🎯 Top 10 des actions",
                    value=actions_text,
                    inline=True
                )

            # Top 10 des utilisateurs les plus actifs
            top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if top_users:
                users_text = "\n".join([f"**{user_id}:** {count}" for user_id, count in top_users])
                embed.add_field(
                    name="👥 Top 10 des utilisateurs",
                    value=users_text,
                    inline=True
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"[LOGS_STATS] Erreur lors de l'affichage des statistiques: {e}")
            await ctx.send(f"❌ Erreur lors de l'affichage des statistiques: {e}")

    @commands.command(name="verifier_integrite", help="Vérifie l'intégrité des données des cartes")
    @commands.has_permissions(administrator=True)
    async def verifier_integrite(self, ctx: commands.Context):
        """Commande d'administration pour vérifier l'intégrité des données."""
        await ctx.send("🔍 Vérification de l'intégrité des données en cours...")

        try:
            report = {
                "total_cards_checked": 0,
                "total_vault_checked": 0,
                "corrupted_cards": [],
                "corrupted_vault": [],
                "invalid_users": [],
                "error": None
            }

            # Vérification des cartes principales
            cards_cache = self.storage.get_cards_cache()
            if cards_cache:
                for i, row in enumerate(cards_cache[1:], start=2):  # Skip header
                    if len(row) < 3:
                        continue

                    report["total_cards_checked"] += 1

                    for j, cell in enumerate(row[2:], start=3):
                        if not cell:
                            continue
                        if ":" not in cell:
                            report["corrupted_cards"].append(f"Ligne {i}, Col {j}: Format invalide ({cell})")
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            uid = int(uid.strip())
                            count = int(count.strip())
                            if uid <= 0 or count <= 0:
                                report["invalid_users"].append(f"Ligne {i}, Col {j}: Valeurs invalides ({cell})")
                        except (ValueError, IndexError):
                            report["corrupted_cards"].append(f"Ligne {i}, Col {j}: Format invalide ({cell})")

            # Vérification du vault
            vault_cache = self.storage.get_vault_cache()
            if vault_cache:
                for i, row in enumerate(vault_cache[1:], start=2):  # Skip header
                    if len(row) < 3:
                        continue

                    report["total_vault_checked"] += 1

                    for j, cell in enumerate(row[2:], start=3):
                        if not cell:
                            continue
                        if ":" not in cell:
                            report["corrupted_vault"].append(f"Ligne {i}, Col {j}: Format invalide dans vault ({cell})")
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            uid = int(uid.strip())
                            count = int(count.strip())
                            if uid <= 0 or count <= 0:
                                report["invalid_users"].append(f"Ligne {i}, Col {j}: Valeurs invalides dans vault ({cell})")
                        except (ValueError, IndexError):
                            report["corrupted_vault"].append(f"Ligne {i}, Col {j}: Format invalide dans vault ({cell})")

            # Créer l'embed de rapport
            embed = discord.Embed(
                title="🔍 Rapport d'intégrité",
                color=discord.Color.green() if not any([
                    report["corrupted_cards"], report["corrupted_vault"], report["invalid_users"]
                ]) else discord.Color.red()
            )

            embed.add_field(
                name="📈 Statistiques",
                value=f"Cartes vérifiées: {report['total_cards_checked']}\nVault vérifié: {report['total_vault_checked']}",
                inline=False
            )

            if report["corrupted_cards"]:
                corrupted_text = "\n".join(report["corrupted_cards"][:10])
                if len(report["corrupted_cards"]) > 10:
                    corrupted_text += f"\n... et {len(report['corrupted_cards']) - 10} autres"
                embed.add_field(
                    name="❌ Cartes corrompues",
                    value=corrupted_text,
                    inline=False
                )

            if report["corrupted_vault"]:
                vault_text = "\n".join(report["corrupted_vault"][:10])
                if len(report["corrupted_vault"]) > 10:
                    vault_text += f"\n... et {len(report['corrupted_vault']) - 10} autres"
                embed.add_field(
                    name="❌ Vault corrompu",
                    value=vault_text,
                    inline=False
                )

            if report["invalid_users"]:
                users_text = "\n".join(report["invalid_users"][:10])
                if len(report["invalid_users"]) > 10:
                    users_text += f"\n... et {len(report['invalid_users']) - 10} autres"
                embed.add_field(
                    name="⚠️ Utilisateurs invalides",
                    value=users_text,
                    inline=False
                )

            if not any([report["corrupted_cards"], report["corrupted_vault"], report["invalid_users"]]):
                embed.add_field(
                    name="✅ Résultat",
                    value="Aucun problème détecté !",
                    inline=False
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"[INTEGRITY] Erreur lors de la vérification: {e}")
            await ctx.send(f"❌ Erreur lors de la vérification: {e}")


async def setup(bot):
    """Fonction de setup pour charger le cog."""
    cards = Cards(bot)
    await bot.add_cog(cards)
    await bot.tree.sync()
    await cards.update_all_character_owners()
    logging.info("[CARDS] Cog Cards chargé avec succès")
