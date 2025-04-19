## À implémenter : Système de tirage journalier

from discord import app_commands
from discord.ext import commands
import discord
import random
import os, json, io
import asyncio
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


class Cards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cards_cache = None  # Cache temporaire du contenu de sheet_cards
        self.cards_cache_time = 0
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
                results = self.drive_service.files().list(
                    q=f"'{folder_id}' in parents",
                    fields="files(id, name)"
                ).execute()
                files = results.get('files', [])
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
                 results = self.drive_service.files().list(
                     q=f"'{folder_id}' in parents",
                     fields="files(id, name)"
                 ).execute()
                 self.upgrade_cards_by_category[cat] = results.get('files', [])

    
    def sanitize_filename(self, name: str) -> str:
        """Nettoie le nom d'une carte pour une utilisation sûre dans les fichiers Discord."""
        return re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    def refresh_cards_cache(self):
        """Recharge le cache depuis Google Sheets (limité par minute)."""
        try:
            self.cards_cache = self.sheet_cards.get_all_values()
            self.cards_cache_time = time.time()
        except Exception as e:
            logging.error(f"[CACHE] Erreur de lecture Google Sheets : {e}")
            self.cards_cache = None
    
    def get_user_cards(self, user_id: int):
        """Récupère les cartes d’un utilisateur depuis le cache ou les données."""
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
                uid, count = cell.split(":")
                if int(uid) == user_id:
                    user_cards.extend([(cat, name)] * int(count))
        return user_cards

    
    def safe_exchange(self, user1_id, card1, user2_id, card2) -> bool:
        cards1 = self.get_user_cards(user1_id)
        cards2 = self.get_user_cards(user2_id)

        def contains_card(card_list, card):
            return any(
                cat == card[0] and self.normalize_name(name.removesuffix(".png")) == self.normalize_name(card[1].removesuffix(".png"))
                for cat, name in card_list
            )

        if not contains_card(cards1, card1) or not contains_card(cards2, card2):
            logging.warning(f"[SAFE_EXCHANGE] Échec : carte(s) non trouvée(s) - {card1=} {card2=}")
            return False

        success1 = self.remove_card_from_user(user1_id, card1[0], card1[1])
        success2 = self.remove_card_from_user(user2_id, card2[0], card2[1])

        if not (success1 and success2):
            logging.error(f"[SAFE_EXCHANGE] Suppression échouée - success1={success1}, success2={success2}")
            return False

        self.add_card_to_user(user1_id, card2[0], card2[1])
        self.add_card_to_user(user2_id, card1[0], card1[1])

        self.refresh_cards_cache()

        return True


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

        try:
            all_user_cards = self.sheet_cards.get_all_values()[1:]  # Skip header
            seen = set()
            for row in all_user_cards:
                if len(row) >= 2:
                    cat, name = row[0], row[1]
                    seen.add((cat, name))

            # Filtrer uniquement les cartes jamais vues avant (vraie découverte globale)
            new_draws = [card for card in drawn_cards if card not in seen]

            if not new_draws:
                return  # Rien de nouveau à annoncer

            for cat, name in new_draws:
                if announce_channel and ("(Variante)" in name or cat in ["Secrète", "Fondateur", "Historique"]):
                    clean_name = name.removesuffix(".png") if name.endswith(".png") else name
                    await announce_channel.send(f"✨ **{interaction.user.display_name}** a obtenu une carte **{cat}** : **{clean_name}** !")

                file_id = next((f['id'] for f in self.cards_by_category.get(cat, []) if f['name'].removesuffix(".png") == name), None)
                if file_id:
                    file_bytes = self.cog.download_drive_file(file_id)
                    safe_name = self.cog.sanitize_filename(name)
                    image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                    message = await announce_channel.send(file=image_file)

                    # Trouver la position globale de la carte dans l'ordre des découvertes
                    index = len(seen) + 1
                    embed_card = discord.Embed(
                        title=name.removesuffix(".png") if name.endswith(".png") else name,
                        description=f"Catégorie : **{cat}**",
                        color=0x4E5D94
                    )
                    embed_card.set_image(url=f"attachment://{safe_name}.png")
                    embed_card.set_footer(
                        text=f"Découverte par : {interaction.user.display_name}\n→ {index}{'ère' if index == 1 else 'ème'} carte découverte"
                    )

                    await message.edit(embed=embed_card)

            # Supprimer ancien message de progression
            async for msg in announce_channel.history(limit=20):
                if msg.author == self.bot.user and msg.content.startswith("📝 Cartes découvertes :"):
                    await msg.delete()
                    break

            total_cards = sum(len(lst) for lst in self.cards_by_category.values())
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

        await interaction.followup.send(
            f"**Menu des Cartes :**\n"
            f"🏅 Médailles comptées : **{medals_used}**\n"
            f"➕ Bonus de tirages : **{bonus_tirages}** (via personnages supplémentaires)\n"
            f"🎴 Tirages restants : **{remaining_clicks}**",
            view=view,
            ephemeral=True
        )


    async def handle_daily_draw(self, interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)
        paris_tz = pytz.timezone("Europe/Paris")
        today = datetime.now(paris_tz).strftime("%Y-%m-%d")

        try:
            all_rows = self.sheet_daily_draw.get_all_values()
            user_row = next((row for row in all_rows if row and row[0] == user_id_str), None)

            if user_row:
                row_index = all_rows.index(user_row) + 1
                last_draw_date = user_row[1] if len(user_row) > 1 else ""
                if last_draw_date == today:
                    await interaction.response.send_message("🚫 Vous avez déjà effectué votre tirage journalier aujourd'hui.", ephemeral=True)
                    return
                else:
                    # Met à jour la date dans la colonne B, même si elle était vide
                    self.sheet_daily_draw.update(f"B{row_index}", [[today]])
            else:
                # Ajoute une nouvelle ligne pour l'utilisateur
                self.sheet_daily_draw.append_row([user_id_str, today])

        except Exception as e:
            logging.error(f"[DAILY_DRAW] Erreur lecture/écriture feuille Tirages Journaliers : {e}")
            await interaction.response.send_message("Erreur de lecture Google Sheets. Réessayez plus tard.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        view = CardsMenuView(self, interaction.user)
        drawn_cards = await view.perform_draw(interaction)
        # Vérifier les doublons post‑tirage journalier
        await self.check_for_upgrades(interaction, interaction.user.id, drawn_cards)


        if not drawn_cards:
            await interaction.edit_original_response(content="Vous n’avez plus de tirages disponibles.")
            return

        embed_msgs = []
        for cat, name in drawn_cards:
            logging.info(f"[DEBUG] Traitement de carte : {cat} | {name}")
            file_id = next((f['id'] for f in self.cards_by_category.get(cat, []) if f['name'].removesuffix(".png") == name), None)
            if file_id:
                file_bytes = self.download_drive_file(file_id)
                safe_name = self.sanitize_filename(name)
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                embed = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                embed.set_image(url=f"attachment://{safe_name}.png")
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

    @app_commands.command(name="tirage_journalier", description="Effectuez votre tirage journalier (une fois par jour)")
    async def daily_draw(self, interaction: discord.Interaction):
        logging.info("[DEBUG] Commande /tirage_journalier déclenchée")
        await self.handle_daily_draw(interaction)

    
    def add_card_to_user(self, user_id: int, category: str, name: str):
        """Ajoute une carte pour un utilisateur dans la persistance."""
        try:
            rows = self.sheet_cards.get_all_values()
            for i, row in enumerate(rows):
                if len(row) < 2:
                    continue
                if row[0] == category and row[1] == name:
                    for j in range(2, len(row)):
                        if row[j].startswith(f"{user_id}:"):
                            uid, count = row[j].split(":")
                            row[j] = f"{uid}:{int(count) + 1}"
                            cleaned_row = [cell for cell in row if cell.strip() != ""]
                            self.sheet_cards.update(f"A{i+1}", [cleaned_row])
                            return
                    row.append(f"{user_id}:1")
                    cleaned_row = [cell for cell in row if cell.strip() != ""]
                    self.sheet_cards.update(f"A{i+1}", [cleaned_row])
                    return
            # Si la carte n'existe pas encore
            new_row = [category, name, f"{user_id}:1"]
            self.sheet_cards.append_row(new_row)
        except Exception as e:
            logging.error(f"Erreur lors de l'ajout de la carte dans Google Sheets: {e}")

    def remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
        """Supprime une carte pour un utilisateur dans la persistance."""
        try:
            rows = self.sheet_cards.get_all_values()
            for i, row in enumerate(rows):
                if len(row) < 2:
                    continue
                if row[0] == category and row[1] == name:
                    for j in range(2, len(row)):
                        if row[j].startswith(f"{user_id}:"):
                            uid, count = row[j].split(":")
                            if int(count) > 1:
                                row[j] = f"{uid}:{int(count) - 1}"
                            else:
                                row[j] = ""
                            cleaned_row = [cell for cell in row if cell.strip() != ""]
                            self.sheet_cards.update(f"A{i+1}", [cleaned_row])
                            return True
            return False
        except Exception as e:
            logging.error(f"Erreur lors de la suppression de la carte dans Google Sheets: {e}")
            return False

    def find_card_by_name(self, input_name: str) -> tuple[str, str, str] | None:
        """
        Recherche une carte par nom (tolérance accents, majuscules, .png) dans toutes les catégories.
        Retourne (catégorie, nom exact, file_id) ou None.
        """
        normalized_input = self.normalize_name(input_name.removesuffix(".png"))

        for cat, files in self.cards_by_category.items():
            for file in files:
                file_name = file["name"]
                normalized_file = self.normalize_name(file_name.removesuffix(".png"))
                if normalized_file == normalized_input:
                    return (cat, file_name, file["id"])
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
        Vérifie, pour chaque carte normale tirée, si l'utilisateur atteint le seuil
        de doublons. Si oui, remplace N cartes par la version Full et notifie.
        """
        for cat, name in set(drawn_cards):
            if cat in self.upgrade_thresholds:
                # compte combien il en possède
                normalized = self.normalize_name(name)
                user_cards = self.get_user_cards(user_id)
                count = sum(
                    1 for c,n in user_cards
                    if c == cat and self.normalize_name(n) == normalized
                )
                seuil = self.upgrade_thresholds[cat]
                if count >= seuil:
                    # 1) retirer les doublons
                    for _ in range(seuil):
                        self.remove_card_from_user(user_id, cat, name)
                    # 2) ajouter la Full
                    full_name = f"{name} (Full)"
                    self.add_card_to_user(user_id, cat, full_name)
                    # 3) récupérer le fichier Full
                    file_id = next(
                        f['id'] for f in self.upgrade_cards_by_category[cat]
                        if self.normalize_name(f['name'].removesuffix(".png"))
                           == self.normalize_name(full_name)
                    )
                    file_bytes = self.download_drive_file(file_id)
                    safe_name = self.sanitize_filename(full_name)
                    image_file = discord.File(
                        io.BytesIO(file_bytes),
                        filename=f"{safe_name}.png"
                    )
                    # 4) notifier l'utilisateur
                    embed = discord.Embed(
                        title=f"🎉 Carte Full obtenue : {full_name}",
                        description=(
                            f"Vous avez échangé **{seuil}× {name}** "
                            f"contre **{full_name}** !"
                        ),
                        color=discord.Color.gold()
                    )
                    embed.set_image(url=f"attachment://{safe_name}.png")
                    await interaction.followup.send(embed=embed, file=image_file)

    
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
                safe_name = self.sanitize_filename(name)
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                embed = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                embed.set_image(url=f"attachment://{safe_name}.png")
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
    
    @commands.command(name="refresh_mur")
    @commands.has_permissions(administrator=True)
    async def refresh_wall(self, ctx: commands.Context):
        """Nettoie et réaffiche toutes les cartes découvertes dans le salon du mur."""
        announce_channel = self.bot.get_channel(1360512727784882207)

        if not announce_channel:
            await ctx.send("Salon d’annonce introuvable.")
            return

        try:
            await ctx.send("🧼 Suppression du mur en cours...")

            def is_bot_message(m):
                return m.author == self.bot.user

            # 1. Purge rapide des messages récents
            deleted = await announce_channel.purge(limit=200, check=is_bot_message, bulk=True)
            await asyncio.sleep(1)

            # 2. Suppression manuelle des anciens messages (>14 jours)
            async for msg in announce_channel.history(limit=None, oldest_first=True):
                if msg.author == self.bot.user:
                    try:
                        await msg.delete()
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logging.warning(f"Erreur suppression message {msg.id}: {e}")

            # 3. Reconstruction du mur
            all_user_cards = self.sheet_cards.get_all_values()
            seen = set()
            unique_cards_ordered = []
            for row in all_user_cards:
                if len(row) >= 3:
                    key = (row[0].strip().lower(), row[1].strip().lower())
                    if key not in seen:
                        seen.add(key)
                        unique_cards_ordered.append((row[1], row[2]))

            for index, (cat, name) in enumerate(unique_cards_ordered, start=1):
                cat_clean, name_clean = cat.strip().lower(), name.strip().lower()
                file_id = next(
                    (f['id'] for f in self.cards_by_category.get(cat, []) if f['name'].strip().lower() == name_clean),
                    None
                )
                if file_id:
                    file_bytes = self.download_drive_file(file_id)
                    safe_name = self.sanitize_filename(name)
                    image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")

                    # 🎯 Récupérer le découvreur
                    discoverer_id = next(
                        (row[0] for row in all_user_cards if len(row) >= 3 and row[1].strip().lower() == cat_clean and row[2].strip().lower() == name_clean),
                        None
                    )
                    try:
                        discoverer_member = ctx.guild.get_member(int(discoverer_id)) if discoverer_id else None
                        if discoverer_member:
                            discoverer_name = discoverer_member.nick or discoverer_member.name
                        else:
                            discoverer_name = "?"
                    except:
                        discoverer_name = "?"

                    message = await announce_channel.send(file=image_file)

                    embed_card = discord.Embed(
                        title=name.removesuffix(".png") if name.endswith(".png") else name,
                        description=f"Catégorie : **{cat}**",
                        color=0x4E5D94
                    )
                    embed_card.set_image(url=f"attachment://{safe_name}.png")
                    embed_card.set_footer(
                        text=f"Découverte par : {discoverer_name}\n→ {index}{'ère' if index == 1 else 'ème'} carte découverte"
                    )

                    await message.edit(embed=embed_card)
                    await asyncio.sleep(0.5)

            # 4. Message de progression
            total_cards = sum(len(lst) for lst in self.cards_by_category.values())
            discovered = len(unique_cards_ordered)
            remaining = total_cards - discovered
            await announce_channel.send(
                f"📝 Cartes découvertes : {discovered}/{total_cards} ({remaining} restantes)"
            )

            await ctx.send("✅ Mur reconstruit avec succès.")

        except Exception as e:
            logging.error("Erreur lors de la reconstruction du mur :", e)
            await ctx.send("❌ Une erreur est survenue.")

class CardsMenuView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.user_id = user.id  # 👈 nécessaire pour les boutons comme Galerie


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
            file_id = next((f['id'] for f in self.cog.cards_by_category.get(cat, []) if f['name'].removesuffix(".png") == name), None)
            if file_id:
                file_bytes = self.cog.download_drive_file(file_id)
                safe_name  = self.cog.sanitize_filename(name)
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                embed = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                embed.set_image(url=f"attachment://{safe_name}.png")
                embeds_and_files.append((embed, image_file))

        for embed, file in embeds_and_files:
            await interaction.followup.send(embed=embed, file=file, ephemeral=False)

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

        # Récupération des cartes de l'utilisateur
        user_cards = self.cog.get_user_cards(self.user.id)
        if not user_cards:
            await interaction.followup.send("Vous n'avez aucune carte pour le moment.", ephemeral=True)
            return

        # Ordre des catégories
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

        # Constitution d'un dict {cat: [noms]}
        cards_by_cat: dict[str, list[str]] = {}
        for cat, name in user_cards:
            cards_by_cat.setdefault(cat, []).append(name)

        # Création des deux embeds
        embed_normales = discord.Embed(
            title=f"Galerie de {interaction.user.display_name}",
            color=discord.Color.blue()
        )
        embed_full = discord.Embed(
            title=f"Cartes Full de {interaction.user.display_name}",
            color=discord.Color.gold()
        )

        # Remplissage des embeds
        for cat in rarity_order:
            noms = cards_by_cat.get(cat, [])

            # 1) Cartes normales
            normales = [n for n in noms if not n.endswith(" (Full)")]
            if normales:
                counts: dict[str,int] = {}
                for n in normales:
                    counts[n] = counts.get(n, 0) + 1
                lines = [
                    f"- **{n.removesuffix('.png')}**{' (x'+str(c)+')' if c>1 else ''}"
                    for n, c in counts.items()
                ]
                embed_normales.add_field(name=cat, value="\n".join(lines), inline=False)

            # 2) Cartes Full
            fulls = [n for n in noms if n.endswith(" (Full)")]
            if fulls:
                counts: dict[str,int] = {}
                for n in fulls:
                    counts[n] = counts.get(n, 0) + 1
                lines = [
                    f"- **{n.removesuffix('.png')}**{' (x'+str(c)+')' if c>1 else ''}"
                    for n, c in counts.items()
                ]
                embed_full.add_field(name=f"{cat} (Full)", value="\n".join(lines), inline=False)

        # Envoi des deux embeds
        view = GalleryActionView(self.cog, self.user)
        await interaction.followup.send(
            embeds=[embed_normales, embed_full],
            view=view,
            ephemeral=True
        )



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
    
    @discord.ui.button(label="Proposer un échange", style=discord.ButtonStyle.success)
    async def offer_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Ce bouton ne vous est pas destiné.", ephemeral=True)
            return

        await interaction.response.send_modal(TradeOfferCardModal(self.cog, self.user))


class CardNameModal(discord.ui.Modal, title="Afficher une carte"):
    card_name = discord.ui.TextInput(label="Nom exact de la carte (sans .png)", placeholder="Ex : Dorian (Variante)", required=True)

    def __init__(self, cog: Cards, user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        input_name = self.card_name.value.strip()
        if not input_name.endswith(".png"):
            input_name += ".png"

        # Vérifie si l'utilisateur possède bien cette carte
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

                # Cherche l'image correspondante dans toutes les catégories
        result = self.cog.find_card_by_name(input_name)
        if not result:
            await interaction.response.send_message("❌ Image introuvable pour cette carte.", ephemeral=True)
            return

        cat, name, file_id = result
        file_bytes = self.cog.download_drive_file(file_id)
        safe_name = self.cog.sanitize_filename(name)
        image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")

        embed = discord.Embed(
            title=name,
            description=f"Catégorie : **{cat}**",
            color=0x4E5D94
        )
        embed.set_image(url=f"attachment://{safe_name}.png")

        await interaction.response.send_message(embed=embed, file=image_file, ephemeral=True)

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
        success = self.cog.safe_exchange(
            self.offerer.id, (self.offer_cat, self.offer_name),
            self.target.id, (self.return_cat, self.return_name)
        )

        if not success:
            await interaction.followup.send("❌ L’échange a échoué : une des cartes n’est plus disponible.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Échange effectué : **{self.offer_name}** ↔ **{self.return_name}**", ephemeral=True)

        try:
            await self.offerer.send(
                f"📦 Échange réussi avec {self.target.display_name} : "
                f"tu as donné **{self.offer_name}** et reçu **{self.return_name}**."
            )
        except:
            pass

        try:
            await self.target.send(
                f"📦 Échange réussi avec {self.offerer.display_name} : "
                f"tu as donné **{self.return_name}** et reçu **{self.offer_name}**."
            )
        except:
            pass

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)


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



