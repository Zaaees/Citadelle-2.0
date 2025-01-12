import discord
from discord import app_commands
from discord.ext import commands
import random
import os
import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

TROUBLES = [
    "Trouble de l'anxiété généralisée",
    "Trouble obsessionnel compulsif",
    "Trouble de la personnalité borderline",
    "Syndrome de stress post-traumatique",
    "Trouble bipolaire",
    "Trouble dissociatif de l'identité",
    "Trouble du contrôle des impulsions"
]

class Espace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Configuration Google Sheets
        self.SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        self.client = self.get_sheets_client()
        self.spreadsheet = self.client.open_by_key(os.getenv('TROUBLES_SHEET_ID'))
        self.sheet = self.spreadsheet.get_worksheet(0)  # Première feuille

    def get_sheets_client(self):
        try:
            creds = ServiceAccountCredentials.from_service_account_info(
                eval(os.getenv('SERVICE_ACCOUNT_JSON')), 
                scopes=self.SCOPES
            )
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Erreur d'authentification Google Sheets : {e}")
            return None

    @app_commands.command(name="espace", description="Détermine ou consulte les troubles psychologiques d'un personnage")
    @app_commands.checks.has_role(1328059488615534683)  # Changement ici: suppression des guillemets
    async def espace(self, interaction: discord.Interaction, personnage: str = None):
        await interaction.response.defer()
        
        # Récupérer toutes les données
        troubles_data = self.sheet.get_all_values()
        
        if not personnage:
            # Afficher tous les troubles de l'utilisateur
            user_troubles = [row for row in troubles_data if row[0] == str(interaction.user.id)]
            if not user_troubles:
                await interaction.followup.send("Vous n'avez aucun personnage avec des troubles.")
                return
                
            embed = discord.Embed(title="Troubles psychologiques de vos personnages", color=0x2F3136)
            for row in user_troubles:
                embed.add_field(name=row[1], value=row[2], inline=False)
            await interaction.followup.send(embed=embed)
            return

        # Vérifier si le personnage a déjà un trouble
        existing_trouble = next((row for row in troubles_data if row[0] == str(interaction.user.id) and row[1].lower() == personnage.lower()), None)
        if existing_trouble:
            await interaction.followup.send(f"**{personnage}** a déjà un trouble : {existing_trouble[2]}")
            return

        # Déterminer si le personnage aura un trouble (1 chance sur 5)
        if random.randint(1, 5) != 1:
            await interaction.followup.send(f"**{personnage}** ne développe pas de trouble psychologique.")
            return

        # Attribuer un trouble aléatoire
        trouble = random.choice(TROUBLES)
        
        # Ajouter à la feuille
        self.sheet.append_row([str(interaction.user.id), personnage, trouble])
        
        await interaction.followup.send(f"**{personnage}** développe le trouble suivant : {trouble}")

    @espace.error
    async def espace_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Une erreur est survenue : {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Espace(bot))
