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
        
        troubles_data = self.sheet.get_all_values()
        
        if not personnage:
            # Regrouper les troubles par personnage
            user_troubles_dict = {}
            for row in troubles_data:
                if row[0] == str(interaction.user.id):
                    if row[1] not in user_troubles_dict:
                        user_troubles_dict[row[1]] = []
                    user_troubles_dict[row[1]].append(row[2])
            
            if not user_troubles_dict:
                await interaction.followup.send("Vous n'avez aucun personnage avec des troubles.")
                return
                
            embed = discord.Embed(title="Troubles psychologiques de vos personnages", color=0x2F3136)
            for perso, troubles in user_troubles_dict.items():
                embed.add_field(name=perso, value="\n".join([f"• {t}" for t in troubles]), inline=False)
            await interaction.followup.send(embed=embed)
            return

        # Normaliser le nom du personnage (mettre en minuscule pour la comparaison)
        personnage_norm = personnage.lower()
        
        # Récupérer tous les troubles existants du personnage
        existing_troubles = [row[2] for row in troubles_data 
                           if row[0] == str(interaction.user.id) 
                           and row[1].lower() == personnage_norm]

        # Calculer les troubles disponibles
        available_troubles = [t for t in TROUBLES if t not in existing_troubles]
        
        if not available_troubles:
            troubles_list = "\n".join([f"• {t}" for t in existing_troubles])
            await interaction.followup.send(f"**{personnage}** a déjà tous les troubles possibles !\n\nTroubles actuels :\n{troubles_list}")
            return

        # Déterminer si le personnage développe un nouveau trouble (1 chance sur 5)
        if random.randint(1, 5) != 1:
            if existing_troubles:
                troubles_list = "\n".join([f"• {t}" for t in existing_troubles])
                await interaction.followup.send(f"**{personnage}** ne développe pas de nouveau trouble psychologique.\n\nTroubles actuels :\n{troubles_list}")
            else:
                await interaction.followup.send(f"**{personnage}** ne développe pas de trouble psychologique.")
            return

        # Attribuer un nouveau trouble aléatoire parmi ceux disponibles
        nouveau_trouble = random.choice(available_troubles)
        
        # Ajouter à la feuille
        self.sheet.append_row([str(interaction.user.id), personnage, nouveau_trouble])
        
        # Créer le message de réponse avec la liste complète des troubles
        troubles_list = "\n".join([f"• {t}" for t in existing_troubles + [nouveau_trouble]])
        message = f"**{personnage}** développe un nouveau trouble : {nouveau_trouble}\n\nTroubles actuels :\n{troubles_list}"
        
        await interaction.followup.send(message)

    @espace.error
    async def espace_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Une erreur est survenue : {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Espace(bot))
