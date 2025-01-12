import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Optional
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import os
import re
import time

class ValidationView(discord.ui.View):
    def __init__(self, cog=None):  # Modifier pour accepter le cog au lieu du sheet
        super().__init__(timeout=None)
        self.cog = cog

    @property
    def sheet(self):
        # Obtenir le sheet via le cog
        return self.cog.sheet if self.cog else None

    @discord.ui.button(label="Validé", style=discord.ButtonStyle.green, custom_id="validate_button")
    async def validate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)  # Déférer immédiatement la réponse
        if self.sheet is None:
            # Récupérer une nouvelle instance de cog
            self.cog = interaction.client.get_cog('Validation')
            if not self.cog:
                await interaction.followup.send("Erreur: impossible de traiter la validation pour le moment.", ephemeral=True)
                return

        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.followup.send("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
            return

        channel_id = str(interaction.channel_id)
        try:
            cell = self.sheet.find(channel_id)
            row_data = self.sheet.row_values(cell.row)
            validated_by = eval(row_data[1]) if row_data[1] else []
            corrections = eval(row_data[2]) if row_data[2] else {}

            if interaction.user.id in validated_by:
                validated_by.remove(interaction.user.id)
                if interaction.user.id in corrections:
                    del corrections[interaction.user.id]
            else:
                validated_by.append(interaction.user.id)
                if interaction.user.id in corrections:
                    del corrections[interaction.user.id]

            self.sheet.update_cell(cell.row, 2, str(validated_by))
            self.sheet.update_cell(cell.row, 3, str(corrections))

            await self.update_validation_message(interaction)
        except gspread.exceptions.CellNotFound:
            await interaction.followup.send("Erreur: Données non trouvées pour ce salon.", ephemeral=True)

    @discord.ui.button(label="À corriger", style=discord.ButtonStyle.red, custom_id="correct_button")
    async def correct_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérifier les permissions d'abord
        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.response.send_message("Permission non accordée.", ephemeral=True)
            return

        if self.sheet is None:
            self.cog = interaction.client.get_cog('Validation')
            if not self.cog:
                await interaction.response.send_message("Erreur système.", ephemeral=True)
                return

        channel_id = str(interaction.channel_id)
        try:
            cell = self.sheet.find(channel_id)
            row_data = self.sheet.row_values(cell.row)
            corrections = eval(row_data[2]) if row_data[2] else {}
            existing_correction = corrections.get(interaction.user.id, "")
            
            modal = CorrectionModal(self.cog.sheet, existing_correction)
            await interaction.response.send_modal(modal)
        except gspread.exceptions.CellNotFound:
            await interaction.response.send_message("Erreur: Données non trouvées pour ce salon.", ephemeral=True)
        except Exception as e:
            print(f"Erreur dans correct_button: {e}")
            await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)

    def convert_channel_mentions(self, guild: discord.Guild, text: str) -> str:
        """Convertit les [#nom-salon] en mentions de salon"""
        pattern = r'\[#([^\]]+)\]'
        
        def replace_channel(match):
            channel_name = match.group(1)
            
            # Fonction pour normaliser un nom de canal
            def normalize_channel_name(name):
                # Supprimer les émojis Discord custom (:emoji:)
                name = re.sub(r':[a-zA-Z0-9_]+:', '', name)
                # Supprimer les émojis Unicode
                name = re.sub(r'【[^】]+】', '', name)
                # Nettoyer les espaces et caractères spéciaux
                name = re.sub(r'[^a-zA-Z0-9\-]', '', name.lower())
                return name
            
            # Normaliser le nom recherché
            normalized_search = normalize_channel_name(channel_name)
            
            # Chercher parmi tous les canaux
            for ch in guild.channels:
                # Si correspondance exacte
                if ch.name == channel_name:
                    return f"<#{ch.id}>"
                
                # Si correspondance après normalisation
                if normalize_channel_name(ch.name) == normalized_search:
                    return f"<#{ch.id}>"
            
            return match.group(0)
        
        return re.sub(pattern, replace_channel, text)

    async def update_validation_message(self, interaction: discord.Interaction):
        try:
            channel_id = str(interaction.channel_id)
            cell = self.sheet.find(channel_id)
            row_data = self.sheet.row_values(cell.row)
            
            validated_by = eval(row_data[1]) if row_data[1] else []
            corrections = eval(row_data[2]) if row_data[2] else {}

            # Message principal
            main_embed = discord.Embed(
                title="__État de la validation__",
                color=discord.Color.from_str("#6d5380"),
                timestamp=datetime.now()
            )

            # Préparer le contenu des validations
            validated_text = ""
            for user_id in validated_by:
                user = interaction.guild.get_member(user_id)
                if user:
                    validated_text += f"`{user.display_name}`\n"
            
            if validated_text:
                main_embed.add_field(name="**✅ Validé par**", value=validated_text[:1024], inline=False)

            # Préparer le contenu des corrections dans la description
            corrections_text = ""
            if corrections:
                corrections_text = "**🔍 Points à corriger :**\n\n"
                for user_id, correction in corrections.items():
                    user = interaction.guild.get_member(user_id)
                    if user:
                        # Convertir les mentions de salon dans le texte
                        converted_correction = self.convert_channel_mentions(interaction.guild, correction)
                        corrections_text += f"**▸ `{user.display_name}`**\n{converted_correction}\n\n"

            if corrections_text:
                if len(corrections_text) > 4096:
                    corrections_text = corrections_text[:4093] + "..."
                main_embed.description = corrections_text

            # Mise à jour du message
            try:
                await interaction.message.edit(content=None, embed=main_embed, view=self)
            except:
                message = await interaction.channel.send(embed=main_embed, view=self)
                await message.pin()
                self.sheet.update_cell(cell.row, 4, str(message.id))

        except Exception as e:
            print(f"Erreur lors de la mise à jour du message : {e}")
            try:
                await interaction.followup.send("Une erreur est survenue lors de la mise à jour.", ephemeral=True)
            except discord.NotFound:
                await interaction.channel.send("Une erreur est survenue lors de la mise à jour.")

class CorrectionModal(discord.ui.Modal, title="Points à corriger"):
    def __init__(self, sheet, existing_correction=""):
        super().__init__()
        self.sheet = sheet
        self.correction = discord.ui.TextInput(
            label="Détaillez les points à corriger",
            style=discord.TextStyle.paragraph,
            placeholder="Entrez les points à corriger... Utilisez [#nom-salon] pour mentionner un salon",
            required=True,
            default=existing_correction,
            max_length=4000  # Augmentation de la limite à 4000 caractères
        )
        self.add_item(self.correction)  # Ajout explicite du TextInput

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            channel_id = str(interaction.channel.id)
            cell = self.sheet.find(channel_id)
            row_data = self.sheet.row_values(cell.row)
            corrections = eval(row_data[2]) if row_data[2] else {}
            old_correction = corrections.get(interaction.user.id, None)
            
            should_notify = old_correction != self.correction.value  # Modifier la condition pour toujours notifier lors d'une modification
            
            corrections[interaction.user.id] = self.correction.value
            self.sheet.update_cell(cell.row, 3, str(corrections))

            validated_by = eval(row_data[1]) if row_data[1] else []
            if interaction.user.id in validated_by:
                validated_by.remove(interaction.user.id)
                self.sheet.update_cell(cell.row, 2, str(validated_by))

            cog = interaction.client.get_cog('Validation')
            view = ValidationView(cog)
            
            # Notifier avant la mise à jour du message pour être sûr que ça passe
            if should_notify and cog:
                await cog.notify_owner_if_needed(interaction.channel)
            
            try:
                await view.update_validation_message(interaction)
            except Exception as e:
                print(f"Erreur lors de la mise à jour : {e}")
                await interaction.channel.send("Les modifications ont été enregistrées mais une erreur est survenue lors de la mise à jour de l'affichage.")
            
        except Exception as e:
            print(f"Erreur dans on_submit : {e}")
            await interaction.followup.send("Une erreur est survenue lors de l'enregistrement.", ephemeral=True)

class Validation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sheet = None
        self._client = None
        self.last_ping = {}
        self.setup_persistent_views()

    def setup_persistent_views(self):
        """Setup persistent views on initialization"""
        self.bot.add_view(ValidationView(self))

    @property
    def sheet(self):
        if self._sheet is None:
            self._setup_sheets()
        return self._sheet

    def _setup_sheets(self):
        """Initialize Google Sheets connection only when needed"""
        if self._client is None:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_info(
                eval(os.getenv('SERVICE_ACCOUNT_JSON')),
                scopes=scopes
            )
            self._client = gspread.authorize(creds)

        if self._sheet is None:
            spreadsheet_id = os.getenv('GOOGLE_SHEET_ID_VALIDATION')
            self._sheet = self._client.open_by_key(spreadsheet_id).sheet1

    async def get_ticket_owner(self, channel):
        try:
            # Récupérer le premier message du canal
            first_message = [msg async for msg in channel.history(limit=1, oldest_first=True)][0]
            # Chercher une mention d'utilisateur dans le contenu
            mention_pattern = r'<@!?(\d+)>'
            matches = re.findall(mention_pattern, first_message.content)
            if matches:
                user_id = int(matches[0])
                return await self.bot.fetch_user(user_id)
        except Exception as e:
            print(f"Erreur lors de la recherche du propriétaire: {e}")
        return None

    async def notify_owner_if_needed(self, channel):
        try:
            # Récupérer le propriétaire
            owner = await self.get_ticket_owner(channel)
            if not owner:
                return
                
            # Vérifier le délai depuis le dernier ping
            current_time = time.time()
            if channel.id in self.last_ping:
                if current_time - self.last_ping[channel.id] < 300:  # 5 minutes de délai
                    return
                    
            # Récupérer l'ID du message de validation
            cell = self.sheet.find(str(channel.id))
            message_id = self.sheet.cell(cell.row, 4).value
            
            if not message_id:
                return
                
            # Créer le lien du message
            message_link = f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{message_id}"
            
            # Envoyer la notification
            await channel.send(
                f"{owner.mention} Des modifications ont été demandées sur votre fiche.\n"
                f"Vous pouvez consulter les détails ici : {message_link}"
            )
            
            # Mettre à jour le timestamp du dernier ping
            self.last_ping[channel.id] = current_time
            
        except Exception as e:
            print(f"Erreur lors de la notification : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print("Validation Cog is ready!")

    @app_commands.command(name="validation", description="Envoie le message de validation dans ce salon")
    @app_commands.default_permissions(administrator=True)
    async def validation(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not interaction.channel.name.startswith("【🎭】"):
            await interaction.followup.send("Ce salon n'est pas un ticket de personnage.", ephemeral=True)
            return

        channel_id = str(interaction.channel.id)
        try:
            cell = self.sheet.find(channel_id)
        except gspread.exceptions.CellNotFound:
            self.sheet.append_row([channel_id, "[]", "{}", ""])  # Plus besoin de la 5ème colonne
        
        embed = discord.Embed(
            title="État de la validation",
            color=discord.Color.from_str("#6d5380"),
            timestamp=datetime.now()
        )
        
        view = ValidationView(self)
        message = await interaction.followup.send(embed=embed, view=view)
        await message.pin()
        
        cell = self.sheet.find(channel_id)
        self.sheet.update_cell(cell.row, 4, str(message.id))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorer les messages du bot
        if message.author.bot:
            return
            
        # Vérifier si c'est un salon de validation
        if not isinstance(message.channel, discord.TextChannel) or not message.channel.name.startswith("【🎭】"):
            return
            
        # Vérifier si le message contient un lien Google Docs
        if "https://docs.google.com/" in message.content:
            try:
                await message.pin()
            except discord.Forbidden:
                print(f"Impossible d'épingler le message dans {message.channel.name}: Permission manquante")
            except discord.HTTPException as e:
                print(f"Erreur lors de l'épinglage du message: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        # Vérifie si c'est un canal texte et si le nom a été modifié
        if isinstance(after, discord.TextChannel):
            # Vérifie si le nom a été changé pour inclure 【🎭】
            if not before.name.startswith("【🎭】") and after.name.startswith("【🎭】"):
                # Vérifie si le canal n'est pas déjà dans la feuille
                try:
                    self.sheet.find(str(after.id))
                except gspread.exceptions.CellNotFound:
                    embed = discord.Embed(
                        title="État de la validation",
                        color=discord.Color.from_str("#6d5380"),
                        timestamp=datetime.now()
                    )
                    view = ValidationView(self)
                    message = await after.send(embed=embed, view=view)
                    await message.pin()
                    # Ajouter le canal et l'ID du message à la feuille
                    self.sheet.append_row([str(after.id), "[]", "{}", str(message.id), "[]"])

async def setup(bot: commands.Bot):
    await bot.add_cog(Validation(bot))
