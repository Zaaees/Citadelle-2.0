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
                full_folder_id = os.getenv(f"FOLDER_{category.upper().replace(' ', '_')}_FULL_ID")
                if full_folder_id:
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
                else:
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
    
    def add_card_to_user(self, user_id: int, category: str, name: str) -> bool:
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
                        return True
                
                # Si la carte n'existe pas encore
                new_row = [category, name, f"{user_id}:1"]
                self.storage.sheet_cards.append_row(new_row)
                self.storage.refresh_cards_cache()
                return True
                
            except Exception as e:
                logging.error(f"[CARDS] Erreur lors de l'ajout de carte: {e}")
                return False
    
    def remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
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
                                    return True
                            except (ValueError, IndexError):
                                continue
                
                return False
                
            except Exception as e:
                logging.error(f"[CARDS] Erreur lors du retrait de carte: {e}")
                return False
    
    def _user_has_card(self, user_id: int, category: str, name: str) -> bool:
        """Vérifie si un utilisateur possède une carte spécifique."""
        user_cards = self.get_user_cards(user_id)
        return (category, name) in user_cards

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

        # Vérifier si c'est un identifiant (C1, C2, etc.)
        if input_text.upper().startswith('C') and input_text[1:].isdigit():
            # Recherche par identifiant
            discovery_index = int(input_text[1:])
            discoveries_cache = self.discovery_manager.storage.get_discoveries_cache()

            if discoveries_cache:
                for row in discoveries_cache[1:]:  # Skip header
                    if len(row) >= 6 and int(row[5]) == discovery_index:
                        category, name = row[0], row[1]
                        # Vérifier que l'utilisateur possède cette carte
                        owned_cards = self.get_user_cards(user_id)
                        if any(cat == category and n == name for cat, n in owned_cards):
                            return (category, name)
                        return None
            return None

        # Recherche par nom
        if not input_text.lower().endswith(".png"):
            input_text += ".png"

        normalized_input = normalize_name(input_text.removesuffix(".png"))
        owned_cards = self.get_user_cards(user_id)

        match = next(
            ((cat, name) for cat, name in owned_cards
             if normalize_name(name.removesuffix(".png")) == normalized_input),
            None
        )
        return match

    def get_card_identifier(self, category: str, name: str) -> str | None:
        """Récupère l'identifiant d'une carte (C1, C2, etc.)."""
        discovery_info = self.discovery_manager.get_discovery_info(category, name)
        if discovery_info:
            return f"C{discovery_info['discovery_index']}"
        return None

    def find_card_by_name(self, input_name: str) -> tuple[str, str, str] | None:
        """
        Recherche une carte par nom dans toutes les catégories.
        Retourne (catégorie, nom exact avec extension, file_id) ou None.
        """
        normalized_input = normalize_name(input_name.removesuffix(".png"))

        # Chercher dans les cartes normales et Full
        all_files = {}
        for cat, files in self.cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)
        for cat, files in self.upgrade_cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)

        for category, files in all_files.items():
            for file_info in files:
                file_name = file_info['name']
                normalized_file = normalize_name(file_name.removesuffix(".png"))
                if normalized_file == normalized_input:
                    # Retourner le nom avec extension pour correspondre au format de l'inventaire
                    return category, file_name, file_info['id']

        return None

    def download_drive_file(self, file_id: str) -> bytes | None:
        """Télécharge un fichier depuis Google Drive."""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            file_bytes = request.execute()
            return file_bytes
        except Exception as e:
            logging.error(f"[DRIVE] Erreur lors du téléchargement du fichier {file_id}: {e}")
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

    def generate_paginated_gallery_embeds(self, user: discord.abc.User, page: int = 0) -> tuple[discord.Embed, discord.Embed | None, dict] | None:
        """Construit les embeds de galerie paginés pour l'utilisateur donné (format original)."""
        try:
            user_cards = self.get_user_cards(user.id)
            if not user_cards:
                return None

            # Configuration de la pagination
            CARDS_PER_PAGE = 15  # Nombre de cartes par catégorie par page

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
            user_cards.sort(key=lambda c: rarity_order.get(c[0], 9))

            cards_by_cat: dict[str, list[str]] = {}
            for cat, name in user_cards:
                cards_by_cat.setdefault(cat, []).append(name)

            # Calculer le nombre total de pages nécessaires
            max_pages_needed = 0
            for cat in rarity_order:
                noms = cards_by_cat.get(cat, [])
                normales = [n for n in noms if not n.endswith(" (Full)")]
                fulls = [n for n in noms if n.endswith(" (Full)")]

                if normales:
                    counts = {}
                    for n in normales:
                        counts[n] = counts.get(n, 0) + 1
                    pages_for_cat = (len(counts) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
                    max_pages_needed = max(max_pages_needed, pages_for_cat)

                if fulls:
                    counts = {}
                    for n in fulls:
                        counts[n] = counts.get(n, 0) + 1
                    pages_for_cat = (len(counts) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
                    max_pages_needed = max(max_pages_needed, pages_for_cat)

            total_pages = max(1, max_pages_needed)
            current_page = max(0, min(page, total_pages - 1))

            embed_normales = discord.Embed(
                title=f"Galerie de {user.display_name} (Page {current_page + 1}/{total_pages})",
                color=discord.Color.blue(),
            )
            embed_full = discord.Embed(
                title=f"Cartes Full de {user.display_name} (Page {current_page + 1}/{total_pages})",
                color=discord.Color.gold(),
            )

            has_normal_cards = False
            has_full_cards = False

            for cat in rarity_order:
                noms = cards_by_cat.get(cat, [])

                normales = [n for n in noms if not n.endswith(" (Full)")]
                if normales:
                    counts: dict[str, int] = {}
                    for n in normales:
                        counts[n] = counts.get(n, 0) + 1
                    # Sort cards alphabetically within the category (accent-insensitive)
                    sorted_cards = sorted(counts.items(), key=lambda x: normalize_name(x[0].removesuffix('.png')))

                    # Pagination logic for normal cards
                    start_idx = current_page * CARDS_PER_PAGE
                    end_idx = start_idx + CARDS_PER_PAGE
                    page_cards = sorted_cards[start_idx:end_idx]

                    if page_cards:  # Only show category if there are cards on this page
                        has_normal_cards = True
                        lines = []
                        for n, c in page_cards:
                            try:
                                card_name = n.removesuffix('.png')
                                # Get card identifier if available
                                identifier = self.get_card_identifier(cat, n)
                                identifier_text = f" ({identifier})" if identifier else ""
                                count_text = f' (x{c})' if c > 1 else ''
                                lines.append(f"- **{card_name}**{identifier_text}{count_text}")
                            except Exception as e:
                                logging.error(f"[GALLERY] Erreur lors du traitement de la carte {n}: {e}")
                                continue

                        if lines:  # Only add field if we have valid lines
                            field_value = "\n".join(lines)

                            # Add pagination info if there are more cards
                            total_cards_in_cat = len(sorted_cards)
                            if total_cards_in_cat > CARDS_PER_PAGE:
                                showing_start = start_idx + 1
                                showing_end = min(end_idx, total_cards_in_cat)
                                field_value += f"\n\n*Affichage {showing_start}-{showing_end} sur {total_cards_in_cat}*"

                            try:
                                total_available = len({
                                    f['name'].removesuffix('.png')
                                    for f in self.cards_by_category.get(cat, [])
                                })
                                owned_unique = len(counts)

                                embed_normales.add_field(
                                    name=f"{cat} : {owned_unique}/{total_available}",
                                    value=field_value,
                                    inline=False,
                                )
                            except Exception as e:
                                logging.error(f"[GALLERY] Erreur lors de l'ajout du champ pour {cat}: {e}")
                                continue

                fulls = [n for n in noms if n.endswith(" (Full)")]
                if fulls:
                    counts: dict[str, int] = {}
                    for n in fulls:
                        counts[n] = counts.get(n, 0) + 1
                    # Sort cards alphabetically within the category (accent-insensitive)
                    sorted_cards = sorted(counts.items(), key=lambda x: normalize_name(x[0].removesuffix('.png')))

                    # Pagination logic for full cards
                    start_idx = current_page * CARDS_PER_PAGE
                    end_idx = start_idx + CARDS_PER_PAGE
                    page_cards = sorted_cards[start_idx:end_idx]

                    if page_cards:  # Only show category if there are cards on this page
                        has_full_cards = True
                        lines = []
                        for n, c in page_cards:
                            try:
                                card_name = n.removesuffix('.png')
                                count_text = f' (x{c})' if c > 1 else ''
                                lines.append(f"- **{card_name}**{count_text}")
                            except Exception as e:
                                logging.error(f"[GALLERY] Erreur lors du traitement de la carte Full {n}: {e}")
                                continue

                        if lines:  # Only add field if we have valid lines
                            field_value = "\n".join(lines)

                            # Add pagination info if there are more cards
                            total_cards_in_cat = len(sorted_cards)
                            if total_cards_in_cat > CARDS_PER_PAGE:
                                showing_start = start_idx + 1
                                showing_end = min(end_idx, total_cards_in_cat)
                                field_value += f"\n\n*Affichage {showing_start}-{showing_end} sur {total_cards_in_cat}*"

                            try:
                                total_full = len({
                                    f['name'].removesuffix('.png')
                                    for f in self.upgrade_cards_by_category.get(cat, [])
                                })
                                owned_full = len(counts)

                                embed_full.add_field(
                                    name=f"{cat} (Full) : {owned_full}/{total_full}",
                                    value=field_value,
                                    inline=False,
                                )
                            except Exception as e:
                                logging.error(f"[GALLERY] Erreur lors de l'ajout du champ Full pour {cat}: {e}")
                                continue

            # Prepare pagination info
            pagination_info = {
                'current_page': current_page,
                'total_pages': total_pages,
                'has_previous': current_page > 0,
                'has_next': current_page < total_pages - 1
            }

            # Return only the embeds that have content
            final_embed_full = embed_full if has_full_cards else None
            return embed_normales, final_embed_full, pagination_info

        except Exception as e:
            logging.error(f"[GALLERY] Erreur dans generate_paginated_gallery_embeds: {e}")
            return None

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
        """Commande principale du système de cartes."""
        logging.info("[DEBUG] Commande /cartes déclenchée")

        await interaction.response.defer(ephemeral=True)

        # Assigner automatiquement le rôle de collectionneur de cartes
        await self.ensure_card_collector_role(interaction)

        await self.update_character_ownership(interaction.user)

        view = CardsMenuView(self, interaction.user)

        # Calcul des statistiques de l'utilisateur
        user_cards = self.get_user_cards(interaction.user.id)
        drawn_count = len(user_cards)

        # Statistiques de cartes uniques
        unique_count = len(set(user_cards))
        unique_count_excluding_full = len(set([(cat, name) for cat, name in user_cards if not "(Full)" in name]))

        # Totaux disponibles
        total_unique = self.total_unique_cards_available()
        total_unique_excluding_full = self.total_unique_cards_available_excluding_full()

        # Classements
        rank, _ = self.get_user_rank(interaction.user.id)
        rank_excluding_full, _ = self.get_user_rank_excluding_full(interaction.user.id)

        rank_text = f"#{rank}" if rank else "Non classé"
        rank_text_excluding_full = f"#{rank_excluding_full}" if rank_excluding_full else "Non classé"

        # Vérifier si le tirage journalier est disponible
        can_draw_today = self.drawing_manager.can_perform_daily_draw(interaction.user.id)
        tirage_status = "✅ Disponible" if can_draw_today else "❌ Déjà effectué"

        # Créer l'embed principal simplifié
        embed = discord.Embed(
            title="🎴 Menu des Cartes",
            description=(
                f"**Bienvenue {interaction.user.display_name} !**\n\n"
                f"🌅 **Tirage journalier :** {tirage_status}\n"
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

    @app_commands.command(name="reclamer_bonus", description="Récupérez vos tirages bonus non réclamés")
    async def reclamer_bonus(self, interaction: discord.Interaction):
        """Permet de récupérer les tirages bonus accordés par les administrateurs."""
        # Assigner automatiquement le rôle de collectionneur de cartes
        await self.ensure_card_collector_role(interaction)

        await interaction.response.defer(ephemeral=True)

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
                await interaction.followup.send(
                    "❌ Vous n'avez aucun tirage bonus à réclamer.",
                    ephemeral=True
                )
                return

            # Effectuer les tirages bonus
            drawn_cards = self.drawing_manager.draw_cards(user_bonus)

            # Ajouter les cartes à l'inventaire
            for cat, name in drawn_cards:
                self.add_card_to_user(interaction.user.id, cat, name)

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

        except Exception as e:
            logging.error(f"[BONUS] Erreur lors de la réclamation des bonus: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la réclamation des bonus.",
                ephemeral=True
            )

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
            # Utiliser la méthode originale pour générer la galerie
            result = self.generate_paginated_gallery_embeds(member, 0)

            if not result:
                await ctx.send(f"❌ {member.display_name} n'a aucune carte dans sa collection.")
                return

            embed_normales, embed_full, pagination_info = result
            embeds = [embed_normales]
            if embed_full:
                embeds.append(embed_full)

            # Créer la vue de galerie admin
            gallery_view = AdminPaginatedGalleryView(self, member)
            await ctx.send(embeds=embeds, view=gallery_view)

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

            embed = discord.Embed(
                title="🎁 Bonus accordé",
                description=f"**{count}** tirage(s) bonus accordé(s) à {member.mention}",
                color=0x00ff00
            )
            embed.add_field(name="Raison", value=source, inline=False)

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"[GIVE_BONUS] Erreur: {e}")
            await ctx.send(f"❌ Erreur lors de l'attribution du bonus: {e}")

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
