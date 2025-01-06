import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Optional
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os

class ValidationView(discord.ui.View):
    def __init__(self, sheet):
        super().__init__(timeout=None)
        self.sheet = sheet

    @discord.ui.button(label="Validé", style=discord.ButtonStyle.green, custom_id="validate_button")
    async def validate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
            return

        modal = CorrectionModal(self.sheet)
        await interaction.response.send_modal(modal)

    async def update_validation_message(self, interaction: discord.Interaction):
        channel_id = str(interaction.channel_id)
        cell = self.sheet.find(channel_id)
        row_data = self.sheet.row_values(cell.row)
        
        validated_by = eval(row_data[1]) if row_data[1] else []
        corrections = eval(row_data[2]) if row_data[2] else {}

        embed = discord.Embed(
            title="État de la validation",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        validated_text = ""
        for user_id in validated_by:
            user = interaction.guild.get_member(user_id)
            if user:
                validated_text += f"✓ {user.display_name}\n"
        
        if validated_text:
            embed.add_field(name="Validé par:", value=validated_text, inline=False)

        corrections_text = ""
        for user_id, correction in corrections.items():
            user = interaction.guild.get_member(user_id)
            if user:
                corrections_text += f"**{user.display_name}** :\n{correction}\n\n"

        if corrections_text:
            embed.add_field(name="Points à corriger:", value=corrections_text, inline=False)

        message = await interaction.message.edit(embed=embed, view=self)
        if not message.pinned:
            await message.pin()

class CorrectionModal(discord.ui.Modal, title="Points à corriger"):
    def __init__(self, sheet):
        super().__init__()
        self.sheet = sheet

    correction = discord.ui.TextInput(
        label="Détaillez les points à corriger",
        style=discord.TextStyle.paragraph,
        placeholder="Entrez les points à corriger...",
        required=True
    )

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
            await view.update_validation_message(interaction)
            await interaction.response.send_message("Vos corrections ont été enregistrées.", ephemeral=True)
        except gspread.exceptions.CellNotFound:
            await interaction.response.send_message("Erreur: Données non trouvées pour ce salon.", ephemeral=True)

class Validation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.setup_sheets()

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

    @commands.Cog.listener()
    async def on_ready(self):
        print("Validation Cog is ready!")

    @app_commands.command(name="validation", description="Envoie le message de validation dans ce salon")
    @app_commands.default_permissions(administrator=True)
    async def validation(self, interaction: discord.Interaction):
        if not interaction.channel.name.startswith("【🎭】"):
            await interaction.response.send_message("Ce salon n'est pas un ticket de personnage.", ephemeral=True)
            return

        channel_id = str(interaction.channel.id)
        try:
            cell = self.sheet.find(channel_id)
        except gspread.exceptions.CellNotFound:
            self.sheet.append_row([channel_id, "[]", "{}"])
        
        embed = discord.Embed(
            title="État de la validation",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        view = ValidationView(self.sheet)
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        await message.pin()

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.TextChannel):
            if channel.category_id == 1020827427888435210 and channel.name.startswith("【🎭】"):
                self.sheet.append_row([str(channel.id), "[]", "{}"])
                embed = discord.Embed(
                    title="État de la validation",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                view = ValidationView(self.sheet)
                message = await channel.send(embed=embed, view=view)
                await message.pin()

async def setup(bot: commands.Bot):
    await bot.add_cog(Validation(bot))