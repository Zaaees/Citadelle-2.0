import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Optional
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import os
import re

class ValidationView(discord.ui.View):
    def __init__(self, sheet=None):  # Rendre sheet optionnel
        super().__init__(timeout=None)
        self.sheet = sheet

    @discord.ui.button(label="Validé", style=discord.ButtonStyle.green, custom_id="validate_button")
    async def validate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()  # Déférer immédiatement la réponse
        if self.sheet is None:
            # Récupérer une nouvelle instance de sheet
            cog = interaction.client.get_cog('Validation')
            if cog:
                self.sheet = cog.sheet
            else:
                await interaction.response.send_message("Erreur: impossible de traiter la validation pour le moment.", ephemeral=True)
                return

        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
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
            await interaction.response.send_message("Erreur: Données non trouvées pour ce salon.", ephemeral=True)

    @discord.ui.button(label="À corriger", style=discord.ButtonStyle.red, custom_id="correct_button")
    async def correct_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sheet is None:
            # Récupérer une nouvelle instance de sheet
            cog = interaction.client.get_cog('Validation')
            if cog:
                self.sheet = cog.sheet
            else:
                await interaction.response.send_message("Erreur: impossible de traiter la validation pour le moment.", ephemeral=True)
                return

        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
            return

        channel_id = str(interaction.channel_id)
        try:
            cell = self.sheet.find(channel_id)
            row_data = self.sheet.row_values(cell.row)
            corrections = eval(row_data[2]) if row_data[2] else {}
            existing_correction = corrections.get(interaction.user.id, "")
            
            modal = CorrectionModal(self.sheet, existing_correction)
            await interaction.response.send_modal(modal)
        except gspread.exceptions.CellNotFound:
            await interaction.response.send_message("Erreur: Données non trouvées pour ce salon.", ephemeral=True)

    async def update_validation_message(self, interaction: discord.Interaction):
        channel_id = str(interaction.channel_id)
        cell = self.sheet.find(channel_id)
        row_data = self.sheet.row_values(cell.row)
        
        validated_by = eval(row_data[1]) if row_data[1] else []
        corrections = eval(row_data[2]) if row_data[2] else {}

        embed = discord.Embed(
            title="__État de la validation__",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        validated_text = ""
        for user_id in validated_by:
            user = interaction.guild.get_member(user_id)
            if user:
                validated_text += f"`{user.display_name}`\n"
        
        if validated_text:
            embed.add_field(name="**✅ Validé par**", value=validated_text, inline=False)

        corrections_text = ""
        for user_id, correction in corrections.items():
            user = interaction.guild.get_member(user_id)
            if user:
                corrections_text += f"**▸ `{user.display_name}`**\n{correction}\n\n"

        if corrections_text:
            embed.add_field(name="**🔍 Points à corriger**", value=corrections_text, inline=False)

        message = await interaction.message.edit(embed=embed, view=self)
        if not message.pinned:
            await message.pin()

        # Vérifier s'il y a eu des changements dans les corrections
        cog = interaction.client.get_cog('Validation')
        if cog:
            await cog.notify_owner_if_needed(interaction.channel)

class CorrectionModal(discord.ui.Modal, title="Points à corriger"):
    def __init__(self, sheet, existing_correction=""):
        super().__init__()
        self.sheet = sheet
        self.correction = discord.ui.TextInput(
            label="Détaillez les points à corriger",
            style=discord.TextStyle.paragraph,
            placeholder="Entrez les points à corriger...",
            required=True,
            default=existing_correction,
            max_length=1000
        )
        self.add_item(self.correction)  # Ajout explicite du TextInput

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = str(interaction.channel.id)
        try:
            cell = self.sheet.find(channel_id)
            row_data = self.sheet.row_values(cell.row)
            corrections = eval(row_data[2]) if row_data[2] else {}
            
            corrections[interaction.user.id] = self.correction.value
            self.sheet.update_cell(cell.row, 3, str(corrections))

            validated_by = eval(row_data[1]) if row_data[1] else []
            if interaction.user.id in validated_by:
                validated_by.remove(interaction.user.id)
                self.sheet.update_cell(cell.row, 2, str(validated_by))

            view = ValidationView(self.sheet)
            await interaction.response.defer()  # Déférer la réponse d'abord
            await view.update_validation_message(interaction)
            await interaction.followup.send("Vos corrections ont été enregistrées.", ephemeral=True)
        except gspread.exceptions.CellNotFound:
            await interaction.response.send_message("Erreur: Données non trouvées pour ce salon.", ephemeral=True)

class Validation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.setup_sheets()
        # Ajouter cette ligne pour que les boutons persistent après redémarrage
        bot.add_view(ValidationView())
        self.last_ping = {}  # Dictionnaire pour stocker les timestamps des derniers pings

    def setup_sheets(self):
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_info(
            eval(os.getenv('SERVICE_ACCOUNT_JSON')),  # eval() convertit directement la chaîne en dictionnaire
            scopes=scopes
        )
        client = gspread.authorize(creds)
        spreadsheet_id = os.getenv('GOOGLE_SHEET_ID_VALIDATION')
        self.sheet = client.open_by_key(spreadsheet_id).sheet1

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
        owner = await self.get_ticket_owner(channel)
        if not owner:
            return

        now = datetime.now()
        last_ping_time = self.last_ping.get(channel.id)
        
        if last_ping_time is None or (now - last_ping_time) > timedelta(minutes=5):
            self.last_ping[channel.id] = now
            try:
                cell = self.sheet.find(str(channel.id))
                row_data = self.sheet.row_values(cell.row)
                if len(row_data) >= 4 and row_data[3]:  # Vérifier si l'ID du message existe
                    message_id = int(row_data[3])
                    message_link = f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{message_id}"
                    await channel.send(
                        f"{owner.mention} Des modifications ont été demandées sur votre fiche.\n"
                        f"Vous pouvez consulter les détails ici : {message_link}"
                    )
            except Exception as e:
                print(f"Erreur lors de l'envoi du ping: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print("Validation Cog is ready!")

    @app_commands.command(name="validation", description="Envoie le message de validation dans ce salon")
    @app_commands.default_permissions(administrator=True)
    async def validation(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Déférer la réponse ici aussi
        if not interaction.channel.name.startswith("【🎭】"):
            await interaction.response.send_message("Ce salon n'est pas un ticket de personnage.", ephemeral=True)
            return

        channel_id = str(interaction.channel.id)
        try:
            cell = self.sheet.find(channel_id)
        except gspread.exceptions.CellNotFound:
            self.sheet.append_row([channel_id, "[]", "{}", ""])  # Ajout d'une colonne vide pour l'ID du message
        
        embed = discord.Embed(
            title="État de la validation",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        view = ValidationView(self.sheet)
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        await message.pin()
        
        # Sauvegarder l'ID du message
        cell = self.sheet.find(channel_id)
        self.sheet.update_cell(cell.row, 4, str(message.id))

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
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    view = ValidationView(self.sheet)
                    message = await after.send(embed=embed, view=view)
                    await message.pin()
                    # Ajouter le canal et l'ID du message à la feuille
                    self.sheet.append_row([str(after.id), "[]", "{}", str(message.id)])

async def setup(bot: commands.Bot):
    await bot.add_cog(Validation(bot))
