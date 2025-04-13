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
import time
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

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

        # Map inverse pour retrouver catégorie par nom si besoin (en supposant noms uniques)
        # self.category_by_name = {file['name']: cat for cat, files in self.cards_by_category.items() for file in files}


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

        rows = self.cards_cache[1:] if self.cards_cache and not self.cards_cache[0][0].isdigit() else self.cards_cache
        user_cards = []
        for row in rows:
            if not row or len(row) < 3:
                continue
            uid_str, cat, name = row[0], row[1], row[2]
            try:
                uid = int(uid_str)
            except:
                continue
            if uid == user_id:
                user_cards.append((cat, name))
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


    
    def add_card_to_user(self, user_id: int, category: str, name: str):
        """Ajoute une carte pour un utilisateur dans la persistance."""
        try:
            self.sheet_cards.append_row([str(user_id), category, name])
        except Exception as e:
            logging.info(f"Erreur lors de l'ajout de la carte dans Google Sheets: {e}")

    def remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
        if not self.cards_cache or time.time() - self.cards_cache_time > 5:
            self.refresh_cards_cache()
        if not self.cards_cache:
            return False

        for i, row in enumerate(self.cards_cache):
            if len(row) < 3:
                continue
            uid_str, cat, card_name = row[0], row[1], row[2]
            if (
                uid_str == str(user_id)
                and cat == category
                and self.normalize_name(card_name.removesuffix(".png")) == self.normalize_name(name.removesuffix(".png"))
            ):
                try:
                    self.sheet_cards.delete_row(i + 1)  # +1 car gspread commence à 1
                    self.cards_cache = None  # Invalide le cache car la structure a changé
                    return True
                except Exception as e:
                    logging.error(f"[REMOVE] Échec suppression ligne {i+1}: {e}")
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

            drawn.append((cat, chosen_card["name"]))

        return drawn

    async def handle_lancement(self, interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)
        try:
            all_rows = self.sheet_lancement.get_all_values()
            if any(row and row[0] == user_id_str for row in all_rows):
                await interaction.response.send_message("🚫 Vous avez déjà utilisé votre tirage de lancement.", ephemeral=True)
                return
        except:
            pass

        try:
            self.sheet_lancement.append_row([user_id_str, interaction.user.display_name])
        except:
            await interaction.response.send_message("Erreur lors de l'enregistrement. Réessayez plus tard.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        view = CardsMenuView(self, interaction.user)
        drawn_cards = await view.perform_draw(interaction)

        logging.info(f"[DEBUG] Tirage obtenu : {drawn_cards}")
        await interaction.followup.send("🔍 Tirage en cours...", ephemeral=True)

        if not drawn_cards:
            await interaction.followup.send("Vous n’avez plus de tirages disponibles.", ephemeral=True)
            return

        embeds_and_files = []
        for cat, name in drawn_cards:
            logging.info(f"[DEBUG] Traitement de carte : {cat} | {name}")
            file_id = next((f['id'] for f in self.cards_by_category.get(cat, []) if f['name'] == name), None)
            if file_id:
                file_bytes = self.download_drive_file(file_id)
                safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                embed = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                embed.set_image(url=f"attachment://{safe_name}.png")
                embeds_and_files.append((embed, image_file))

        for embed, image_file in embeds_and_files:
            await interaction.followup.send(embed=embed, file=image_file, ephemeral=True)

        # Annonce publique si carte rare ou variante
        announce_channel = self.bot.get_channel(1360512727784882207)
        for cat, name in drawn_cards:
            if announce_channel and ("(Variante)" in name or cat in ["Secrète", "Fondateur", "Historique"]):
                clean_name = name.removesuffix(".png") if name.endswith(".png") else name
                await announce_channel.send(f"✨ **{interaction.user.display_name}** a obtenu une carte **{cat}** : **{clean_name}** !")


        # Mur public
        try:
            all_user_cards = self.sheet_cards.get_all_values()
            unique_drawn = set((row[1], row[2]) for row in all_user_cards if len(row) >= 3)
            total_cards = sum(len(lst) for lst in self.cards_by_category.values())
            discovered = len(unique_drawn)
            remaining = total_cards - discovered

            mur_channel = self.bot.get_channel(1360512727784882207)
            if mur_channel:
                for cat, name in drawn_cards:
                    try:
                        file_id = next((f['id'] for f in self.cards_by_category.get(cat, []) if f['name'] == name), None)
                        if file_id:
                            file_bytes = self.download_drive_file(file_id)
                            safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                            image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                            embed_card = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                            embed_card.set_image(url=f"attachment://{safe_name}.png")
                            embed_card.set_footer(text=f"Découverte par : {interaction.user.display_name}")
                            await mur_channel.send(embed=embed_card, file=image_file)

                    except Exception as e:
                        logging.error("Erreur envoi image mur (lancement):", e)

                # Supprimer ancien résumé
                async for msg in mur_channel.history(limit=20):
                    if msg.author == self.bot.user and msg.content.startswith("📝 Cartes découvertes :"):
                        await msg.delete()
                        break

                await mur_channel.send(
                    f"📝 Cartes découvertes : {discovered}/{total_cards} ({remaining} restantes)"
                )

        except Exception as e:
            logging.error("Erreur envoi mur tirages (lancement):", e)




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

        if not drawn_cards:
            await interaction.followup.send("🎖️ Vous n'avez plus assez de tirages disponibles (1 tirage requis, soit 3 cartes).", ephemeral=True)
            return

        # Générer les embeds
        embeds_and_files = []
        for cat, name in drawn_cards:
            logging.info(f"[DEBUG] Traitement de carte : {cat} | {name}")
            file_id = next((f['id'] for f in self.cog.cards_by_category.get(cat, []) if f['name'] == name), None)
            if file_id:
                file_bytes = self.cog.download_drive_file(file_id)
                safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                embed = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                embed.set_image(url=f"attachment://{safe_name}.png")
                embeds_and_files.append((embed, image_file))

        for embed, file in embeds_and_files:
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)

        # Annonce publique si carte rare ou variante
        announce_channel = self.cog.bot.get_channel(1360512727784882207)
        for cat, name in drawn_cards:
            if announce_channel and ("(Variante)" in name or cat in ["Fondateur", "Secrète", "Historique"]):
                clean_name = name[:-4] if name.endswith(".png") else name
                await announce_channel.send(f"✨ **{self.user.display_name}** a obtenu une carte **{cat}** : **{clean_name}** !")


        # Mur public
        try:
            all_user_cards = self.cog.sheet_cards.get_all_values()
            unique_drawn = set((row[1], row[2]) for row in all_user_cards if len(row) >= 3)
            total_cards = sum(len(lst) for lst in self.cog.cards_by_category.values())
            discovered = len(unique_drawn)
            remaining = total_cards - discovered

            mur_channel = self.cog.bot.get_channel(1360512727784882207)
            if mur_channel:
                for cat, name in drawn_cards:
                    try:
                        file_id = next((f['id'] for f in self.cog.cards_by_category.get(cat, []) if f['name'] == name), None)
                        if file_id:
                            file_bytes = self.cog.download_drive_file(file_id)
                            safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                            image_file = discord.File(io.BytesIO(file_bytes), filename=f"{safe_name}.png")
                            embed_card = discord.Embed(title=name, description=f"Catégorie : **{cat}**", color=0x4E5D94)
                            embed_card.set_image(url=f"attachment://{safe_name}.png")
                            embed_card.set_footer(text=f"Découverte par : {self.user.display_name}")
                            await mur_channel.send(embed=embed_card, file=image_file)

                    except Exception as e:
                        logging.error("Erreur envoi image mur :", e)

                # Supprimer ancien résumé
                async for msg in mur_channel.history(limit=20):
                    if msg.author == self.cog.bot.user and msg.content.startswith("📝 Cartes découvertes :"):
                        await msg.delete()
                        break

                await mur_channel.send(
                    f"📝 Cartes découvertes : {discovered}/{total_cards} ({remaining} restantes)"
                )

        except Exception as e:
            logging.error("Erreur envoi mur tirages:", e)


    async def perform_draw(self, interaction: discord.Interaction) -> list[tuple[str, str]]:
        """
        Tire jusqu'à 3 cartes pour l'utilisateur, met à jour les données,
        et retourne la liste des cartes tirées sous forme (catégorie, nom).
        à appeler depuis /lancement ou draw_card.
        """
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
        draw_count = min(3, remaining_draws)

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

        await interaction.response.defer(ephemeral=True)  # ✅ Correction ici

        user_cards = self.cog.get_user_cards(self.user.id)
        if not user_cards:
            await interaction.followup.send("Vous n'avez aucune carte pour le moment.", ephemeral=True)
            return

        # Trier les cartes par rareté selon l'ordre défini des catégories
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

        # Construire un embed listant les cartes par catégorie
        embed = discord.Embed(title=f"Galerie de {interaction.user.display_name}", color=0x4E5D94)
        cards_by_cat = {}
        for cat, name in user_cards:
            cards_by_cat.setdefault(cat, []).append(name)

        for cat in rarity_order:
            if cat in cards_by_cat:
                rarity_pct = {
                    "Secrète": "???",
                    "Fondateur": "1%",
                    "Historique": "2%",
                    "Maître": "4%",
                    "Black Hole": "6%",
                    "Architectes": "10%",
                    "Professeurs": "15%",
                    "Autre": "25%",
                    "Élèves": "37%",
                }
                card_list = cards_by_cat[cat]
                names_counts = {}
                for n in card_list:
                    names_counts[n] = names_counts.get(n, 0) + 1
                card_lines = []
                for n, count in names_counts.items():
                    clean_name = n.removesuffix(".png")
                    if count > 1:
                        card_lines.append(f"- **{clean_name}** (x{count})")
                    else:
                        card_lines.append(f"- **{clean_name}**")
                value = "\n".join(card_lines)
                embed.add_field(name=f"{cat} – {rarity_pct.get(cat, '')}", value=value, inline=False)

        view = GalleryActionView(self.cog, self.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


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
        safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
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


@app_commands.command(name="lancement", description="Tirage gratuit de bienvenue (une seule fois)")
async def lancement(interaction: discord.Interaction):
    cog: Cards = interaction.client.get_cog("Cards")
    if cog is None:
        await interaction.response.send_message("Erreur : cog introuvable.", ephemeral=True)
        return
    await cog.handle_lancement(interaction)



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

    @discord.ui.button(label="Confirmer l'échange", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas autorisé à confirmer cet échange.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        success = self.cog.safe_exchange(
            self.offerer.id, (self.offer_cat, self.offer_name),
            self.target.id, (self.return_cat, self.return_name)
        )

        if not success:
            await interaction.followup.send("❌ L’échange a échoué : une des cartes n’est plus disponible.", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Échange effectué : **{self.offer_name}** ↔ **{self.return_name}**",
            ephemeral=True
        )

        try:
            await self.offerer.send(
                f"📦 Échange réussi avec {self.target.display_name} : "
                f"tu as donné **{self.offer_name}** et reçu **{self.return_name}**."
            )
        except:
            pass

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

        confirm_view = TradeFinalConfirmView(
            cog=self.cog,
            offerer=self.offerer,
            target=self.target,
            offer_cat=self.offer_cat,
            offer_name=self.offer_name,
            return_cat=return_cat,
            return_name=return_name
        )

        await interaction.response.send_message(
            f"✅ Carte sélectionnée : **{return_name}** (*{return_cat}*)\n"
            f"**Vous avez 1 minute pour confirmer l’échange.**",
            view=confirm_view,
            ephemeral=True
        )

async def setup(bot):
    cards = Cards(bot)
    await bot.add_cog(cards)
    bot.tree.add_command(lancement)  # 👈 commande slash individuelle
    await bot.tree.sync()
    await cards.update_all_character_owners()



