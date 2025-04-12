from discord import app_commands
from discord.ext import commands
import discord
import random
import os, json, io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread

class Cards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
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

    @app_commands.command(name="cartes", description="Gérer vos cartes à collectionner")
    async def cartes(self, interaction: discord.Interaction):
        """Commande principale /cartes : affiche le menu des cartes avec les trois options."""
        view = CardsMenuView(self, interaction.user)
        await interaction.response.send_message("**Menu des Cartes :**", view=view, ephemeral=True)

        # Ajout : Affichage du nombre de tirages restants
        user_cards = self.get_user_cards(interaction.user.id)
        drawn_count = len(user_cards)

        inventory_cog = interaction.client.get_cog("Inventory")
        total_medals = 0
        if inventory_cog:
            students = inventory_cog.load_students()
            for data in students.values():
                if data.get('user_id') == interaction.user.id:
                    total_medals += data.get('medals', 0)

        draw_limit = total_medals * 3
        remaining_draws = max(draw_limit - drawn_count, 0)

        await interaction.followup.send(f"🎴 Tirages restants : **{remaining_draws}**", ephemeral=True)


    def add_card_to_user(self, user_id: int, category: str, name: str):
        """Ajoute une carte pour un utilisateur dans la persistance."""
        try:
            self.sheet_cards.append_row([str(user_id), category, name])
        except Exception as e:
            print(f"Erreur lors de l'ajout de la carte dans Google Sheets: {e}")

    def remove_card_from_user(self, user_id: int, category: str, name: str):
        """Retire une carte (un exemplaire) d'un utilisateur."""
        try:
            cell_list = self.sheet_cards.findall(str(user_id))
            # findall retourne toutes les cellules correspondant à l'user_id
            for cell in cell_list:
                # Vérifier si la ligne correspond à la carte voulue
                row_values = self.sheet_cards.row_values(cell.row)
                if len(row_values) >= 3:
                    uid_str, cat, card_name = row_values[0], row_values[1], row_values[2]
                    if uid_str == str(user_id) and cat == category and card_name == name:
                        self.sheet_cards.delete_row(cell.row)
                        break
        except Exception as e:
            print(f"Erreur lors de la suppression de la carte: {e}")

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

class CardsMenuView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user

    @discord.ui.button(label="Tirer une carte", style=discord.ButtonStyle.primary)
    async def draw_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer()  # rendre la réponse publique

        # Calcul des tirages disponibles
        inventory_cog = interaction.client.get_cog("Inventory")
        total_medals = 0
        if inventory_cog:
            students = inventory_cog.load_students()
            for data in students.values():
                if data.get('user_id') == self.user.id:
                    total_medals += data.get('medals', 0)

        user_cards = self.cog.get_user_cards(self.user.id)
        drawn_count = len(user_cards)
        draw_limit = total_medals * 3
        if drawn_count + 3 > draw_limit:
            await interaction.followup.send("🎖️ Vous n'avez plus assez de tirages disponibles (3 requis).", ephemeral=True)
            return

        # Tirage des cartes
        categories = ["Secrète", "Fondateur", "Historique", "Maître", "Black Hole", "Architectes", "Professeurs", "Autre", "Élèves"]
        weights = [0.5, 1, 2, 4, 6, 10, 15, 25, 37]

        drawn_cards = []
        embeds_and_files = []

        for _ in range(3):
            category = random.choices(categories, weights=weights, k=1)[0]
            card_list = self.cog.cards_by_category.get(category, [])
            variant_cards = [f for f in card_list if "(Variante)" in f['name']]
            normal_cards = [f for f in card_list if "(Variante)" not in f['name']]
            card_file = random.choice(variant_cards if variant_cards and random.random() < 0.1 else normal_cards or card_list)

            card_name = card_file['name']
            self.cog.add_card_to_user(self.user.id, category, card_name)
            drawn_cards.append((category, card_name))

            try:
                file_bytes = self.cog.download_drive_file(card_file['id'])
                image_file = discord.File(io.BytesIO(file_bytes), filename=f"{card_name}.png")
                embed_card = discord.Embed(title=card_name, description=f"Catégorie : **{category}**", color=0x4E5D94)
                embed_card.set_image(url=f"attachment://{card_name}.png")
                embeds_and_files.append((embed_card, image_file))
            except Exception as e:
                print(f"Erreur image: {e}")

        # Envoi des cartes tirées une par une (embed + image)
        for embed, file in embeds_and_files:
            await interaction.followup.send(embed=embed, file=file)

        # Annonce publique si carte rare ou variante
        announce_channel = self.cog.bot.get_channel(1017906514838700032)
        for cat, name in drawn_cards:
            if announce_channel and ("(Variante)" in name or cat in ["Fondateur", "Maître", "Historique"]):
                await announce_channel.send(f"✨ **{self.user.display_name}** a obtenu une carte **{cat}** : **{name}** !")

        # Mur des cartes avec affichage visuel
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
                            image_file = discord.File(io.BytesIO(file_bytes), filename=f"{name}.png")
                            embed_card = discord.Embed(title=name, description=f"Carte **{cat}**")
                            embed_card.set_image(url=f"attachment://{name}.png")
                            await mur_channel.send(embed=embed_card, file=image_file)
                    except Exception as e:
                        print("Erreur envoi image mur :", e)

                # Message de progression général
                await mur_channel.send(
                    f"📝 Cartes découvertes : {discovered}/{total_cards} ({remaining} restantes)"
                )
        except Exception as e:
            print("Erreur envoi mur tirages:", e)



    @discord.ui.button(label="Galerie", style=discord.ButtonStyle.secondary)
    async def show_gallery(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        # Récupérer l'inventaire de cartes de l'utilisateur
        user_cards = self.cog.get_user_cards(self.user.id)
        if not user_cards:
            await interaction.response.send_message("Vous n'avez aucune carte pour le moment.", ephemeral=True)
            return

        # Trier les cartes par rareté selon l'ordre défini des catégories
        rarity_order = {
            "Secrète": 0,
            "Fondateur": 1,
            "Personnage Historique": 2,
            "Maître": 3,
            "Black Hole": 4,
            "Professeurs": 5,
            "Architectes": 6,
            "Autre": 7,
            "Élèves": 8,
        }
        user_cards.sort(key=lambda c: rarity_order.get(c[0], 9))

        # Construire un embed listant les cartes par catégorie
        embed = discord.Embed(title=f"Galerie de {interaction.user.display_name}", color=0x4E5D94)
        cards_by_cat = {}
        for cat, name in user_cards:
            cards_by_cat.setdefault(cat, []).append(name)
        for cat in ["Personnage Historique", "Fondateur", "Black Hole", "Maître", "Architectes", "Professeurs", "Autre", "Élèves", "Secrète"]:
            if cat in cards_by_cat:
                # Indiquer la rareté en pourcentage dans le titre du champ
                rarity_pct = {
                    "Secrète": "???",
                    "Fondateur": "1%",
                    "Personnage Historique": "2%",
                    "Maître": "4%",
                    "Black Hole": "6%",
                    "Architectes": "10%",
                    "Professeurs": "15%",
                    "Autre": "25%",
                    "Élèves": "37%",
                }
                card_list = cards_by_cat[cat]
                # Ajouter "(xN)" après le nom pour les doublons
                names_counts = {}
                for n in card_list:
                    names_counts[n] = names_counts.get(n, 0) + 1
                card_lines = []
                for n, count in names_counts.items():
                    if count > 1:
                        card_lines.append(f"- **{n}** (x{count})")
                    else:
                        card_lines.append(f"- **{n}**")
                value = "\n".join(card_lines)
                embed.add_field(name=f"{cat} – {rarity_pct.get(cat, '')}", value=value, inline=False)
        # Préparer une vue avec un Select pour choisir une carte à afficher
        view = GallerySelectView(self.cog, self.user.id, user_cards)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class GallerySelectView(discord.ui.View):
    def __init__(self, cog: Cards, user_id: int, cards_list: list):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        # Définir les options du sélecteur (une par carte unique)
        # On combine catégorie et nom dans la value pour identification
        unique_cards = []
        seen = set()
        for cat, name in cards_list:
            if (cat, name) not in seen:
                seen.add((cat, name))
                label = f"{name} ({cat})"
                unique_cards.append(discord.SelectOption(label=label, value=f"{cat}|{name}"))
        # Créer le menu déroulant
        self.select = discord.ui.Select(placeholder="Choisir une carte à afficher", options=unique_cards, min_values=1, max_values=1)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        # Quand l'utilisateur sélectionne une carte dans la galerie
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Cette sélection ne vous appartient pas.", ephemeral=True)
            return
        value = self.select.values[0]  # ex: "Fondateur|NomDeCarte"
        cat, name = value.split("|", 1)
        # Retrouver l'ID du fichier correspondant à cette carte
        file_id = None
        for f in self.cog.cards_by_category.get(cat, []):
            if f['name'] == name:
                file_id = f['id']
                break
        if not file_id:
            await interaction.response.send_message("Image introuvable pour cette carte.", ephemeral=True)
            return
        # Télécharger l'image et l'envoyer
        try:
            file_bytes = self.cog.download_drive_file(file_id)
            image_file = discord.File(io.BytesIO(file_bytes), filename=f"{name}.png")
            embed = discord.Embed(title=name, description=f"Carte **{cat}**")
            embed.set_image(url=f"attachment://{name}.png")
            await interaction.response.send_message(embed=embed, file=image_file, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Carte sélectionnée : **{name}** (catégorie {cat}). *Impossible de charger l'image.*", ephemeral=True)

    @discord.ui.button(label="Échanger", style=discord.ButtonStyle.success)
    async def trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas initier cet échange.", ephemeral=True)
            return
        # Récupérer les cartes de l'utilisateur initiateur
        user_cards = self.cog.get_user_cards(self.user.id)
        if not user_cards:
            await interaction.response.send_message("Vous n'avez aucune carte à échanger.", ephemeral=True)
            return
        # Envoyer un menu pour choisir la carte et le joueur cible (en éphemère)
        view = TradeInitiateView(self.cog, self.user)
        await interaction.response.send_message("Choisissez une carte et un joueur avec qui échanger :", view=view, ephemeral=True)

class TradeInitiateView(discord.ui.View):
    def __init__(self, cog: Cards, user: discord.User):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        # Sélecteur de carte (cartes de l'utilisateur initiateur)
        options = []
        user_cards = self.cog.get_user_cards(user.id)
        seen = set()
        for cat, name in user_cards:
            # ne lister chaque carte unique qu'une fois
            if (cat, name) not in seen:
                seen.add((cat, name))
                options.append(discord.SelectOption(label=f"{name} ({cat})", value=f"{cat}|{name}"))
        self.card_select = discord.ui.Select(placeholder="Votre carte à échanger", options=options, min_values=1, max_values=1)
        self.add_item(self.card_select)
        # Sélecteur d'utilisateur (choisir le partenaire d'échange)
        self.user_select = discord.ui.UserSelect(placeholder="Choisir un joueur", min_values=1, max_values=1)
        self.add_item(self.user_select)
        # Bouton de confirmation
        self.confirm = discord.ui.Button(label="Proposer l'échange", style=discord.ButtonStyle.primary)
        self.confirm.callback = self.confirm_callback
        self.add_item(self.confirm)

    async def confirm_callback(self, interaction: discord.Interaction):
        # Vérifier l'auteur
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Seul l'initiateur peut confirmer cet échange.", ephemeral=True)
            return
        # Obtenir la sélection de carte et d'utilisateur
        if not self.card_select.values or not self.user_select.values:
            await interaction.response.send_message("Veuillez sélectionner une carte **et** un joueur.", ephemeral=True)
            return
        target_user = self.user_select.values[0]
        cat, name = self.card_select.values[0].split("|", 1)
        # Vérifier que l'utilisateur cible est différent et qu'il possède au moins une carte (sinon échange inutile)
        if target_user.id == self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas échanger avec vous-même.", ephemeral=True)
            return
        target_cards = self.cog.get_user_cards(target_user.id)
        if target_cards is None:
            target_cards = []
        # Préparer et envoyer la demande d'échange au joueur cible
        offer_embed = discord.Embed(
            title="Proposition d'échange",
            description=f"{self.user.mention} propose d'échanger sa carte **{name}** *({cat})* avec vous."
        )
        view = TradeConfirmView(self.cog, offerer=self.user, target=target_user, card_category=cat, card_name=name)
        try:
            await target_user.send(embed=offer_embed, view=view)
            await interaction.response.send_message(f"📨 Proposition d'échange envoyée à {target_user.mention} !", ephemeral=True)
        except discord.Forbidden:
            # Si on ne peut pas DM l'utilisateur cible, on envoie la demande dans le canal courant
            await interaction.channel.send(f"{target_user.mention}", embed=offer_embed, view=view)
            await interaction.response.send_message("Proposition d'échange envoyée publiquement (le destinataire n'a pas pu être contacté en DM).", ephemeral=True)

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
        # Seul le destinataire peut accepter
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas l'utilisateur visé par cet échange.", ephemeral=True)
            return
        # Effectuer l'échange : retirer la carte de l'offreur et l'ajouter au destinataire
        self.cog.remove_card_from_user(self.offerer.id, self.card_category, self.card_name)
        self.cog.add_card_to_user(self.target.id, self.card_category, self.card_name)
        await interaction.response.send_message(f"✅ Échange accepté ! {self.offerer.mention} a donné **{self.card_name}** à {self.target.mention}.")
        # On peut éventuellement notifier l'offreur via DM
        try:
            await self.offerer.send(f"✨ {self.target.display_name} a accepté votre échange et reçu votre carte **{self.card_name}**.")
        except:
            pass
        # Désactiver les boutons après l'échange conclu
        for child in self.children:
            child.disabled = True

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

async def setup(bot):
    await bot.add_cog(Cards(bot))
