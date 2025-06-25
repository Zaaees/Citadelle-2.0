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

    # ========== MÉTHODES UTILITAIRES ==========

    def find_user_card_by_input(self, user_id: int, input_text: str) -> tuple[str, str] | None:
        """Recherche une carte dans l'inventaire d'un utilisateur par nom ou ID."""
        normalized_input, is_card_id = parse_card_input(input_text)

        if is_card_id:
            # Recherche par ID de carte
            # Cette fonctionnalité sera implémentée avec le système d'ID
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

    def find_card_by_name(self, input_name: str) -> tuple[str, str, str] | None:
        """
        Recherche une carte par nom dans toutes les catégories.
        Retourne (catégorie, nom exact, file_id) ou None.
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
                    return category, file_name.removesuffix('.png'), file_info['id']

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

        # Calcul des tirages restants
        user_cards = self.get_user_cards(interaction.user.id)
        drawn_count = len(user_cards)

        # Créer l'embed principal
        embed = discord.Embed(
            title="🎴 Système de cartes à collectionner",
            description=f"Bienvenue {interaction.user.display_name} !",
            color=0x3498db
        )

        embed.add_field(
            name="📊 Vos statistiques",
            value=f"Cartes possédées : **{drawn_count}**",
            inline=True
        )

        embed.add_field(
            name="🎯 Actions disponibles",
            value="Utilisez les boutons ci-dessous pour interagir avec vos cartes.",
            inline=False
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="tirage_journalier", description="Effectuer votre tirage journalier gratuit")
    async def tirage_journalier(self, interaction: discord.Interaction):
        """Commande pour le tirage journalier."""
        await interaction.response.defer(ephemeral=True)

        # Vérifier si l'utilisateur peut effectuer son tirage journalier
        if not self.drawing_manager.can_perform_daily_draw(interaction.user.id):
            await interaction.followup.send(
                "🚫 Vous avez déjà effectué votre tirage journalier aujourd'hui.",
                ephemeral=True
            )
            return

        try:
            # Effectuer le tirage
            drawn_cards = self.drawing_manager.draw_cards(3)

            # Ajouter les cartes à l'inventaire
            for cat, name in drawn_cards:
                self.add_card_to_user(interaction.user.id, cat, name)

            # Enregistrer le tirage journalier
            self.drawing_manager.record_daily_draw(interaction.user.id)

            # Créer l'embed de résultat
            embed = discord.Embed(
                title="🌅 Tirage journalier !",
                description="Vous avez reçu 3 cartes gratuites !",
                color=0xf1c40f
            )

            for i, (cat, name) in enumerate(drawn_cards, 1):
                display_name = name.removesuffix('.png')
                embed.add_field(
                    name=f"Carte {i}",
                    value=f"**{display_name}**\n*{cat}*",
                    inline=True
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Annonce publique si nouvelles cartes
            await self._handle_announce_and_wall(interaction, drawn_cards)

        except Exception as e:
            logging.error(f"[DAILY_DRAW] Erreur lors du tirage journalier: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du tirage journalier.",
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
            # Créer la vue de galerie admin
            gallery_view = AdminPaginatedGalleryView(self, member)
            result = await gallery_view.get_gallery_page(0)

            if not result:
                await ctx.send(f"❌ {member.display_name} n'a aucune carte dans sa collection.")
                return

            embed_normales, embed_full, pagination_info = result
            embeds = [embed_normales, embed_full] if embed_full else [embed_normales]

            await ctx.send(embeds=embeds, view=gallery_view)

        except Exception as e:
            logging.error(f"[ADMIN_GALLERY] Erreur: {e}")
            await ctx.send("❌ Une erreur est survenue lors de l'affichage de la galerie.")


async def setup(bot):
    """Fonction de setup pour charger le cog."""
    cards = Cards(bot)
    await bot.add_cog(cards)
    await bot.tree.sync()
    await cards.update_all_character_owners()
    logging.info("[CARDS] Cog Cards chargé avec succès")
