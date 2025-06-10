from discord import app_commands
from discord.ext import commands
import discord
import random
import os, json, io
import asyncio
import threading
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread
import unicodedata
import re
import time
from datetime import datetime
import pytz
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

class TradeExchangeState:
    def __init__(self, cog, offerer, target, offer_cat, offer_name, return_cat, return_name):
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name
        self.return_cat = return_cat
        self.return_name = return_name
        self.confirmed_by_offer = False
        self.confirmed_by_target = False
        self.completed = False  # Pour éviter double validation

class TradeConfirmTargetView(discord.ui.View):
    def __init__(self, state: TradeExchangeState):
        super().__init__(timeout=60)
        self.state = state

    @discord.ui.button(label="Confirmer l'échange (destinataire)", style=discord.ButtonStyle.success)
    async def confirm_target(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.state.target.id:
            await interaction.response.send_message("Vous n'êtes pas le destinataire de l’échange.", ephemeral=True)
            return

        self.state.confirmed_by_target = True
        await interaction.response.send_message("✅ Vous avez confirmé. En attente du proposeur.", ephemeral=True)
        await self.check_and_finalize(interaction)

    async def check_and_finalize(self, interaction: discord.Interaction):
        if self.state.confirmed_by_offer and self.state.confirmed_by_target and not self.state.completed:
            await finalize_exchange(self.state, interaction)

async def finalize_exchange(state: TradeExchangeState, interaction: discord.Interaction):
    state.completed = True
    success = state.cog.safe_exchange(
        state.offerer.id, (state.offer_cat, state.offer_name),
        state.target.id, (state.return_cat, state.return_name)
    )

    if success:
        await state.offerer.send(
            f"📦 Échange confirmé ! Tu as donné **{state.offer_name}** et reçu **{state.return_name}**."
        )
        await state.target.send(
            f"📦 Échange confirmé ! Tu as donné **{state.return_name}** et reçu **{state.offer_name}**."
        )
    else:
        await state.offerer.send("❌ L’échange a échoué : une des cartes n’était plus disponible.")
        await state.target.send("❌ L’échange a échoué : une des cartes n’était plus disponible.")

class TradeConfirmOffererView(discord.ui.View):
    def __init__(self, state: TradeExchangeState):
        super().__init__(timeout=60)
        self.state = state

    @discord.ui.button(label="Confirmer l'échange (proposeur)", style=discord.ButtonStyle.success)
    async def confirm_offer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.state.offerer.id:
            await interaction.response.send_message("Vous n'êtes pas le proposeur de l’échange.", ephemeral=True)
            return

        self.state.confirmed_by_offer = True
        await interaction.response.send_message("✅ Vous avez confirmé. En attente du destinataire.", ephemeral=True)
        await self.check_and_finalize(interaction)

    async def check_and_finalize(self, interaction: discord.Interaction):
        if self.state.confirmed_by_offer and self.state.confirmed_by_target and not self.state.completed:
            await finalize_exchange(self.state, interaction)

# SOLUTION A : fonction « globale » hors de la classe
def _merge_cells(row):
    """Fusionne les colonnes d'un même utilisateur en nettoyant les espaces."""
    merged = {}
    for cell in row[2:]:
        cell = cell.strip()
        if not cell or ":" not in cell:
            continue
        uid, cnt = cell.split(":", 1)
        uid = uid.strip()
        try:
            cnt = int(cnt.strip())
        except ValueError:
            continue
        merged[uid] = merged.get(uid, 0) + cnt
    return row[:2] + [f"{uid}:{cnt}" for uid, cnt in merged.items()]

class Cards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cards_cache = None  # Cache temporaire du contenu de sheet_cards
        self.cards_cache_time = 0

        # Système de verrous pour éviter les race conditions
        self._cards_lock = threading.RLock()  # Verrou pour les opérations sur les cartes
        self._vault_lock = threading.RLock()  # Verrou pour les opérations sur le vault
        self._cache_lock = threading.RLock()  # Verrou pour les opérations de cache
        # Charger les identifiants du service Google (mêmes credentials que le cog inventaire)
        creds_info = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
        creds = Credentials.from_service_account_info(creds_info, scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ])
        # Client Google Sheets (pour persistance des cartes)
        self.gspread_client = gspread.authorize(creds)
        # Ouvrir la feuille Google Sheets dédiée aux cartes (ID dans .env)
        spreadsheet = self.gspread_client.open_by_key(os.getenv('GOOGLE_SHEET_ID_CARTES'))
        self.sheet_cards = spreadsheet.sheet1  # première feuille utilisée pour l'inventaire des cartes
        try:
            self.sheet_lancement = spreadsheet.worksheet("Lancement")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_lancement = spreadsheet.add_worksheet(title="Lancement", rows="1000", cols="2")

        try:
            self.sheet_daily_draw = spreadsheet.worksheet("Tirages Journaliers")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_daily_draw = spreadsheet.add_worksheet(title="Tirages Journaliers", rows="1000", cols="2")

        # ————— Bonus tirages —————
        try:
            self.sheet_bonus = spreadsheet.worksheet("Bonus")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_bonus = spreadsheet.add_worksheet(title="Bonus", rows="1000", cols="4")
            # initialiser l’en‑tête
            self.sheet_bonus.append_row(["user_id", "source", "date", "claimed"])

        # ————— Vault pour les échanges —————
        try:
            self.sheet_vault = spreadsheet.worksheet("Vault")
        except gspread.exceptions.WorksheetNotFound:
            self.sheet_vault = spreadsheet.add_worksheet(title="Vault", rows="1000", cols="20")
            # initialiser l'en‑tête
            self.sheet_vault.append_row(["category", "name", "user_data..."])

        # Cache pour le vault
        self.vault_cache = None
        self.vault_cache_time = 0

       
        # Service Google Drive pour accéder aux images des cartes
        self.drive_service = build('drive', 'v3', credentials=creds)
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
        self.cards_by_category = {}  # ex: {"Fondateur": [{"name": ..., "id": ...}, ...], ...}
        for category, folder_id in self.FOLDER_IDS.items():
            if folder_id:
                # ❶ Cartes « normales »
                results = self.drive_service.files().list(
                    q=f"'{folder_id}' in parents",
                    fields="files(id, name, mimeType)"      # <-- ajoute mimeType
                ).execute()

                # Ajoute ce filtre juste après
                files = [
                    f for f in results.get('files', [])
                    if f.get('mimeType', '').startswith('image/')
                    and f['name'].lower().endswith('.png')
                ]
                self.cards_by_category[category] = files

         # ————— Doublons “Full” pour Élèves —————
         # ID du dossier “doublons” à déclarer dans .env : FOLDER_ELEVES_DOUBLONS_ID
        self.upgrade_folder_ids = {
             "Élèves": os.getenv("FOLDER_ELEVES_DOUBLONS_ID")
         }
         # Nombre de cartes normales à échanger pour obtenir la Full
        self.upgrade_thresholds = {"Élèves": 5}
         # Précharge les fichiers “Full” dans self.upgrade_cards_by_category
        self.upgrade_cards_by_category = {}
        for cat, folder_id in self.upgrade_folder_ids.items():
             if folder_id:
                # ❷ Cartes « Full »
                results = self.drive_service.files().list(
                    q=f"'{folder_id}' in parents",
                    fields="files(id, name, mimeType)"
                ).execute()

                files = [
                    f for f in results.get('files', [])
                    if f.get('mimeType', '').startswith('image/')
                    and f['name'].lower().endswith('.png')
                ]
                self.upgrade_cards_by_category[cat] = files
    
    def sanitize_filename(self, name: str) -> str:
        """Nettoie le nom d'une carte pour une utilisation sûre dans les fichiers Discord."""
        return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    def build_card_embed(self, cat: str, name: str, file_bytes: bytes) -> tuple[discord.Embed, discord.File]:
        """Construit un embed et le fichier attaché pour une carte.

        Le fichier utilise toujours le nom constant ``card.png`` afin que
        l'URL ``attachment://card.png`` reste stable et ne dépende pas du nom
        de la carte fourni par l'utilisateur.
        """
        file = discord.File(io.BytesIO(file_bytes), filename="card.png")
        embed = discord.Embed(
            title=name,
            description=f"Catégorie : **{cat}**",
            color=0x4E5D94,
        )
        embed.set_image(url="attachment://card.png")
        return embed, file
    
    def refresh_cards_cache(self):
        """Recharge le cache depuis Google Sheets (limité par minute)."""
        with self._cache_lock:
            try:
                self.cards_cache = self.sheet_cards.get_all_values()
                self.cards_cache_time = time.time()
                logging.info("[CACHE] Cache des cartes rechargé avec succès")
            except Exception as e:
                logging.error(f"[CACHE] Erreur de lecture Google Sheets : {e}")
                self.cards_cache = None

    def refresh_vault_cache(self):
        """Recharge le cache du vault depuis Google Sheets."""
        with self._cache_lock:
            try:
                self.vault_cache = self.sheet_vault.get_all_values()
                self.vault_cache_time = time.time()
                logging.info("[VAULT_CACHE] Cache du vault rechargé avec succès")
            except Exception as e:
                logging.error(f"[VAULT_CACHE] Erreur de lecture Google Sheets : {e}")
                self.vault_cache = None
    
    def get_user_cards(self, user_id: int):
        """Récupère les cartes d’un utilisateur depuis le cache ou les données."""
        with self._cache_lock:
            now = time.time()
            if not self.cards_cache or now - self.cards_cache_time > 5:  # 5 sec de validité
                self.refresh_cards_cache()

            if not self.cards_cache:
                return []

            rows = self.cards_cache[1:]  # Skip header
            user_cards = []
            for row in rows:
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

    def _create_unified_trade_confirmation_embed(self, initiator, target, initiator_vault, target_vault, description):
        """Crée un embed unifié pour les confirmations d'échange."""
        embed = discord.Embed(
            title="🔄 Confirmation d'échange complet",
            description=description,
            color=0x4E5D94
        )

        # Afficher un résumé des cartes qui seront échangées
        initiator_unique = list({(cat, name) for cat, name in initiator_vault})
        target_unique = list({(cat, name) for cat, name in target_vault})

        # Cartes que l'initiateur donne
        give_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in initiator_unique[:6]])
        if len(initiator_unique) > 6:
            give_text += f"\n... et {len(initiator_unique) - 6} autres cartes"

        embed.add_field(
            name=f"📤 {initiator.display_name} donne ({len(initiator_unique)} cartes uniques)",
            value=give_text if give_text else "Aucune carte",
            inline=False
        )

        # Cartes que le destinataire donne
        receive_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in target_unique[:6]])
        if len(target_unique) > 6:
            receive_text += f"\n... et {len(target_unique) - 6} autres cartes"

        embed.add_field(
            name=f"📤 {target.display_name} donne ({len(target_unique)} cartes uniques)",
            value=receive_text if receive_text else "Aucune carte",
            inline=False
        )

        embed.add_field(
            name="⚠️ Important",
            value="Cet échange transfère TOUTES les cartes des deux coffres vers vos inventaires principaux.",
            inline=False
        )

        return embed

    def get_user_vault_cards(self, user_id: int):
        """Récupère les cartes du vault d'un utilisateur."""
        with self._cache_lock:
            now = time.time()
            if not self.vault_cache or now - self.vault_cache_time > 5:  # 5 sec de validité
                self.refresh_vault_cache()

            if not self.vault_cache:
                return []

            rows = self.vault_cache[1:]  # Skip header
            user_vault_cards = []
            for row in rows:
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
                            user_vault_cards.extend([(cat, name)] * int(count))
                    except (ValueError, IndexError) as e:
                        logging.warning(f"[SECURITY] Données corrompues dans get_user_vault_cards: {cell}, erreur: {e}")
                        continue
            return user_vault_cards

    def add_card_to_vault(self, user_id: int, category: str, name: str, skip_possession_check: bool = False) -> bool:
        """Ajoute une carte au vault d'un utilisateur."""
        with self._vault_lock:
            try:
                # Validation des paramètres d'entrée
                if not category or not name or user_id <= 0:
                    logging.error(f"[SECURITY] Paramètres invalides pour add_card_to_vault: user_id={user_id}, category='{category}', name='{name}'")
                    return False

                # RESTRICTION: Empêcher le dépôt de cartes Full dans le vault
                if "(Full)" in name:
                    logging.error(f"[SECURITY] Tentative de dépôt d'une carte Full dans le vault: user_id={user_id}, carte=({category}, {name})")
                    return False

                # Vérifier que l'utilisateur possède cette carte avant de l'ajouter au vault
                # (sauf si skip_possession_check=True, utilisé lors du dépôt après retrait de l'inventaire)
                if not skip_possession_check:
                    user_cards = self.get_user_cards(user_id)
                    if not any(cat == category and n == name for cat, n in user_cards):
                        logging.error(f"[SECURITY] Tentative d'ajout d'une carte non possédée au vault: user_id={user_id}, carte=({category}, {name})")
                        return False

                rows = self.sheet_vault.get_all_values()
                for i, row in enumerate(rows):
                    if len(row) < 2:
                        continue
                    if row[0] == category and row[1] == name:
                        original_len = len(row)
                        for j in range(2, len(row)):
                            cell = row[j].strip()
                            if cell.startswith(f"{user_id}:"):
                                try:
                                    uid, count = cell.split(":", 1)
                                    uid = uid.strip()
                                    new_count = int(count) + 1
                                    row[j] = f"{uid}:{new_count}"
                                    cleaned_row = _merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.sheet_vault.update(f"A{i+1}", [cleaned_row])
                                    self.refresh_vault_cache()
                                    logging.info(f"[VAULT] Carte ajoutée au vault: user_id={user_id}, carte=({category}, {name}), nouveau_count={new_count}")
                                    return True
                                except (ValueError, IndexError) as e:
                                    logging.error(f"[SECURITY] Données corrompues dans add_card_to_vault: {cell}, erreur: {e}")
                                    return False
                        row.append(f"{user_id}:1")
                        cleaned_row = _merge_cells(row)
                        pad = max(original_len + 1, len(cleaned_row)) - len(cleaned_row)
                        cleaned_row += [""] * pad
                        self.sheet_vault.update(f"A{i+1}", [cleaned_row])
                        self.refresh_vault_cache()
                        logging.info(f"[VAULT] Nouvelle entrée ajoutée au vault: user_id={user_id}, carte=({category}, {name})")
                        return True
                # Si la carte n'existe pas encore dans le vault
                new_row = [category, name, f"{user_id}:1"]
                self.sheet_vault.append_row(new_row)
                self.refresh_vault_cache()
                logging.info(f"[VAULT] Nouvelle carte créée dans le vault: user_id={user_id}, carte=({category}, {name})")
                return True
            except Exception as e:
                logging.error(f"[SECURITY] Erreur lors de l'ajout de la carte au vault: {e}")
                return False

    def remove_card_from_vault(self, user_id: int, category: str, name: str) -> bool:
        """Supprime une carte du vault d'un utilisateur."""
        with self._vault_lock:
            try:
                # Validation des paramètres d'entrée
                if not category or not name or user_id <= 0:
                    logging.error(f"[SECURITY] Paramètres invalides pour remove_card_from_vault: user_id={user_id}, category='{category}', name='{name}'")
                    return False

                # Vérifier que l'utilisateur a cette carte dans son vault
                vault_cards = self.get_user_vault_cards(user_id)
                if not any(cat == category and n == name for cat, n in vault_cards):
                    logging.error(f"[SECURITY] Tentative de suppression d'une carte non présente dans le vault: user_id={user_id}, carte=({category}, {name})")
                    return False

                rows = self.sheet_vault.get_all_values()
                for i, row in enumerate(rows):
                    if len(row) < 2:
                        continue
                    if row[0] == category and row[1] == name:
                        original_len = len(row)
                        for j in range(2, len(row)):
                            cell = row[j].strip()
                            if cell.startswith(f"{user_id}:"):
                                try:
                                    uid, count = cell.split(":", 1)
                                    uid = uid.strip()
                                    current_count = int(count)
                                    if current_count > 1:
                                        new_count = current_count - 1
                                        row[j] = f"{uid}:{new_count}"
                                        logging.info(f"[VAULT] Carte retirée du vault: user_id={user_id}, carte=({category}, {name}), nouveau_count={new_count}")
                                    else:
                                        row[j] = ""
                                        logging.info(f"[VAULT] Dernière carte retirée du vault: user_id={user_id}, carte=({category}, {name})")
                                    cleaned_row = _merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.sheet_vault.update(f"A{i+1}", [cleaned_row])
                                    self.refresh_vault_cache()
                                    return True
                                except (ValueError, IndexError) as e:
                                    logging.error(f"[SECURITY] Données corrompues dans remove_card_from_vault: {cell}, erreur: {e}")
                                    return False
                return False
            except Exception as e:
                logging.error(f"[SECURITY] Erreur lors de la suppression de la carte du vault: {e}")
                return False

    def get_unique_card_counts(self) -> dict[int, int]:
        """Retourne un dictionnaire {user_id: nombre de cartes différentes}."""
        now = time.time()
        if not self.cards_cache or now - self.cards_cache_time > 5:
            self.refresh_cards_cache()

        if not self.cards_cache:
            return {}

        rows = self.cards_cache[1:]
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

    def get_leaderboard(self, top_n: int = 5) -> list[tuple[int, int]]:
        """Renvoie la liste triée des (user_id, compte unique) pour les `top_n` meilleurs."""
        counts = self.get_unique_card_counts()
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

    def total_unique_cards_available(self) -> int:
        """Nombre total de cartes différentes existantes."""
        total = 0
        for lst in (*self.cards_by_category.values(), *self.upgrade_cards_by_category.values()):
            total += len(lst)
        return total

    def generate_gallery_embeds(self, user: discord.abc.User) -> tuple[discord.Embed, discord.Embed] | None:
        """Construit les embeds de galerie pour l'utilisateur donné."""
        user_cards = self.get_user_cards(user.id)
        if not user_cards:
            return None

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

        embed_normales = discord.Embed(
            title=f"Galerie de {user.display_name}",
            color=discord.Color.blue(),
        )
        embed_full = discord.Embed(
            title=f"Cartes Full de {user.display_name}",
            color=discord.Color.gold(),
        )

        for cat in rarity_order:
            noms = cards_by_cat.get(cat, [])

            normales = [n for n in noms if not n.endswith(" (Full)")]
            if normales:
                counts: dict[str, int] = {}
                for n in normales:
                    counts[n] = counts.get(n, 0) + 1
                lines = [
                    f"- **{n.removesuffix('.png')}**{' (x'+str(c)+')' if c>1 else ''}"
                    for n, c in counts.items()
                ]

                total_available = len({
                    f['name'].removesuffix('.png')
                    for f in self.cards_by_category.get(cat, [])
                })
                owned_unique = len(counts)

                embed_normales.add_field(
                    name=f"{cat} : {owned_unique}/{total_available}",
                    value="\n".join(lines),
                    inline=False,
                )

            fulls = [n for n in noms if n.endswith(" (Full)")]
            if fulls:
                counts: dict[str, int] = {}
                for n in fulls:
                    counts[n] = counts.get(n, 0) + 1
                lines = [
                    f"- **{n.removesuffix('.png')}**{' (x'+str(c)+')' if c>1 else ''}"
                    for n, c in counts.items()
                ]

                total_full = len({
                    f['name'].removesuffix('.png')
                    for f in self.upgrade_cards_by_category.get(cat, [])
                })
                owned_full = len(counts)

                embed_full.add_field(
                    name=f"{cat} (Full) : {owned_full}/{total_full}",
                    value="\n".join(lines),
                    inline=False,
                )

        return embed_normales, embed_full

    
    def safe_exchange(self, user1_id, card1, user2_id, card2) -> bool:
        """Effectue un échange sécurisé entre deux utilisateurs avec rollback complet en cas d'échec."""
        # Utiliser les deux verrous pour éviter les race conditions
        with self._cards_lock:
            try:
                # Validation des paramètres
                if not card1 or not card2 or len(card1) != 2 or len(card2) != 2:
                    logging.error(f"[SECURITY] Paramètres d'échange invalides: card1={card1}, card2={card2}")
                    return False

                if user1_id <= 0 or user2_id <= 0 or user1_id == user2_id:
                    logging.error(f"[SECURITY] IDs utilisateurs invalides: user1_id={user1_id}, user2_id={user2_id}")
                    return False

                # Vérifier que les cartes existent dans le système
                all_files = {}
                for cat, files in self.cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)
                for cat, files in self.upgrade_cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)

                card1_exists = any(f['name'].removesuffix('.png') == card1[1] for f in all_files.get(card1[0], []))
                card2_exists = any(f['name'].removesuffix('.png') == card2[1] for f in all_files.get(card2[0], []))

                if not card1_exists or not card2_exists:
                    logging.error(f"[SECURITY] Cartes inexistantes dans l'échange: card1_exists={card1_exists}, card2_exists={card2_exists}")
                    return False

                # Obtenir les inventaires actuels
                cards1 = self.get_user_cards(user1_id)
                cards2 = self.get_user_cards(user2_id)

                def contains_card(card_list, card):
                    return any(
                        cat == card[0] and self.normalize_name(name.removesuffix(".png")) == self.normalize_name(card[1].removesuffix(".png"))
                        for cat, name in card_list
                    )

                if not contains_card(cards1, card1) or not contains_card(cards2, card2):
                    logging.warning(f"[SAFE_EXCHANGE] Échec : carte(s) non trouvée(s) - user1_id={user1_id} card1={card1}, user2_id={user2_id} card2={card2}")
                    return False

                # Sauvegarder l'état initial pour rollback complet
                initial_cards1 = cards1.copy()
                initial_cards2 = cards2.copy()

                logging.info(f"[SAFE_EXCHANGE] Début échange: user1_id={user1_id} donne {card1} pour {card2}, user2_id={user2_id} donne {card2} pour {card1}")

                # Phase 1: Suppression des cartes
                success1 = self.remove_card_from_user(user1_id, card1[0], card1[1])
                success2 = self.remove_card_from_user(user2_id, card2[0], card2[1])

                if not (success1 and success2):
                    logging.error(f"[SAFE_EXCHANGE] Suppression échouée - success1={success1}, success2={success2}")
                    # Rollback des suppressions réussies
                    if success1:
                        self.add_card_to_user(user1_id, card1[0], card1[1])
                    if success2:
                        self.add_card_to_user(user2_id, card2[0], card2[1])
                    return False

                # Phase 2: Ajout des cartes échangées
                add1 = self.add_card_to_user(user1_id, card2[0], card2[1])
                add2 = self.add_card_to_user(user2_id, card1[0], card1[1])

                if not (add1 and add2):
                    logging.error(f"[SAFE_EXCHANGE] Ajout échoué - add1={add1}, add2={add2}. Rollback complet en cours")

                    # Rollback complet: restaurer l'état initial
                    if add1:
                        self.remove_card_from_user(user1_id, card2[0], card2[1])
                    if add2:
                        self.remove_card_from_user(user2_id, card1[0], card1[1])

                    # Restaurer les cartes supprimées
                    self.add_card_to_user(user1_id, card1[0], card1[1])
                    self.add_card_to_user(user2_id, card2[0], card2[1])
                    return False

                # Vérification finale de l'intégrité
                final_cards1 = self.get_user_cards(user1_id)
                final_cards2 = self.get_user_cards(user2_id)

                # Vérifier que l'échange s'est bien passé
                if not contains_card(final_cards1, card2) or not contains_card(final_cards2, card1):
                    logging.error(f"[SAFE_EXCHANGE] Vérification finale échouée. Rollback complet.")
                    # Rollback complet
                    self.remove_card_from_user(user1_id, card2[0], card2[1])
                    self.remove_card_from_user(user2_id, card1[0], card1[1])
                    self.add_card_to_user(user1_id, card1[0], card1[1])
                    self.add_card_to_user(user2_id, card2[0], card2[1])
                    return False

                self.refresh_cards_cache()
                logging.info(f"[SAFE_EXCHANGE] Échange réussi entre user1_id={user1_id} et user2_id={user2_id}")
                return True

            except Exception as e:
                logging.error(f"[SAFE_EXCHANGE] Erreur critique: {e}")
                return False


    def compute_total_medals(self, user_id: int, students: dict, user_character_names: set) -> int:
        owned_chars = []
        for char_name in user_character_names:
            if char_name in students and students[char_name].get("user_id") != user_id:
                students[char_name]["user_id"] = user_id
        for data in students.values():
            if data.get("user_id") == user_id:
                owned_chars.append(data)
        if owned_chars:
            most_medals = max(char.get("medals", 0) for char in owned_chars)
            bonus_draws = (len(owned_chars) - 1) * 5
            return most_medals + bonus_draws
        return 0

    async def _handle_announce_and_wall(self, interaction: discord.Interaction, drawn_cards: list[tuple[str, str]]):
            announce_channel = self.bot.get_channel(1360512727784882207)
            if not announce_channel:
                return

            try:
                # 1) Charger toutes les cartes déjà vues (feuille Google Sheets)
                all_user_cards = self.sheet_cards.get_all_values()[1:]
                seen = {(row[0], row[1]) for row in all_user_cards if len(row) >= 2}

                # 2) Fusionner les fichiers “normaux” et “Full”
                all_files = {}
                for cat, files in self.cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)
                for cat, files in self.upgrade_cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)

                # 3) Identifier les nouvelles cartes
                new_draws = [card for card in drawn_cards if card not in seen]
                if not new_draws:
                    return

                # 4) Envoyer chaque carte dans un embed avec l'image
                for cat, name in new_draws:
                    file_id = next(
                        (f['id'] for f in all_files.get(cat, [])
                        if f['name'].removesuffix(".png") == name),
                        None
                    )
                    if not file_id:
                        continue

                    file_bytes = self.download_drive_file(file_id)
                    embed, image_file = self.build_card_embed(cat, name, file_bytes)
                    embed.set_footer(text=(
                        f"Découverte par : {interaction.user.display_name}\n"
                        f"→ {len(seen) + new_draws.index((cat,name)) + 1}"
                        f"{'ère' if (len(seen) + new_draws.index((cat,name)) + 1) == 1 else 'ème'} carte découverte"
                    ))

                    await announce_channel.send(embed=embed, file=image_file)

                # 5) Mettre à jour le message de progression
                async for msg in announce_channel.history(limit=20):
                    if msg.author == self.bot.user and msg.content.startswith("📝 Cartes découvertes"):
                        await msg.delete()
                        break

                total_cards = sum(
                    len(lst) for lst in (*self.cards_by_category.values(), *self.upgrade_cards_by_category.values())
                )
                discovered = len(seen) + len(new_draws)
                remaining = total_cards - discovered
                await announce_channel.send(
                    f"📝 Cartes découvertes : {discovered}/{total_cards} ({remaining} restantes)"
                )
            except Exception as e:
                logging.error("Erreur lors de la mise à jour du mur :", e)


    @app_commands.command(name="cartes", description="Gérer vos cartes à collectionner")
    async def cartes(self, interaction: discord.Interaction):
        logging.info("[DEBUG] Commande /cartes déclenchée")

        await interaction.response.defer(ephemeral=True)  # ✅ Ajout indispensable

        await self.update_character_ownership(interaction.user)

        view = CardsMenuView(self, interaction.user)

        # Calcul des tirages restants
        user_cards = self.get_user_cards(interaction.user.id)
        drawn_count = len(user_cards)

        inventory_cog = interaction.client.get_cog("Inventory")
        total_medals = 0
        if inventory_cog:
            students = inventory_cog.load_students()
            user_character_names = {name for name, data in students.items() if data.get("user_id") == interaction.user.id}
            owned_chars = [data for data in students.values() if data.get("user_id") == interaction.user.id]

            total_medals = self.compute_total_medals(interaction.user.id, students, user_character_names)

            if owned_chars:
                most_medals = max(char.get('medals', 0) for char in owned_chars)
                bonus_draws = (len(owned_chars) - 1) * 5
                total_medals = most_medals + bonus_draws

        draw_limit = total_medals * 3
        remaining_draws = max(draw_limit - drawn_count, 0)
        remaining_clicks = int(remaining_draws) // 3  # nombre de clics restants

        medals_used = most_medals if 'most_medals' in locals() else 0
        bonus_persos = (len(owned_chars) - 1) * 5 if 'owned_chars' in locals() and len(owned_chars) > 1 else 0
        bonus_tirages = bonus_persos

        unique_count = len({(c, n) for c, n in user_cards})
        total_unique = self.total_unique_cards_available()
        rank, _ = self.get_user_rank(interaction.user.id)
        total_players = len(self.get_unique_card_counts())
        rank_text = f"#{rank}/{total_players}" if rank else "N/A"

        await interaction.followup.send(
            f"**Menu des Cartes :**\n"
            f"🏅 Médailles comptées : **{medals_used}**\n"
            f"➕ Bonus de tirages : **{bonus_tirages}** (via personnages supplémentaires)\n"
            f"🎴 Tirages restants : **{remaining_clicks}**\n"
            f"📈 Cartes différentes : **{unique_count}/{total_unique}**\n"
            f"🥇 Classement : **{rank_text}**",
            view=view,
            ephemeral=True
        )


    async def handle_daily_draw(self, interaction: discord.Interaction):
        # 1) defer une seule fois pour éviter le timeout
        await interaction.response.defer(ephemeral=False)

        user_id_str = str(interaction.user.id)
        paris_tz    = pytz.timezone("Europe/Paris")
        today       = datetime.now(paris_tz).strftime("%Y-%m-%d")

        # 2) Vérification sans écrire dans Sheets
        all_rows = self.sheet_daily_draw.get_all_values()
        row_idx  = next((i for i, r in enumerate(all_rows) if r and r[0] == user_id_str), None)
        if row_idx is not None and len(all_rows[row_idx]) > 1 and all_rows[row_idx][1] == today:
            return await interaction.followup.send(
                "🚫 Vous avez déjà effectué votre tirage journalier aujourd’hui.",
                ephemeral=True
            )

        try:
            # 3) Exécute le tirage et l’envoi avant de toucher à la feuille
            view        = CardsMenuView(self, interaction.user)
            drawn_cards = self.draw_cards(3)

            # (a) annonce publique si nouvelles cartes
            seen = {(r[0], r[1]) for r in self.sheet_cards.get_all_values()[1:]}
            new_ = [c for c in drawn_cards if c not in seen]
            if new_:
                await self._handle_announce_and_wall(interaction, new_)

            # (d) affichage embeds/images
            embed_msgs = []
            for cat, name in drawn_cards:
                # Recherche du fichier image (inclut cartes Full)
                file_id = next(
                    (f["id"] for f in (self.cards_by_category.get(cat, []) + self.upgrade_cards_by_category.get(cat, []))
                    if f["name"].removesuffix(".png") == name),
                    None,
                )
                if file_id:
                    file_bytes = self.download_drive_file(file_id)
                    embed, image_file = self.build_card_embed(cat, name, file_bytes)
                    embed_msgs.append((embed, image_file))

            if embed_msgs:
                first_embed, first_file = embed_msgs[0]
                await interaction.edit_original_response(content=None, embed=first_embed, attachments=[first_file])
                for em, f in embed_msgs[1:]:
                    await interaction.followup.send(embed=em, file=f, ephemeral=False)

            # ——————————— COMMIT ———————————
            # 1) on écrit les cartes dans l’inventaire
            for cat, name in drawn_cards:
                self.add_card_to_user(interaction.user.id, cat, name)

            # 2) maintenant que l’inventaire est à jour, on gère les upgrades
            await self.check_for_upgrades(interaction, interaction.user.id, drawn_cards)

            # 3) enfin, on inscrit la date du tirage dans la feuille
            if row_idx is None:
                self.sheet_daily_draw.append_row([user_id_str, today])
            else:
                self.sheet_daily_draw.update(f"B{row_idx+1}", [[today]])

        except Exception as e:
            logging.error(f"[DAILY_DRAW] Échec du tirage : {e}")
            return await interaction.followup.send(
                "Une erreur est survenue, réessayez plus tard.",
                ephemeral=True
            )



    @app_commands.command(name="tirage_journalier", description="…")
    async def daily_draw(self, interaction: discord.Interaction):
        logging.info("[DEBUG] Commande /tirage_journalier déclenchée")
        await self.handle_daily_draw(interaction)


    def add_card_to_user(self, user_id: int, category: str, name: str) -> bool:
        """Ajoute une carte pour un utilisateur dans la persistance."""
        with self._cards_lock:
            try:
                # Validation des paramètres d'entrée
                if not category or not name or user_id <= 0:
                    logging.error(f"[SECURITY] Paramètres invalides pour add_card_to_user: user_id={user_id}, category='{category}', name='{name}'")
                    return False

                # Vérifier que la carte existe dans les fichiers disponibles
                all_files = {}
                for cat, files in self.cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)
                for cat, files in self.upgrade_cards_by_category.items():
                    all_files.setdefault(cat, []).extend(files)

                card_exists = any(
                    f['name'].removesuffix('.png') == name
                    for f in all_files.get(category, [])
                )
                if not card_exists:
                    logging.error(f"[SECURITY] Tentative d'ajout d'une carte inexistante: category='{category}', name='{name}'")
                    return False

                rows = self.sheet_cards.get_all_values()
                for i, row in enumerate(rows):
                    if len(row) < 2:
                        continue
                    if row[0] == category and row[1] == name:
                        original_len = len(row)
                        for j in range(2, len(row)):
                            cell = row[j].strip()
                            if cell.startswith(f"{user_id}:"):
                                try:
                                    uid, count = cell.split(":", 1)
                                    uid = uid.strip()
                                    new_count = int(count) + 1
                                    row[j] = f"{uid}:{new_count}"
                                    cleaned_row = _merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.sheet_cards.update(f"A{i+1}", [cleaned_row])
                                    self.refresh_cards_cache()
                                    logging.info(f"[CARDS] Carte ajoutée: user_id={user_id}, carte=({category}, {name}), nouveau_count={new_count}")
                                    return True
                                except (ValueError, IndexError) as e:
                                    logging.error(f"[SECURITY] Données corrompues dans add_card_to_user: {cell}, erreur: {e}")
                                    return False
                        row.append(f"{user_id}:1")
                        cleaned_row = _merge_cells(row)
                        pad = max(original_len + 1, len(cleaned_row)) - len(cleaned_row)
                        cleaned_row += [""] * pad
                        self.sheet_cards.update(f"A{i+1}", [cleaned_row])
                        self.refresh_cards_cache()
                        logging.info(f"[CARDS] Nouvelle entrée ajoutée: user_id={user_id}, carte=({category}, {name})")
                        return True
                # Si la carte n'existe pas encore
                new_row = [category, name, f"{user_id}:1"]
                self.sheet_cards.append_row(new_row)
                self.refresh_cards_cache()
                logging.info(f"[CARDS] Nouvelle carte créée: user_id={user_id}, carte=({category}, {name})")
                return True
            except Exception as e:
                logging.error(f"[SECURITY] Erreur lors de l'ajout de la carte dans Google Sheets: {e}")
                return False

    def remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
        """Supprime une carte pour un utilisateur dans la persistance."""
        with self._cards_lock:
            try:
                # Validation des paramètres d'entrée
                if not category or not name or user_id <= 0:
                    logging.error(f"[SECURITY] Paramètres invalides pour remove_card_from_user: user_id={user_id}, category='{category}', name='{name}'")
                    return False

                # Vérifier que l'utilisateur possède cette carte
                user_cards = self.get_user_cards(user_id)
                if not any(cat == category and n == name for cat, n in user_cards):
                    logging.error(f"[SECURITY] Tentative de suppression d'une carte non possédée: user_id={user_id}, carte=({category}, {name})")
                    return False

                rows = self.sheet_cards.get_all_values()
                for i, row in enumerate(rows):
                    if len(row) < 2:
                        continue
                    if row[0] == category and row[1] == name:
                        original_len = len(row)
                        for j in range(2, len(row)):
                            cell = row[j].strip()
                            if cell.startswith(f"{user_id}:"):
                                try:
                                    uid, count = cell.split(":", 1)
                                    uid = uid.strip()
                                    current_count = int(count)
                                    if current_count > 1:
                                        new_count = current_count - 1
                                        row[j] = f"{uid}:{new_count}"
                                        logging.info(f"[CARDS] Carte retirée: user_id={user_id}, carte=({category}, {name}), nouveau_count={new_count}")
                                    else:
                                        row[j] = ""
                                        logging.info(f"[CARDS] Dernière carte retirée: user_id={user_id}, carte=({category}, {name})")
                                    cleaned_row = _merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.sheet_cards.update(f"A{i+1}", [cleaned_row])
                                    self.refresh_cards_cache()
                                    return True
                                except (ValueError, IndexError) as e:
                                    logging.error(f"[SECURITY] Données corrompues dans remove_card_from_user: {cell}, erreur: {e}")
                                    return False
                return False
            except Exception as e:
                logging.error(f"[SECURITY] Erreur lors de la suppression de la carte dans Google Sheets: {e}")
                return False

    def verify_data_integrity(self) -> dict:
        """Vérifie l'intégrité des données et retourne un rapport."""
        with self._cache_lock:
            report = {
                "corrupted_cards": [],
                "corrupted_vault": [],
                "invalid_users": [],
                "duplicate_entries": [],
                "total_cards_checked": 0,
                "total_vault_checked": 0
            }

            try:
                # Vérification des cartes principales
                rows = self.sheet_cards.get_all_values()
                for i, row in enumerate(rows[1:], start=2):  # Skip header
                    if len(row) < 3:
                        continue

                    cat, name = row[0], row[1]
                    report["total_cards_checked"] += 1

                    # Vérifier que la carte existe dans les fichiers
                    all_files = {}
                    for c, files in self.cards_by_category.items():
                        all_files.setdefault(c, []).extend(files)
                    for c, files in self.upgrade_cards_by_category.items():
                        all_files.setdefault(c, []).extend(files)

                    card_exists = any(f['name'].removesuffix('.png') == name for f in all_files.get(cat, []))
                    if not card_exists:
                        report["corrupted_cards"].append(f"Ligne {i}: Carte inexistante ({cat}, {name})")

                    # Vérifier les données utilisateur
                    for j, cell in enumerate(row[2:], start=3):
                        if not cell.strip():
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            uid = uid.strip()
                            count = int(count.strip())
                            if count <= 0:
                                report["corrupted_cards"].append(f"Ligne {i}, Col {j}: Count invalide ({cell})")
                            if int(uid) <= 0:
                                report["invalid_users"].append(f"Ligne {i}, Col {j}: User ID invalide ({uid})")
                        except (ValueError, IndexError):
                            report["corrupted_cards"].append(f"Ligne {i}, Col {j}: Format invalide ({cell})")

                # Vérification du vault
                vault_rows = self.sheet_vault.get_all_values()
                for i, row in enumerate(vault_rows[1:], start=2):  # Skip header
                    if len(row) < 3:
                        continue

                    cat, name = row[0], row[1]
                    report["total_vault_checked"] += 1

                    # Vérifier que la carte existe dans les fichiers
                    card_exists = any(f['name'].removesuffix('.png') == name for f in all_files.get(cat, []))
                    if not card_exists:
                        report["corrupted_vault"].append(f"Ligne {i}: Carte inexistante dans vault ({cat}, {name})")

                    # Vérifier les données utilisateur du vault
                    for j, cell in enumerate(row[2:], start=3):
                        if not cell.strip():
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            uid = uid.strip()
                            count = int(count.strip())
                            if count <= 0:
                                report["corrupted_vault"].append(f"Ligne {i}, Col {j}: Count invalide dans vault ({cell})")
                            if int(uid) <= 0:
                                report["invalid_users"].append(f"Ligne {i}, Col {j}: User ID invalide dans vault ({uid})")
                        except (ValueError, IndexError):
                            report["corrupted_vault"].append(f"Ligne {i}, Col {j}: Format invalide dans vault ({cell})")

                logging.info(f"[INTEGRITY] Vérification terminée: {report['total_cards_checked']} cartes, {report['total_vault_checked']} vault entries")

            except Exception as e:
                logging.error(f"[INTEGRITY] Erreur lors de la vérification: {e}")
                report["error"] = str(e)

            return report

    @commands.command(name="verifier_integrite", help="Vérifie l'intégrité des données des cartes")
    @commands.has_permissions(administrator=True)
    async def verifier_integrite(self, ctx: commands.Context):
        """Commande d'administration pour vérifier l'intégrité des données."""
        await ctx.send("🔍 Vérification de l'intégrité des données en cours...")

        report = self.verify_data_integrity()

        embed = discord.Embed(
            title="📊 Rapport d'intégrité des données",
            color=discord.Color.blue() if not any([
                report["corrupted_cards"],
                report["corrupted_vault"],
                report["invalid_users"]
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
                name="❌ Utilisateurs invalides",
                value=users_text,
                inline=False
            )

        if not any([report["corrupted_cards"], report["corrupted_vault"], report["invalid_users"]]):
            embed.add_field(
                name="✅ Résultat",
                value="Aucun problème d'intégrité détecté !",
                inline=False
            )

        if "error" in report:
            embed.add_field(
                name="⚠️ Erreur",
                value=f"Erreur lors de la vérification: {report['error']}",
                inline=False
            )

        await ctx.send(embed=embed)

    def find_card_by_name(self, input_name: str) -> tuple[str, str, str] | None:
        """
        Recherche une carte par nom (tolérance accents, majuscules, .png) dans toutes les catégories,
        y compris les cartes Full.
        Retourne (catégorie, nom exact (avec extension si besoin), file_id) ou None.
        """
        normalized_input = self.normalize_name(input_name.removesuffix(".png"))

        # On cherche à la fois dans les dossiers 'normaux' et 'Full'
        # (on combine les deux dicts en un seul mapping catégorie → liste de fichiers)
        all_files = {}
        for cat, files in self.cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)
        for cat, files in self.upgrade_cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)

        for cat, files in all_files.items():
            for f in files:
                name = f["name"]               # p.ex. "Alex (Full).png" ou "Alex.png"
                normalized_file = self.normalize_name(name.removesuffix(".png"))
                if normalized_file == normalized_input:
                    return (cat, name, f["id"])
        return None
    
    def download_drive_file(self, file_id: str) -> bytes:
        """Télécharge un fichier depuis Google Drive par son ID et renvoie son contenu binaire."""
        request = self.drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()

    async def update_character_ownership(self, user: discord.User):
        """Met à jour les fiches appartenant à un utilisateur à partir des forums de fiches."""
        inventory_cog = self.bot.get_cog("Inventory")
        if not inventory_cog:
            return
        students = inventory_cog.load_students()
        forum_ids = [1090463730904604682, 1152643359568044094, 1217215470445269032]
        user_character_names = set()

        for forum_id in forum_ids:
            try:
                channel = self.bot.get_channel(forum_id)
                if not channel:
                    channel = await self.bot.fetch_channel(forum_id)

                threads = []
                threads.extend(channel.threads)

                archived = []
                async for thread in channel.archived_threads():
                    archived.append(thread)
                threads.extend(archived)

                for thread in threads:
                    if thread.owner_id == user.id:
                        user_character_names.add(thread.name)

            except Exception as e:
                logging.info("[update_character_ownership] Erreur forum %s : %s", forum_id, e)

        changed = False
        for char_name in user_character_names:
            for student_name in students:
                if self.normalize_name(char_name) == self.normalize_name(student_name):
                    if students[student_name].get("user_id") != user.id:
                        students[student_name]["user_id"] = user.id
                        changed = True
                    break


        if changed:
            inventory_cog.save_students(students)

    async def update_all_character_owners(self):
        """Balaye tous les forums de fiches pour assigner les bons owner_id dans students."""
        inventory_cog = self.bot.get_cog("Inventory")
        if not inventory_cog:
            return
        students = inventory_cog.load_students()
        forum_ids = [1090463730904604682, 1152643359568044094, 1217215470445269032]

        for forum_id in forum_ids:
            try:
                channel = self.bot.get_channel(forum_id)
                if not channel:
                    channel = await self.bot.fetch_channel(forum_id)

                threads = []
                threads.extend(channel.threads)

                archived = []
                async for thread in channel.archived_threads():
                    archived.append(thread)
                threads.extend(archived)

                for thread in threads:
                    thread_name = thread.name
                    for student_name in students:
                        if self.normalize_name(thread_name) == self.normalize_name(student_name):
                            students[student_name]["user_id"] = thread.owner_id
                            break

            except Exception as e:
                logging.info("[update_all_character_owners] Erreur forum %s : %s", forum_id, e)

        inventory_cog.save_students(students)

    def normalize_name(self, name: str) -> str:
        """Supprime les accents et met en minuscules pour comparaison insensible."""
        return ''.join(
            c for c in unicodedata.normalize('NFD', name)
            if unicodedata.category(c) != 'Mn'
        ).lower()

    def draw_cards(self, number: int) -> list[tuple[str, str]]:
        """Effectue un tirage aléatoire de `number` cartes avec rareté adaptative pour les variantes."""
        drawn = []
        rarity_weights = {
           "Secrète":     0.005,
            "Fondateur":   0.01,
            "Historique":  0.02,
            "Maître":      0.06,
            "Black Hole":  0.06,
            "Architectes": 0.07,
            "Professeurs": 0.1167,
            "Autre":       0.2569,
            "Élèves":      0.4203

        }

        all_categories = [
            "Secrète", "Fondateur", "Historique", "Maître", "Black Hole",
            "Architectes", "Professeurs", "Autre", "Élèves"
        ]
        categories = all_categories
        weights = [rarity_weights.get(cat, 0.01) for cat in categories]

        # 🔧 Normalisation des poids
        total = sum(weights)
        weights = [w / total for w in weights]
        number = int(number)

        for _ in range(number):
            # Tirage de la catégorie en fonction de sa rareté globale
            cat = random.choices(categories, weights=weights, k=1)[0]
            options = self.cards_by_category.get(cat, [])
            if not options:
                continue
            logging.info(f"[TIRAGE] → Catégorie tirée : {cat} (Cartes disponibles : {len(options)})")


            # Séparer cartes normales et variantes
            normales = [card for card in options if "(Variante)" not in card["name"]]
            variantes = [card for card in options if "(Variante)" in card["name"]]

            if not normales and not variantes:
                continue

            # Poids : 1.0 pour chaque carte normale, 0.5 pour chaque variante (deux fois plus rare)
            weighted_cards = []
            for card in normales:
                weighted_cards.append((card, 1.0))
            for card in variantes:
                weighted_cards.append((card, 0.5))

            # Tirage d’une carte dans la catégorie, avec pondération des variantes
            chosen_card = random.choices(
                population=[entry[0] for entry in weighted_cards],
                weights=[entry[1] for entry in weighted_cards],
                k=1
            )[0]
            is_variante = "(Variante)" in chosen_card["name"]
            logging.info(f"[TIRAGE] 🎴 Carte tirée : {chosen_card['name']} {'(Variante)' if is_variante else ''}")

            if chosen_card not in options:
                logging.warning(f"[ANOMALIE] La carte {chosen_card['name']} ne semble pas être dans {cat} !")

            # Retirer ".png" du nom de la carte
            card_name = chosen_card["name"].removesuffix(".png")
            drawn.append((cat, card_name))

        return drawn

    async def check_for_upgrades(
        self,
        interaction: discord.Interaction,
        user_id: int,
        drawn_cards: list[tuple[str,str]]
    ):
        """
        Pour chaque carte normale où l'utilisateur a atteint le seuil de
        doublons, on échange les N doublons contre la version Full,
        on notifie l'utilisateur et on met à jour le mur.
        """
        # 1) Récupérer tous les doublons de l'utilisateur
        user_cards = self.get_user_cards(user_id)
        # Compter les occurrences par (catégorie, nom)
        counts: dict[tuple[str,str], int] = {}
        for cat, name in user_cards:
            counts[(cat, name)] = counts.get((cat, name), 0) + 1

        # 2) Pour chaque carte où count >= seuil, effectuer l'upgrade

        for (cat, name), count in counts.items():
            if cat not in self.upgrade_thresholds:
                continue
            seuil = self.upgrade_thresholds[cat]
            if count >= seuil:
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
                    full_name = f"{name} (Full)"

                    file_id = next(
                        f['id'] for f in self.upgrade_cards_by_category[cat]
                        if self.normalize_name(f['name'].removesuffix(".png"))
                        == self.normalize_name(full_name)
                    )
                    file_bytes = self.download_drive_file(file_id)
                    embed, image_file = self.build_card_embed(cat, full_name, file_bytes)
                    embed.title = f"🎉 Carte Full obtenue : {full_name}"
                    embed.description = (
                        f"Vous avez échangé **{seuil}× {name}** "
                        f"contre **{full_name}** !"
                    )
                    embed.color = discord.Color.gold()

                    await interaction.followup.send(embed=embed, file=image_file)

                    await self._handle_announce_and_wall(interaction, [(cat, full_name)])

                    if not self.add_card_to_user(user_id, cat, full_name):
                        logging.error(
                            f"[UPGRADE] Échec ajout {full_name} pour {user_id}. Rollback"
                        )
                        for _ in range(seuil):
                            self.add_card_to_user(user_id, cat, name)


    def log_bonus(self, user_id: int, source: str):
        """Enregistre un bonus de tirage pour un utilisateur (non réclamé)."""
        paris_tz = pytz.timezone("Europe/Paris")
        today = datetime.now(paris_tz).strftime("%Y-%m-%d")
        # user_id, raison, date, colonne 'claimed' vide
        self.sheet_bonus.append_row([str(user_id), source, today, ""])

    
    async def handle_lancement(self, interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)

        try:
            all_rows = self.sheet_lancement.get_all_values()
            if any(row and row[0] == user_id_str for row in all_rows):
                await interaction.response.send_message("🚫 Vous avez déjà utilisé votre tirage de lancement.", ephemeral=True)
                return
        except Exception as e:
            logging.error(f"[LANCEMENT] Erreur lecture feuille Lancement : {e}")
            await interaction.response.send_message("Erreur de lecture Google Sheets. Réessayez plus tard.", ephemeral=True)
            return

        try:
            self.sheet_lancement.append_row([user_id_str, interaction.user.display_name])
        except Exception as e:
            logging.error(f"[LANCEMENT] Erreur ajout feuille Lancement : {e}")
            await interaction.response.send_message("Erreur lors de l'enregistrement. Réessayez plus tard.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        view = CardsMenuView(self, interaction.user)
        drawn_cards = await view.perform_draw(interaction)

        if not drawn_cards:
            await interaction.edit_original_response(content="Vous n’avez plus de tirages disponibles.")
            return

        embed_msgs = []
        for cat, name in drawn_cards:
            logging.info(f"[DEBUG] Traitement de carte : {cat} | {name}")
            file_id = next((f['id'] for f in self.cards_by_category.get(cat, []) if f['name'].removesuffix(".png") == name), None)
            if file_id:
                file_bytes = self.download_drive_file(file_id)
                embed, image_file = self.build_card_embed(cat, name, file_bytes)
                embed_msgs.append((embed, image_file))

        # Mise à jour du message initial
        if embed_msgs:
            first_embed, first_file = embed_msgs[0]
            await interaction.edit_original_response(content=None, embed=first_embed, attachments=[first_file])

        # Envoi des autres cartes
        for embed, file in embed_msgs[1:]:
            await interaction.followup.send(embed=embed, file=file, ephemeral=False)

        # Annonces publiques et mur
        await self._handle_announce_and_wall(interaction, drawn_cards)

    @commands.command(name="reconstruire_mur", help="Reconstruit le mur dans l'ordre de première découverte")
    @commands.has_permissions(administrator=True)
    async def reconstruire_mur(self, ctx: commands.Context):
        announce_channel = self.bot.get_channel(1360512727784882207)
        if not announce_channel:
            await ctx.send("Salon d’annonce introuvable.")
            return

        # Purge du salon
        await ctx.send("🧼 Suppression de tous les messages du mur en cours…")
        try:
            await announce_channel.purge(limit=None)
        except Exception as e:
            logging.warning(f"[RECONSTRUIRE_MUR] Impossible de tout purger : {e}")

        # Fusionner cartes normales et Full
        all_files = {}
        for category, files in self.cards_by_category.items():
            all_files.setdefault(category, []).extend(files)
        for category, files in self.upgrade_cards_by_category.items():
            all_files.setdefault(category, []).extend(files)

        try:
            rows = self.sheet_cards.get_all_values()[1:]
            index = 1
            for row in rows:
                if len(row) < 3 or not row[2].strip():
                    continue

                cat, name = row[0], row[1]
                discoverer_id = int(row[2].split(":", 1)[0].strip())
                member = ctx.guild.get_member(discoverer_id)
                if member:
                    discoverer_name = member.nick or member.name
                else:
                    try:
                        user = await self.bot.fetch_user(discoverer_id)
                        discoverer_name = user.name
                    except:
                        discoverer_name = f"<@{discoverer_id}>"

                file_id = next(
                    (f['id'] for f in all_files.get(cat, []) if f['name'].removesuffix(".png") == name),
                    None
                )
                if not file_id:
                    continue

                file_bytes = self.download_drive_file(file_id)
                embed, image_file = self.build_card_embed(cat, name, file_bytes)
                embed.set_footer(text=(
                    f"Découverte par : {discoverer_name}\n"
                    f"→ {index}{'ère' if index == 1 else 'ème'} carte découverte"
                ))

                await announce_channel.send(embed=embed, file=image_file)
                await asyncio.sleep(0.5)
                index += 1

            total_cards = sum(len(lst) for lst in all_files.values())
            discovered = index - 1
            remaining = total_cards - discovered
            await ctx.send(
                f"✅ Mur reconstruit : {discovered}/{total_cards} cartes postées ({remaining} restantes)."
            )
        except Exception as e:
            logging.error(f"[RECONSTRUIRE_MUR] Erreur : {e}")
            await ctx.send("❌ Une erreur est survenue lors de la reconstruction.")


    @app_commands.command(
        name="reclamer_bonus",
        description="Récupérez vos tirages bonus non réclamés"
    )
    async def reclamer_bonus(self, interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)
        # Lecture des bonus
        try:
            all_rows = self.sheet_bonus.get_all_values()[1:]  # skip header
        except Exception:
            return await interaction.response.send_message(
                "Erreur de lecture des bonus. Réessayez plus tard.", ephemeral=True
            )

        # Filtrer ceux non réclamés
        unclaimed = [
            (idx + 2, row)  # +2 car header + index base 0 → numéro ligne Sheets
            for idx, row in enumerate(all_rows)
            if len(row) >= 4 and row[0] == user_id_str and row[3] == ""
        ]
        if not unclaimed:
            return await interaction.response.send_message(
                "Vous n'avez aucun bonus non réclamé.", ephemeral=True
            )

        await interaction.response.defer(thinking=True, ephemeral=False)
        total_drawn = []
        new_cards_for_wall = []

        for row_index, _ in unclaimed:
            # marquer comme réclamé
            self.sheet_bonus.update(f"D{row_index}", [["X"]])
            # Tirage pur : 3 cartes, sans vérification de médailles
            drawn = self.draw_cards(3)
            # On garde la liste pour l’affichage public sur le mur
            new_cards_for_wall.extend(drawn)
            # On ajoute immédiatement ces cartes à l’inventaire de l’utilisateur
            for cat, name in drawn:
                self.add_card_to_user(interaction.user.id, cat, name)
            # On accumule pour l’embed privé
            total_drawn.extend(drawn)

        # Si on a de nouvelles cartes, on les annonce
        if new_cards_for_wall:
            await self._handle_announce_and_wall(interaction, new_cards_for_wall)


        # envoyer les cartes comme dans daily_draw
        embed_msgs = []
        for cat, name in total_drawn:
            # Recherche du fichier image (inclut cartes Full)
            file_id = next(
                (f["id"] for f in (self.cards_by_category.get(cat, []) + self.upgrade_cards_by_category.get(cat, []))
                if f["name"].removesuffix(".png") == name),
                None,
            )
            if not file_id:
                continue
            file_bytes = self.download_drive_file(file_id)
            embed, image_file = self.build_card_embed(cat, name, file_bytes)
            embed_msgs.append((embed, image_file))

        if embed_msgs:
            first_embed, first_file = embed_msgs[0]
            await interaction.edit_original_response(content=None, embed=first_embed, attachments=[first_file])
            for embed, file in embed_msgs[1:]:
                await interaction.followup.send(embed=embed, file=file)

        # Annonces publiques pour les cartes rares/variantes
        await self._handle_announce_and_wall(interaction, total_drawn)

    @commands.command(name="give_bonus")
    @commands.has_permissions(administrator=True)
    async def give_bonus(self, ctx: commands.Context, member: discord.Member, count: int = 1, *, source: str):
        """
        Donne un nombre de bonus de tirage à un joueur.
        Usage : !give_bonus @joueur [nombre] raison du bonus
        Exemple : !give_bonus @Alice 3 quête_RP
        """
        # Boucle pour ajouter 'count' bonus
        for _ in range(count):
            self.log_bonus(member.id, source)

        await ctx.send(
            f"✅ {count} bonus ajouté{'s' if count > 1 else ''} pour {member.display_name} (raison : {source})."
        )

    @commands.command(name="verifier_mur", help="Vérifie et met à jour le mur des cartes")
    @commands.has_permissions(administrator=True)
    async def verifier_mur(self, ctx: commands.Context):
        announce_channel = self.bot.get_channel(1360512727784882207)  # Remplace par ton ID si nécessaire
        if not announce_channel:
            await ctx.send("Salon d'annonce introuvable.")
            return

        await ctx.send("🔍 Vérification du mur des cartes en cours...")

        # Récupérer les cartes déjà présentes
        rows = self.sheet_cards.get_all_values()[1:]  # skip header
        seen_cards = {(row[0], row[1]) for row in rows if len(row) >= 2}

        # Fusionner cartes normales et Full
        all_files = {}
        for cat, files in self.cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)
        for cat, files in self.upgrade_cards_by_category.items():
            all_files.setdefault(cat, []).extend(files)

        # Détecter les cartes manquantes sur le mur
        missing_cards = []
        for card in seen_cards:
            cat, name = card
            message_exists = False
            async for msg in announce_channel.history(limit=None):
                if msg.embeds and msg.embeds[0].title == name:
                    message_exists = True
                    break
            if not message_exists:
                missing_cards.append((cat, name))

        # Poster les cartes manquantes
        index = len(seen_cards) - len(missing_cards) + 1
        for cat, name in missing_cards:
            discoverer_row = next((row for row in rows if row[0] == cat and row[1] == name), None)
            discoverer_id = int(discoverer_row[2].split(":", 1)[0].strip()) if discoverer_row and len(discoverer_row) > 2 else None
            member = ctx.guild.get_member(discoverer_id) if discoverer_id else None
            discoverer_name = member.display_name if member else "Inconnu"

            file_id = next((f['id'] for f in all_files.get(cat, []) if f['name'].removesuffix(".png") == name), None)
            if not file_id:
                continue

            file_bytes = self.download_drive_file(file_id)
            safe_name = self.sanitize_filename(name)
            image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")

            embed = discord.Embed(
                title=name,
                description=f"Catégorie : **{cat}**",
                color=0x4E5D94
            )
            embed.set_image(url=f"attachment://{safe_name}.png")
            embed.set_footer(
                text=(
                    f"Découverte par : {discoverer_name}\n"
                    f"→ {index}{'ère' if index == 1 else 'ème'} carte découverte"
                )
            )
            await announce_channel.send(embed=embed, file=image_file)
            await asyncio.sleep(1)
            index += 1

        # Mise à jour du message de progression
        async for msg in announce_channel.history(limit=50):
            if msg.author == self.bot.user and msg.content.startswith("📝 Cartes découvertes"):
                await msg.delete()
                break

        total_cards = sum(len(lst) for lst in all_files.values())
        discovered = len(seen_cards)
        remaining = total_cards - discovered

        await announce_channel.send(
            f"📝 Cartes découvertes : {discovered}/{total_cards} ({remaining} restantes)"
        )

        await ctx.send(f"✅ Mur vérifié : {len(missing_cards)} cartes ajoutées, progression mise à jour.")

    @commands.command(
        name="forcer_full",
        help="Force la conversion des doublons en Full pour un joueur"
    )
    @commands.has_permissions(administrator=True)  # ← ou le rôle que tu veux
    async def forcer_full(self, ctx: commands.Context, member: discord.Member):
        """
        Exécute check_for_upgrades sur le joueur indiqué, 
        même s’il n’est pas en train de tirer des cartes.
        Usage :  !forcer_full @Joueur
        """
        # --- petit “faux” Interaction : on lui donne juste .followup.send ---
        class DummyInteraction:
            def __init__(self, ctx, user):
                self.followup = ctx       # ctx.send existe → OK
                self.guild = ctx.guild    # utile pour _handle_announce_and_wall
                self.channel = ctx.channel
                self.user = user       # used by _handle_announce_and_wall

        fake_inter = DummyInteraction(ctx, member)

        # on lance la vérification (drawn_cards=[] pour ne rien annoncer de plus)
        await self.check_for_upgrades(fake_inter, member.id, [])

        await ctx.send(f"✅ Conversion forcée terminée pour {member.mention}.")

    @commands.command(name="voir_galerie")
    @commands.has_permissions(administrator=True)
    async def voir_galerie(self, ctx: commands.Context, member: discord.Member):
        """Affiche la galerie de cartes d'un utilisateur."""
        embeds = self.generate_gallery_embeds(member)
        if not embeds:
            await ctx.send(f"{member.display_name} n'a aucune carte pour le moment.")
            return

        embed_normales, embed_full = embeds
        await ctx.send(embeds=[embed_normales, embed_full])

class CardsMenuView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.user_id = user.id 

    @discord.ui.button(label="Tirer une carte", style=discord.ButtonStyle.primary)
    async def draw_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        await self.cog.update_character_ownership(interaction.user)

        drawn_cards = await self.perform_draw(interaction)
        # Vérifier et transformer les doublons en Full si besoin
        await self.cog.check_for_upgrades(interaction, self.user.id, drawn_cards)


        if not drawn_cards:
            await interaction.followup.send("🎖️ Vous n'avez plus assez de tirages disponibles (1 tirage requis, soit 3 cartes).", ephemeral=True)
            return

        # Générer les embeds
        embeds_and_files = []
        for cat, name in drawn_cards:
            logging.info(f"[DEBUG] Traitement de carte : {cat} | {name}")
            # Recherche du fichier image (inclut cartes Full)
            file_id = next(
                (f['id'] for f in (self.cog.cards_by_category.get(cat, []) + self.cog.upgrade_cards_by_category.get(cat, []))
                if f['name'].removesuffix(".png") == name),
                None
            )
            if file_id:
                file_bytes = self.cog.download_drive_file(file_id)
                safe_name = self.cog.sanitize_filename(name)
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                embed = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                embed.set_image(url=f"attachment://{safe_name}.png")
                embeds_and_files.append((embed, image_file))

        # Annonce publique si carte rare ou variante
        await self.cog._handle_announce_and_wall(interaction, drawn_cards)

    async def perform_draw(self, interaction: discord.Interaction) -> list[tuple[str, str]]:
        """
        Tire jusqu'à 3 cartes pour l'utilisateur, met à jour les données,
        et retourne la liste des cartes tirées sous forme (catégorie, nom).
        à appeler depuis /lancement ou draw_card.
        """
        # ✅ Exception : /tirage_journalier donne 3 cartes même sans personnage
        if interaction.command and interaction.command.name == "tirage_journalier":
            drawn_cards = self.cog.draw_cards(3)
            for cat, name in drawn_cards:
                self.cog.add_card_to_user(self.user.id, cat, name)
            return drawn_cards

        inventory_cog = interaction.client.get_cog("Inventory")
        if inventory_cog is None:
            return []

        students = inventory_cog.load_students()
        owned_chars = [data for data in students.values() if data.get("user_id") == self.user.id]
        user_character_names = {name for name, data in students.items() if data.get("user_id") == self.user.id}

        total_medals = self.cog.compute_total_medals(self.user.id, students, user_character_names)
        if owned_chars:
            most_medals = max(char.get("medals", 0) for char in owned_chars)
            bonus_draws = (len(owned_chars) - 1) * 5
            total_medals = most_medals + bonus_draws

        draw_limit = total_medals * 3
        user_cards = self.cog.get_user_cards(self.user.id)
        drawn_count = len(user_cards)
        remaining_draws = max(draw_limit - drawn_count, 0)
        draw_count = int(min(3, remaining_draws))

        if draw_count == 0:
            return []

        drawn_cards = self.cog.draw_cards(draw_count)
        for cat, name in drawn_cards:
            self.cog.add_card_to_user(self.user.id, cat, name)

        return drawn_cards


    @discord.ui.button(label="Galerie", style=discord.ButtonStyle.secondary)
    async def show_gallery(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        embeds = self.cog.generate_gallery_embeds(self.user)
        if not embeds:
            await interaction.followup.send("Vous n'avez aucune carte pour le moment.", ephemeral=True)
            return

        embed_normales, embed_full = embeds
        view = GalleryActionView(self.cog, self.user)
        await interaction.followup.send(
            embeds=[embed_normales, embed_full],
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Classement", style=discord.ButtonStyle.secondary)
    async def show_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        leaderboard = self.cog.get_leaderboard()
        embed = discord.Embed(title="Top 5 des collectionneurs", color=0x4E5D94)
        for idx, (uid, count) in enumerate(leaderboard, start=1):
            user = self.cog.bot.get_user(uid)
            name = user.display_name if user else str(uid)
            embed.add_field(name=f"#{idx} {name}", value=f"{count} cartes différentes", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Echanger", style=discord.ButtonStyle.success)
    async def trade_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Afficher les instructions et les options d'échange
        embed = discord.Embed(
            title="🔄 Système d'Échange",
            description=(
                "**Bienvenue dans le système d'échange de cartes !**\n\n"
                "**📦 Déposer carte :** Stockez vos cartes dans votre coffre personnel pour les échanger\n"
                "**🤝 Initier échange :** Commencez un échange avec un autre joueur\n\n"
                "**Comment ça marche :**\n"
                "1. Déposez les cartes que vous voulez échanger dans votre coffre (vous et l'autre joueur)\n"
                "2. Initiez un échange avec un autre joueur\n"
                "3. Les deux joueurs voient les cartes disponibles et confirment l'échange\n"
                "4. Les cartes sont automatiquement transférées après confirmation mutuelle"
            ),
            color=0x00ff00
        )

        view = TradeMenuView(self.cog, self.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class TradeMenuView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user

    @discord.ui.button(label="📦 Déposer carte", style=discord.ButtonStyle.primary)
    async def deposit_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.send_modal(DepositCardModal(self.cog, self.user))

    @discord.ui.button(label="🤝 Initier échange", style=discord.ButtonStyle.secondary)
    async def initiate_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.send_modal(InitiateTradeModal(self.cog, self.user))

    @discord.ui.button(label="👀 Voir mon coffre", style=discord.ButtonStyle.secondary)
    async def view_vault(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        vault_cards = self.cog.get_user_vault_cards(self.user.id)
        if not vault_cards:
            await interaction.followup.send("📦 Votre coffre est vide.", ephemeral=True)
            return

        # Grouper les cartes par catégorie et compter
        cards_by_cat = {}
        for cat, name in vault_cards:
            cards_by_cat.setdefault(cat, []).append(name)

        embed = discord.Embed(
            title=f"📦 Coffre de {self.user.display_name}",
            color=0x4E5D94
        )

        for cat, names in cards_by_cat.items():
            counts = {}
            for name in names:
                counts[name] = counts.get(name, 0) + 1

            lines = [
                f"- **{name.removesuffix('.png')}**{' (x'+str(count)+')' if count > 1 else ''}"
                for name, count in counts.items()
            ]

            embed.add_field(
                name=f"{cat} ({len(names)} cartes)",
                value="\n".join(lines) if lines else "Aucune carte",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔄 Retirer cartes du coffre", style=discord.ButtonStyle.danger)
    async def withdraw_vault_cards(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        vault_cards = self.cog.get_user_vault_cards(self.user.id)
        if not vault_cards:
            await interaction.followup.send("📦 Votre coffre est vide. Aucune carte à retirer.", ephemeral=True)
            return

        # Filtrer les cartes Full et obtenir les cartes uniques échangeables
        exchangeable_cards = [(cat, name) for cat, name in vault_cards
                             if not name.removesuffix('.png').endswith(' (Full)')]
        full_cards = [(cat, name) for cat, name in vault_cards
                     if name.removesuffix('.png').endswith(' (Full)')]

        unique_exchangeable_cards = list({(cat, name) for cat, name in exchangeable_cards})

        # Compter le nombre total de cartes échangeables
        total_exchangeable = len(exchangeable_cards)
        unique_exchangeable_count = len(unique_exchangeable_cards)
        full_cards_count = len(full_cards)

        # Vérifier s'il y a des cartes échangeables
        if not exchangeable_cards:
            if full_cards:
                await interaction.followup.send(
                    f"📦 Votre coffre ne contient que **{full_cards_count} carte(s) Full** qui ne peuvent pas être retirées car elles ne sont pas échangeables.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("📦 Votre coffre est vide. Aucune carte à retirer.", ephemeral=True)
            return

        # Créer un embed de confirmation
        description = f"Vous êtes sur le point de retirer **{total_exchangeable} cartes** ({unique_exchangeable_count} uniques) de votre coffre vers votre inventaire principal."
        if full_cards_count > 0:
            description += f"\n\n⚠️ **{full_cards_count} carte(s) Full** resteront dans le coffre car elles ne sont pas échangeables."

        embed = discord.Embed(
            title="⚠️ Confirmation de retrait",
            description=description,
            color=0xff9900
        )

        # Afficher un aperçu des cartes échangeables uniquement
        cards_by_cat = {}
        for cat, name in exchangeable_cards:
            cards_by_cat.setdefault(cat, []).append(name)

        for cat, names in list(cards_by_cat.items())[:3]:  # Limiter à 3 catégories pour l'aperçu
            counts = {}
            for name in names:
                counts[name] = counts.get(name, 0) + 1

            lines = [
                f"- **{name.removesuffix('.png')}**{' (x'+str(count)+')' if count > 1 else ''}"
                for name, count in list(counts.items())[:3]  # Limiter à 3 cartes par catégorie
            ]

            if len(counts) > 3:
                lines.append(f"... et {len(counts) - 3} autres cartes")

            embed.add_field(
                name=f"{cat} ({len(names)} cartes)",
                value="\n".join(lines),
                inline=False
            )

        if len(cards_by_cat) > 3:
            embed.add_field(
                name="...",
                value=f"Et {len(cards_by_cat) - 3} autres catégories",
                inline=False
            )

        embed.add_field(
            name="⚠️ Attention",
            value="Cette action retirera **TOUTES** vos cartes du coffre et les remettra dans votre inventaire principal.",
            inline=False
        )

        view = WithdrawVaultConfirmationView(self.cog, self.user, unique_exchangeable_cards)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)



class WithdrawVaultConfirmationView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User, unique_vault_cards: list[tuple[str, str]]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.unique_vault_cards = unique_vault_cards

    @discord.ui.button(label="✅ Confirmer le retrait", style=discord.ButtonStyle.success)
    async def confirm_withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Récupérer toutes les cartes du coffre (avec duplicatas)
        vault_cards = self.cog.get_user_vault_cards(self.user.id)
        if not vault_cards:
            await interaction.followup.send("📦 Votre coffre est maintenant vide.", ephemeral=True)
            return

        # Filtrer les cartes Full (non échangeables) et compter les cartes par type
        card_counts = {}
        full_cards_found = []

        for cat, name in vault_cards:
            # Vérifier si c'est une carte Full
            if name.removesuffix('.png').endswith(' (Full)'):
                full_cards_found.append((cat, name))
                continue  # Ignorer les cartes Full

            key = (cat, name)
            card_counts[key] = card_counts.get(key, 0) + 1

        # Si seules des cartes Full sont présentes
        if not card_counts and full_cards_found:
            await interaction.followup.send(
                "📦 Votre coffre ne contient que des cartes **Full** qui ne peuvent pas être retirées car elles ne sont pas échangeables.",
                ephemeral=True
            )
            return

        # Si des cartes Full sont présentes avec d'autres cartes, informer l'utilisateur
        if full_cards_found:
            full_count = len(full_cards_found)
            await interaction.followup.send(
                f"ℹ️ **{full_count} carte(s) Full** resteront dans le coffre car elles ne sont pas échangeables. "
                f"Seules les cartes normales seront retirées.",
                ephemeral=True
            )

        # Listes pour le rollback en cas d'erreur
        removed_cards = []
        failed_additions = []

        try:
            # Étape 1: Retirer toutes les cartes du coffre
            for (cat, name), count in card_counts.items():
                for _ in range(count):
                    if self.cog.remove_card_from_vault(self.user.id, cat, name):
                        removed_cards.append((cat, name))
                    else:
                        # Rollback: remettre les cartes déjà retirées
                        for rollback_cat, rollback_name in removed_cards:
                            self.cog.add_card_to_vault(self.user.id, rollback_cat, rollback_name)
                        await interaction.followup.send(
                            "❌ Erreur lors du retrait des cartes du coffre. Aucune modification n'a été apportée.",
                            ephemeral=True
                        )
                        return

            # Étape 2: Ajouter toutes les cartes à l'inventaire principal
            for cat, name in removed_cards:
                if not self.cog.add_card_to_user(self.user.id, cat, name):
                    failed_additions.append((cat, name))

            # Si certaines additions ont échoué, rollback partiel
            if failed_additions:
                # Remettre les cartes qui n'ont pas pu être ajoutées dans le coffre
                for cat, name in failed_additions:
                    self.cog.add_card_to_vault(self.user.id, cat, name)

                successful_transfers = len(removed_cards) - len(failed_additions)
                await interaction.followup.send(
                    f"⚠️ Retrait partiellement réussi. {successful_transfers} cartes ont été transférées vers votre inventaire. "
                    f"{len(failed_additions)} cartes sont restées dans le coffre en raison d'erreurs.",
                    ephemeral=True
                )
                return

            # Succès complet
            total_transferred = len(removed_cards)
            unique_transferred = len(set(removed_cards))

            embed = discord.Embed(
                title="✅ Retrait réussi !",
                description=f"**{total_transferred} cartes** ({unique_transferred} uniques) ont été transférées de votre coffre vers votre inventaire principal.",
                color=0x00ff00
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Erreur lors du retrait des cartes du coffre: {e}")
            # Rollback complet en cas d'erreur inattendue
            for cat, name in removed_cards:
                self.cog.add_card_to_vault(self.user.id, cat, name)
            await interaction.followup.send(
                "❌ Une erreur inattendue s'est produite. Aucune modification n'a été apportée.",
                ephemeral=True
            )

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.send_message("❌ Retrait annulé.", ephemeral=True)

        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True


class DepositCardModal(discord.ui.Modal, title="Déposer une carte"):
    card_name = discord.ui.TextInput(
        label="Nom exact de la carte à déposer",
        placeholder="Ex : Dorian (Variante)",
        required=True
    )

    def __init__(self, cog: Cards, user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        # Répondre immédiatement pour éviter l'expiration de l'interaction
        await interaction.response.defer(ephemeral=True)

        try:
            input_name = self.card_name.value.strip()
            if not input_name.lower().endswith(".png"):
                input_name += ".png"

            # Vérifier que l'utilisateur possède cette carte
            normalized = self.cog.normalize_name(input_name.removesuffix(".png"))
            owned = self.cog.get_user_cards(self.user.id)

            match = next(
                ((cat, name) for cat, name in owned
                 if self.cog.normalize_name(name.removesuffix(".png")) == normalized),
                None
            )

            if not match:
                await interaction.followup.send(
                    "🚫 Vous ne possédez pas cette carte dans votre inventaire.", ephemeral=True
                )
                return

            cat, name = match

            # Vérifier que ce n'est pas une carte Full (non échangeable)
            if name.removesuffix('.png').endswith(' (Full)'):
                await interaction.followup.send(
                    "🚫 Les cartes **Full** ne peuvent pas être déposées dans le coffre car elles ne sont pas échangeables.",
                    ephemeral=True
                )
                return

            # Retirer la carte de l'inventaire principal
            remove_success = self.cog.remove_card_from_user(self.user.id, cat, name)
            if not remove_success:
                await interaction.followup.send(
                    "❌ Erreur lors du retrait de la carte de votre inventaire.", ephemeral=True
                )
                return

            # Ajouter la carte au vault (skip_possession_check=True car la carte vient d'être retirée)
            add_success = self.cog.add_card_to_vault(self.user.id, cat, name, skip_possession_check=True)
            if not add_success:
                # Rollback: remettre la carte dans l'inventaire
                self.cog.add_card_to_user(self.user.id, cat, name)
                await interaction.followup.send(
                    "❌ Erreur lors du dépôt de la carte dans le coffre.", ephemeral=True
                )
                return

            # Succès - envoyer le message de confirmation
            await interaction.followup.send(
                f"✅ **{name.removesuffix('.png')}** (*{cat}*) a été déposée dans votre coffre !",
                ephemeral=True
            )

        except Exception as e:
            logging.error(f"Erreur dans DepositCardModal.on_submit: {e}")
            try:
                await interaction.followup.send(
                    "❌ Une erreur inattendue s'est produite. Veuillez réessayer.", ephemeral=True
                )
            except Exception as followup_error:
                logging.error(f"Erreur lors du followup: {followup_error}")
                # En dernier recours, ne pas faire planter le bot


class InitiateTradeModal(discord.ui.Modal, title="Initier un échange"):
    target_user = discord.ui.TextInput(
        label="Nom d'utilisateur ou ID Discord",
        placeholder="Ex : @username ou 123456789012345678",
        required=True
    )

    def __init__(self, cog: Cards, user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        target_input = self.target_user.value.strip()

        # Essayer de trouver l'utilisateur
        target_user = None

        # Si c'est un ID numérique
        if target_input.isdigit():
            target_user = self.cog.bot.get_user(int(target_input))

        # Si c'est une mention (@username)
        elif target_input.startswith('@'):
            username = target_input[1:]
            for member in interaction.guild.members:
                if member.name.lower() == username.lower() or member.display_name.lower() == username.lower():
                    target_user = member
                    break

        # Recherche par nom d'utilisateur
        else:
            for member in interaction.guild.members:
                if member.name.lower() == target_input.lower() or member.display_name.lower() == target_input.lower():
                    target_user = member
                    break

        if not target_user:
            await interaction.response.send_message(
                "❌ Utilisateur introuvable. Vérifiez le nom d'utilisateur ou l'ID Discord.",
                ephemeral=True
            )
            return

        if target_user.id == self.user.id:
            await interaction.response.send_message(
                "🚫 Vous ne pouvez pas échanger avec vous-même.",
                ephemeral=True
            )
            return

        # Vérifier que l'utilisateur a des cartes dans son vault
        my_vault_cards = self.cog.get_user_vault_cards(self.user.id)
        if not my_vault_cards:
            await interaction.response.send_message(
                "📦 Votre coffre est vide. Déposez d'abord des cartes avant d'initier un échange.",
                ephemeral=True
            )
            return

        # Vérifier que la cible a des cartes dans son vault
        target_vault_cards = self.cog.get_user_vault_cards(target_user.id)
        if not target_vault_cards:
            await interaction.response.send_message(
                f"📦 Le coffre de {target_user.display_name} est vide. Ils doivent d'abord déposer des cartes.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Créer l'embed de proposition d'échange
        embed = discord.Embed(
            title="🤝 Proposition d'échange",
            description=f"{self.user.mention} souhaite initier un échange avec {target_user.mention}",
            color=0x00ff00
        )

        # Afficher les cartes disponibles des deux côtés
        my_unique_cards = list({(cat, name) for cat, name in my_vault_cards})
        target_unique_cards = list({(cat, name) for cat, name in target_vault_cards})

        my_cards_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in my_unique_cards[:10]])
        if len(my_unique_cards) > 10:
            my_cards_text += f"\n... et {len(my_unique_cards) - 10} autres cartes"

        target_cards_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in target_unique_cards[:10]])
        if len(target_unique_cards) > 10:
            target_cards_text += f"\n... et {len(target_unique_cards) - 10} autres cartes"

        embed.add_field(
            name=f"📦 Cartes de {self.user.display_name}",
            value=my_cards_text,
            inline=True
        )
        embed.add_field(
            name=f"📦 Cartes de {target_user.display_name}",
            value=target_cards_text,
            inline=True
        )

        view = TradeRequestView(self.cog, self.user, target_user)

        try:
            await target_user.send(embed=embed, view=view)
            await interaction.followup.send(
                f"📨 Proposition d'échange envoyée à {target_user.display_name} en message privé !",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(embed=embed, view=view)
            await interaction.followup.send(
                f"{target_user.mention} - Vous avez reçu une proposition d'échange !",
                ephemeral=False
            )


class TradeRequestView(discord.ui.View):
    def __init__(self, cog: Cards, initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)  # 5 minutes
        self.cog = cog
        self.initiator = initiator
        self.target = target

    @discord.ui.button(label="✅ Accepter l'échange", style=discord.ButtonStyle.success)
    async def accept_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Vérifier que les deux utilisateurs ont encore des cartes dans leur vault
        initiator_vault = self.cog.get_user_vault_cards(self.initiator.id)
        target_vault = self.cog.get_user_vault_cards(self.target.id)

        if not initiator_vault:
            await interaction.followup.send(
                f"❌ {self.initiator.display_name} n'a plus de cartes dans son coffre.", ephemeral=True
            )
            return

        if not target_vault:
            await interaction.followup.send(
                "❌ Vous n'avez plus de cartes dans votre coffre.", ephemeral=True
            )
            return

        # Créer la vue de confirmation d'échange complet
        view = FullVaultTradeConfirmationView(self.cog, self.initiator, self.target)

        # Utiliser l'embed unifié pour la confirmation
        embed = self.cog._create_unified_trade_confirmation_embed(
            self.initiator, self.target, initiator_vault, target_vault,
            f"**{self.target.display_name}**, voulez-vous échanger TOUT le contenu de votre coffre avec **{self.initiator.display_name}** ?"
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="❌ Refuser l'échange", style=discord.ButtonStyle.danger)
    async def decline_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True
            )
            return

        await interaction.response.send_message("❌ Échange refusé.", ephemeral=True)

        try:
            await self.initiator.send(
                f"**{self.target.display_name}** a refusé votre proposition d'échange."
            )
        except discord.Forbidden:
            pass

        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True


class FullVaultTradeConfirmationView(discord.ui.View):
    def __init__(self, cog: Cards, initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.initiator = initiator
        self.target = target
        self.initiator_confirmed = False
        self.target_confirmed = False

    @discord.ui.button(label="✅ Confirmer l'échange complet", style=discord.ButtonStyle.success)
    async def confirm_full_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True
            )
            return

        # Éviter les clics multiples
        if self.target_confirmed:
            await interaction.response.send_message(
                "⚠️ Vous avez déjà confirmé cet échange.", ephemeral=True
            )
            return

        self.target_confirmed = True

        # Désactiver les boutons immédiatement
        for child in self.children:
            child.disabled = True

        await interaction.response.send_message(
            "✅ Vous avez accepté l'échange complet. En attente de la confirmation de l'initiateur.",
            ephemeral=True
        )

        # Notifier l'initiateur et lui demander confirmation
        try:
            # Récupérer les cartes des deux coffres pour l'affichage
            initiator_vault_cards = self.cog.get_user_vault_cards(self.initiator.id)
            target_vault_cards = self.cog.get_user_vault_cards(self.target.id)

            # Utiliser l'embed unifié avec un message personnalisé pour l'initiateur
            embed = self.cog._create_unified_trade_confirmation_embed(
                self.initiator, self.target, initiator_vault_cards, target_vault_cards,
                f"**{self.target.display_name}** a accepté l'échange complet !\n\n**Confirmez-vous cet échange ?**"
            )
            # Changer la couleur pour indiquer que c'est une confirmation finale
            embed.color = 0x00ff00
            embed.title = "🔔 Confirmation finale requise"

            view = InitiatorFinalConfirmationView(self.cog, self.initiator, self.target)
            await self.initiator.send(embed=embed, view=view)

            # Feedback supplémentaire pour confirmer que le DM a été envoyé
            await interaction.followup.send(
                f"📨 Demande de confirmation finale envoyée à {self.initiator.display_name} en message privé.",
                ephemeral=True
            )

        except discord.Forbidden:
            # Si impossible d'envoyer en DM, créer un message public avec embed unifié
            initiator_vault_cards = self.cog.get_user_vault_cards(self.initiator.id)
            target_vault_cards = self.cog.get_user_vault_cards(self.target.id)

            embed = self.cog._create_unified_trade_confirmation_embed(
                self.initiator, self.target, initiator_vault_cards, target_vault_cards,
                f"{self.initiator.mention}, **{self.target.display_name}** a accepté l'échange complet !\n\n**Confirmez-vous cet échange ?**"
            )
            embed.color = 0x00ff00
            embed.title = "🔔 Confirmation finale requise"

            view = InitiatorFinalConfirmationView(self.cog, self.initiator, self.target)
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    @discord.ui.button(label="❌ Refuser l'échange", style=discord.ButtonStyle.danger)
    async def decline_full_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True
            )
            return

        # Éviter les clics multiples sur refuser aussi
        if self.target_confirmed:
            await interaction.response.send_message(
                "⚠️ Vous avez déjà traité cette proposition.", ephemeral=True
            )
            return

        self.target_confirmed = True  # Marquer comme traité

        # Désactiver tous les boutons immédiatement
        for child in self.children:
            child.disabled = True

        await interaction.response.send_message("❌ Échange refusé.", ephemeral=True)

        try:
            await self.initiator.send(
                f"**{self.target.display_name}** a refusé votre proposition d'échange complet."
            )
        except discord.Forbidden:
            pass


class InitiatorFinalConfirmationView(discord.ui.View):
    def __init__(self, cog: Cards, initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.initiator = initiator
        self.target = target
        self.trade_executed = False  # Flag pour éviter les exécutions multiples

    @discord.ui.button(label="✅ Confirmer l'échange complet", style=discord.ButtonStyle.success)
    async def confirm_final_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.initiator.id:
            await interaction.response.send_message(
                "Vous n'êtes pas l'initiateur de cet échange.", ephemeral=True
            )
            return

        # Éviter les exécutions multiples - vérifier ET définir atomiquement
        if self.trade_executed:
            await interaction.response.send_message(
                "⚠️ Cet échange a déjà été traité.", ephemeral=True
            )
            return

        # Répondre IMMÉDIATEMENT à l'interaction pour donner un feedback instantané
        await interaction.response.send_message(
            "⏳ Traitement de l'échange en cours...", ephemeral=True
        )

        # Marquer comme en cours de traitement APRÈS avoir répondu
        self.trade_executed = True

        # Désactiver tous les boutons IMMÉDIATEMENT
        for child in self.children:
            child.disabled = True

        # Exécuter l'échange complet des coffres
        success = await self.execute_full_vault_trade(interaction)

        # Mettre à jour le message de statut selon le résultat
        if success:
            await interaction.edit_original_response(content="✅ Échange terminé avec succès !")
        else:
            await interaction.edit_original_response(content="❌ Échec de l'échange.")
            # Réactiver les boutons en cas d'échec pour permettre une nouvelle tentative
            self.trade_executed = False
            for child in self.children:
                child.disabled = False

    @discord.ui.button(label="❌ Annuler l'échange", style=discord.ButtonStyle.danger)
    async def cancel_final_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.initiator.id:
            await interaction.response.send_message(
                "Vous n'êtes pas l'initiateur de cet échange.", ephemeral=True
            )
            return

        # Éviter les clics multiples sur annuler aussi
        if self.trade_executed:
            await interaction.response.send_message(
                "⚠️ Cet échange a déjà été traité.", ephemeral=True
            )
            return

        self.trade_executed = True

        # Désactiver tous les boutons immédiatement
        for child in self.children:
            child.disabled = True

        await interaction.response.send_message("❌ Échange annulé.", ephemeral=True)

        try:
            await self.target.send(
                f"**{self.initiator.display_name}** a annulé l'échange complet."
            )
        except discord.Forbidden:
            pass

    async def execute_full_vault_trade(self, interaction: discord.Interaction) -> bool:
        """Exécute l'échange complet des coffres entre les deux utilisateurs."""
        try:
            # Récupérer les cartes des deux coffres
            initiator_vault_cards = self.cog.get_user_vault_cards(self.initiator.id)
            target_vault_cards = self.cog.get_user_vault_cards(self.target.id)

            if not initiator_vault_cards or not target_vault_cards:
                await interaction.followup.send(
                    "❌ Un des coffres est vide. L'échange ne peut pas avoir lieu.",
                    ephemeral=True
                )
                return False

            # Étape 1: Retirer toutes les cartes des coffres
            initiator_removed_cards = []
            target_removed_cards = []

            # Retirer les cartes uniques du coffre de l'initiateur
            for cat, name in set(initiator_vault_cards):
                if self.cog.remove_card_from_vault(self.initiator.id, cat, name):
                    initiator_removed_cards.append((cat, name))
                else:
                    # Rollback en cas d'échec
                    for rollback_cat, rollback_name in initiator_removed_cards:
                        self.cog.add_card_to_vault(self.initiator.id, rollback_cat, rollback_name)
                    return False

            # Retirer les cartes uniques du coffre de la cible
            for cat, name in set(target_vault_cards):
                if self.cog.remove_card_from_vault(self.target.id, cat, name):
                    target_removed_cards.append((cat, name))
                else:
                    # Rollback complet en cas d'échec
                    for rollback_cat, rollback_name in initiator_removed_cards:
                        self.cog.add_card_to_vault(self.initiator.id, rollback_cat, rollback_name)
                    for rollback_cat, rollback_name in target_removed_cards:
                        self.cog.add_card_to_vault(self.target.id, rollback_cat, rollback_name)
                    return False

            # Étape 2: Ajouter les cartes aux inventaires principaux
            # Ajouter les cartes de la cible à l'inventaire de l'initiateur
            for cat, name in target_removed_cards:
                if not self.cog.add_card_to_user(self.initiator.id, cat, name):
                    # Rollback complet
                    await self.rollback_full_trade(initiator_removed_cards, target_removed_cards)
                    return False

            # Ajouter les cartes de l'initiateur à l'inventaire de la cible
            for cat, name in initiator_removed_cards:
                if not self.cog.add_card_to_user(self.target.id, cat, name):
                    # Rollback complet
                    await self.rollback_full_trade(initiator_removed_cards, target_removed_cards)
                    return False

            # Succès ! Notifier les deux utilisateurs avec un seul message public
            success_embed = discord.Embed(
                title="🎉 Échange complet réussi !",
                description=f"**{self.initiator.display_name}** et **{self.target.display_name}** ont échangé leurs coffres !",
                color=0x00ff00
            )

            success_embed.add_field(
                name=f"📤 {self.initiator.display_name} a donné",
                value=f"{len(initiator_removed_cards)} cartes uniques",
                inline=True
            )

            success_embed.add_field(
                name=f"📥 {self.target.display_name} a donné",
                value=f"{len(target_removed_cards)} cartes uniques",
                inline=True
            )

            # Un seul message public pour éviter les doublons
            await interaction.followup.send(embed=success_embed, ephemeral=False)

            # Messages privés simplifiés (optionnels)
            try:
                await self.initiator.send(
                    f"✅ Échange terminé ! Vous avez reçu {len(target_removed_cards)} cartes de {self.target.display_name}."
                )
            except discord.Forbidden:
                pass

            try:
                await self.target.send(
                    f"✅ Échange terminé ! Vous avez reçu {len(initiator_removed_cards)} cartes de {self.initiator.display_name}."
                )
            except discord.Forbidden:
                pass

            return True

        except Exception as e:
            logging.error(f"Erreur lors de l'échange complet: {e}")
            return False

    async def rollback_full_trade(self, initiator_cards, target_cards):
        """Rollback complet en cas d'échec de l'échange."""
        for cat, name in initiator_cards:
            self.cog.add_card_to_vault(self.initiator.id, cat, name)
        for cat, name in target_cards:
            self.cog.add_card_to_vault(self.target.id, cat, name)


# Les anciennes classes de sélection de cartes individuelles ont été supprimées
# Le nouveau système échange les coffres complets


class GalleryActionView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user

    @discord.ui.button(label="Afficher une carte", style=discord.ButtonStyle.primary)
    async def show_card_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.send_modal(CardNameModal(self.cog, self.user))


class CardNameModal(discord.ui.Modal, title="Afficher une carte"):
    card_name = discord.ui.TextInput(
        label="Nom exact de la carte (sans .png)",
        placeholder="Ex : Dorian (Variante)",
        required=True
    )

    def __init__(self, cog: Cards, user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        # 1) Préparation du nom de fichier
        input_name = self.card_name.value.strip()
        if not input_name.lower().endswith(".png"):
            input_name += ".png"

        # 2) Vérification de possession
        normalized = self.cog.normalize_name(input_name.removesuffix(".png"))
        owned = self.cog.get_user_cards(self.user.id)
        if not any(self.cog.normalize_name(n.removesuffix(".png")) == normalized for _, n in owned):
            return await interaction.response.send_message(
                "🚫 Vous ne possédez pas cette carte.", ephemeral=True
            )

        # 3) Recherche dans Drive
        result = self.cog.find_card_by_name(input_name)
        if not result:
            return await interaction.response.send_message(
                "❌ Image introuvable pour cette carte.", ephemeral=True
            )
        cat, name, file_id = result

        # 4) Téléchargement et création de l’embed
        file_bytes = self.cog.download_drive_file(file_id)
        embed, image_file = self.cog.build_card_embed(cat, name.removesuffix(".png"), file_bytes)

        # 5) ENVOI UNIQUE : embed + fichier ensemble
        await interaction.response.send_message(
            embed=embed,
            file=image_file,
            ephemeral=True
        )

class TradeOfferCardModal(discord.ui.Modal, title="Proposer un échange"):
    card_name = discord.ui.TextInput(label="Nom exact de la carte à échanger", placeholder="Ex : Alex (Variante)", required=True)

    def __init__(self, cog: Cards, user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        input_name = self.card_name.value.strip()
        normalized_input = self.cog.normalize_name(input_name.removesuffix(".png"))

        owned_cards = self.cog.get_user_cards(self.user.id)

        match = next(
            ((cat, name) for cat, name in owned_cards
             if self.cog.normalize_name(name.removesuffix(".png")) == normalized_input),
            None
        )

        if not match:
            await interaction.response.send_message("🚫 Vous ne possédez pas cette carte.", ephemeral=True)
            return

        offer_cat, offer_name = match

        await interaction.response.send_message(
            f"{interaction.user.mention} 🔁 Vous allez proposer un échange de la carte **{offer_name.removesuffix('.png')}** (*{offer_cat}*).\n"
            "Merci de **mentionner le joueur** avec qui vous voulez échanger dans **votre prochain message ici**.",
            ephemeral=False
        )

        def check(m):
            return (
                m.author.id == self.user.id
                and m.channel == interaction.channel
                and m.mentions
            )

        try:
            response_msg = await self.cog.bot.wait_for("message", check=check, timeout=60)
            target_user = response_msg.mentions[0]

            if target_user.id == self.user.id:
                await interaction.channel.send("🚫 Vous ne pouvez pas échanger avec vous-même.")
                return

            offer_embed = discord.Embed(
                title="Proposition d'échange",
                description=f"{self.user.mention} propose d'échanger sa carte **{offer_name}** *({offer_cat})* avec vous."
            )

            view = TradeConfirmView(self.cog, offerer=self.user, target=target_user, card_category=offer_cat, card_name=offer_name)

            try:
                await target_user.send(embed=offer_embed, view=view)
                await interaction.channel.send(f"📨 Proposition envoyée à {target_user.display_name} en message privé !")
            except discord.Forbidden:
                await interaction.channel.send(f"{target_user.mention}", embed=offer_embed, view=view)
                await interaction.channel.send("Le joueur ne peut pas être contacté en DM. L’échange est proposé ici.")

        except asyncio.TimeoutError:
            await interaction.channel.send("⏱ Temps écoulé. Aucun joueur mentionné, échange annulé.")


class TradeConfirmView(discord.ui.View):
    def __init__(self, cog: Cards, offerer: discord.User, target: discord.User, card_category: str, card_name: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.card_category = card_category
        self.card_name = card_name

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas l'utilisateur visé par cet échange.", ephemeral=True)
            return

        # Récupère les cartes du destinataire
        user_cards = self.cog.get_user_cards(self.target.id)
        unique_cards = list({(cat, name) for cat, name in user_cards})

        if not unique_cards:
            await interaction.response.send_message("❌ Vous n'avez aucune carte à proposer en retour.", ephemeral=True)
            return

        view = TradeRespondView(self.cog, self.offerer, self.target, self.card_category, self.card_name, unique_cards)
        await interaction.response.send_message("Sélectionnez une carte à offrir en retour :", view=view, ephemeral=True)

    

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True)
            return
        await interaction.response.send_message("❌ Échange refusé.")
        try:
            await self.offerer.send(f"**{self.target.display_name}** a refusé votre proposition d'échange pour la carte {self.card_name}.")
        except:
            pass
        for child in self.children:
            child.disabled = True

class TradeRespondView(discord.ui.View):
    def __init__(self, cog: Cards, offerer: discord.User, target: discord.User, offer_cat: str, offer_name: str, possible_cards: list[tuple[str, str]]):
        super().__init__(timeout=60)
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name
        self.selected_card = None
        self.choose_card_button = discord.ui.Button(label="Choisir une carte à échanger", style=discord.ButtonStyle.primary)
        self.choose_card_button.callback = self.choose_card
        self.add_item(self.choose_card_button)


    async def choose_card(self, interaction: discord.Interaction):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas autorisé à répondre à cet échangse.", ephemeral=True)
            return

        await interaction.response.send_modal(TradeResponseModal(self.cog, self.offerer, self.target, self.offer_cat, self.offer_name))


class TradeFinalConfirmView(discord.ui.View):
    def __init__(self, cog: Cards, offerer: discord.User, target: discord.User, offer_cat: str, offer_name: str, return_cat: str, return_name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name
        self.return_cat = return_cat
        self.return_name = return_name
        self.confirmed_by_offer = False
        self.confirmed_by_target = False

    @discord.ui.button(label="Confirmer (destinataire)", style=discord.ButtonStyle.success)
    async def confirm_target(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas le destinataire de l’échange.", ephemeral=True)
            return

        self.confirmed_by_target = True
        await interaction.response.send_message("✅ Vous avez confirmé l’échange. En attente de confirmation du proposeur.", ephemeral=True)

        if self.confirmed_by_offer:
            await self.finalize_exchange(interaction)

    @discord.ui.button(label="Confirmer (proposeur)", style=discord.ButtonStyle.success)
    async def confirm_offer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.offerer.id:
            await interaction.response.send_message("Vous n'êtes pas le proposeur de l’échange.", ephemeral=True)
            return

        self.confirmed_by_offer = True
        await interaction.response.send_message("✅ Vous avez confirmé l’échange. En attente de confirmation du destinataire.", ephemeral=True)

        if self.confirmed_by_target:
            await self.finalize_exchange(interaction)

    async def finalize_exchange(self, interaction: discord.Interaction):
        """Finalise l'échange entre les deux utilisateurs."""
        # Créer un état temporaire pour l'échange
        state = TradeExchangeState(
            cog=self.cog,
            offerer=self.offerer,
            target=self.target,
            offer_cat=self.offer_cat,
            offer_name=self.offer_name,
            return_cat=self.return_cat,
            return_name=self.return_name
        )

        state.completed = True
        success = state.cog.safe_exchange(
            state.offerer.id, (state.offer_cat, state.offer_name),
            state.target.id,  (state.return_cat,  state.return_name)
        )

        if success:
            # DM aux deux joueurs
            await state.offerer.send(
                f"📦 Échange confirmé ! Tu as donné **{state.offer_name}** et reçu **{state.return_name}**."
            )
            await state.target.send(
                f"📦 Échange confirmé ! Tu as donné **{state.return_name}** et reçu **{state.offer_name}**."
            )
            # → Annonce la carte reçue sur le mur public
            await state.cog._handle_announce_and_wall(
                interaction,
                [(state.return_cat, state.return_name)]
            )
            # Annonce également la carte reçue par l’autre joueur sur le mur public
            await state.cog._handle_announce_and_wall(
                interaction,
                [(state.offer_cat, state.offer_name)]
            )
            await state.cog.check_for_upgrades(interaction, state.offerer.id, [])
            await state.cog.check_for_upgrades(interaction, state.target.id, [])
        else:
            await state.offerer.send("❌ L’échange a échoué : une des cartes n’était plus disponible.")
            await state.target.send("❌ L’échange a échoué : une des cartes n’était plus disponible.")


class TradeResponseModal(discord.ui.Modal, title="Réponse à l’échange"):
    card_name = discord.ui.TextInput(
    label="Carte que vous proposez (sans .png)", 
    placeholder="Ex : Inès (Variante)", 
    required=True
)


    def __init__(self, cog: Cards, offerer: discord.User, target: discord.User, offer_cat: str, offer_name: str):
        super().__init__()
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name

    async def on_submit(self, interaction: discord.Interaction):
        input_name = self.card_name.value.strip()
        normalized_input = self.cog.normalize_name(input_name.removesuffix(".png"))

        owned_cards = self.cog.get_user_cards(interaction.user.id)
        match = next(
            ((cat, name) for cat, name in owned_cards
             if self.cog.normalize_name(name.removesuffix(".png")) == normalized_input),
            None
        )

        if not match:
            await interaction.response.send_message("🚫 Vous ne possédez pas cette carte.", ephemeral=True)
            return

        return_cat, return_name = match

        state = TradeExchangeState(
            cog=self.cog,
            offerer=self.offerer,
            target=self.target,
            offer_cat=self.offer_cat,
            offer_name=self.offer_name,
            return_cat=return_cat,
            return_name=return_name
        )

        # Message au destinataire (toi-même)
        await interaction.response.send_message(
            f"✅ Carte sélectionnée : **{return_name}** (*{return_cat}*)\n"
            f"**Vous devez confirmer l’échange.**",
            view=TradeConfirmTargetView(state),
            ephemeral=True
        )

        # Message au proposeur
        try:
            await self.offerer.send(
                f"💬 **{self.target.display_name}** souhaite échanger avec la carte **{return_name}** (*{return_cat}*).\n"
                f"Confirmez pour finaliser l’échange.",
                view=TradeConfirmOffererView(state)
            )
        except:
            logging.warning("[TRADE] Impossible d’envoyer un DM au proposeur.")



async def setup(bot):
    cards = Cards(bot)
    await bot.add_cog(cards)
    await bot.tree.sync()
    await cards.update_all_character_owners()



