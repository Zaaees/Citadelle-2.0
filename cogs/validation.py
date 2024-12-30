import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import asyncio

class CharacterValidation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_google_sheets()
        
    def setup_google_sheets(self):
        service_account_info = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.sheet_service = build('sheets', 'v4', credentials=credentials)
        self.SHEET_ID = os.getenv('GOOGLE_SHEET_ID_VALIDATIONS')

    def get_sheet_data(self, channel_id):
        try:
            result = self.sheet_service.spreadsheets().values().get(
                spreadsheetId=self.SHEET_ID,
                range=f'{channel_id}!A:C'
            ).execute()
            return result.get('values', [])
        except Exception:
            return []

    def update_sheet_data(self, channel_id, data):
        try:
            self.sheet_service.spreadsheets().values().clear(
                spreadsheetId=self.SHEET_ID,
                range=f'{channel_id}!A:C'
            ).execute()
            
            if data:
                self.sheet_service.spreadsheets().values().update(
                    spreadsheetId=self.SHEET_ID,
                    range=f'{channel_id}!A1',
                    valueInputOption='RAW',
                    body={'values': data}
                ).execute()
        except Exception as e:
            print(f"Erreur lors de la mise à jour des données: {e}")

    async def create_validation_embed(self, channel_id):
        data = self.get_sheet_data(channel_id)
        
        validations = []
        corrections = []
        
        for row in data:
            if len(row) >= 2:
                if row[1] == "validated":
                    validations.append(row[0])
                elif row[1] == "correction":
                    corrections.append(f"{row[0]}: {row[2]}")

        embed = discord.Embed(
            title="Validation de la fiche personnage",
            color=discord.Color.blue()
        )
        
        if validations:
            embed.add_field(
                name="Validations",
                value="\n".join(f"✅ {v}" for v in validations),
                inline=False
            )
            
        if corrections:
            embed.add_field(
                name="Points à corriger",
                value="\n".join(f"❌ {c}" for c in corrections),
                inline=False
            )
            
        return embed

    async def correction_modal(self, interaction):
        modal = CorrectionModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.correction:
            channel_id = str(interaction.channel.id)
            data = self.get_sheet_data(channel_id)
            
            # Supprime les anciennes corrections de cet utilisateur
            data = [row for row in data if not (row[0] == interaction.user.name and row[1] == "correction")]
            
            # Ajoute la nouvelle correction
            data.append([interaction.user.name, "correction", modal.correction])
            
            self.update_sheet_data(channel_id, data)
            return True
        return False

    @app_commands.command(name="validation", description="Envoie le message de validation")
    @app_commands.checks.has_role(1018179623886000278)  # Rôle MJ
    async def send_validation(self, interaction: discord.Interaction):
        if not interaction.channel.name.startswith("【🎭】"):
            await interaction.response.send_message("Ce salon n'est pas un ticket de personnage.", ephemeral=True)
            return

        view = ValidationView(self)
        embed = await self.create_validation_embed(str(interaction.channel.id))
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        await message.pin()

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if (isinstance(channel, discord.TextChannel) and 
            channel.category_id == 1020827427888435210 and 
            channel.name.startswith("【🎭】")):
            
            view = ValidationView(self)
            embed = await self.create_validation_embed(str(channel.id))
            message = await channel.send(embed=embed, view=view)
            await message.pin()

class ValidationView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Validé", style=discord.ButtonStyle.green, custom_id="validate")
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
            return

        channel_id = str(interaction.channel.id)
        data = self.cog.get_sheet_data(channel_id)
        
        user_entry = [row for row in data if row[0] == interaction.user.name]
        
        if user_entry and user_entry[0][1] == "validated":
            # Supprime la validation
            data = [row for row in data if row[0] != interaction.user.name]
        else:
            # Supprime toutes les entrées de l'utilisateur et ajoute la validation
            data = [row for row in data if row[0] != interaction.user.name]
            data.append([interaction.user.name, "validated", ""])
            
        self.cog.update_sheet_data(channel_id, data)
        
        embed = await self.cog.create_validation_embed(channel_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="À corriger", style=discord.ButtonStyle.red, custom_id="correct")
    async def correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
            return

        if await self.cog.correction_modal(interaction):
            embed = await self.cog.create_validation_embed(str(interaction.channel.id))
            await interaction.message.edit(embed=embed, view=self)

class CorrectionModal(discord.ui.Modal, title="Points à corriger"):
    correction_input = discord.ui.TextInput(
        label="Que faut-il corriger ?",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        self.correction = self.correction_input.value
        await interaction.response.send_message("Correction enregistrée.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CharacterValidation(bot))