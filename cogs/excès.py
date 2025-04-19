import os
import json
import random
import discord
from discord import app_commands
from discord.ext import commands
import gspread
from google.oauth2.service_account import Credentials

# Channel ID for permanent excès announcements
PERM_EXCES_CHANNEL_ID = 1085300906981085366

def calc_permanent_exces_chance(n_exces: int) -> float:
    """
    Calcule la chance d'un excès permanent.
    A partir de 4 excès, la probabilité double à chaque excès supplémentaire,
    en partant de 10% au 4ème.
    """
    if n_exces <= 3:
        return 0.0
    chance = 0.1 * (2 ** (n_exces - 4))
    return min(chance, 1.0)

class Exces(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialisation du client Google Sheets via JSON stocké en ENV
        scope = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        sa_json = os.getenv('SERVICE_ACCOUNT_JSON')
        if not sa_json:
            raise RuntimeError("L'ENV SERVICE_ACCOUNT_JSON n'est pas défini ou vide.")
        try:
            info = json.loads(sa_json)
        except json.JSONDecodeError as e:
            raise RuntimeError("SERVICE_ACCOUNT_JSON contient un JSON invalide.") from e
        creds = Credentials.from_service_account_info(info, scopes=scope)
        gc = gspread.authorize(creds)

        # Sheet inventaire : lecture des personnages/utilisateurs
        inv_sheet_id = os.getenv('GOOGLE_SHEET_ID_INVENTAIRE')
        if not inv_sheet_id:
            raise RuntimeError("L'ENV GOOGLE_SHEET_ID_INVENTAIRE n'est pas défini.")
        self.inv_sheet = gc.open_by_key(inv_sheet_id).sheet1

        # Sheet excès : lecture du nombre d'excès par personnage
        exces_sheet_id = os.getenv('GOOGLE_SHEET_ID_EXCES')
        if not exces_sheet_id:
            raise RuntimeError("L'ENV GOOGLE_SHEET_ID_EXCES n'est pas défini.")
        self.exces_sheet = gc.open_by_key(exces_sheet_id).sheet1

    @app_commands.command(name='excès', description="Vérifier si ton personnage subit un excès permanent")
    async def exces(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # Trouver le personnage lié à l'utilisateur dans le sheet inventaire
        inv_records = self.inv_sheet.get_all_records()
        inv_record = next(
            (r for r in inv_records if str(r.get('DiscordID') or r.get('ID', '')) == user_id),
            None
        )
        if not inv_record:
            await interaction.response.send_message(
                "❌ Aucun personnage trouvé pour ton compte.", ephemeral=True
            )
            return

        personnage = inv_record.get('Nom', 'Inconnu')

        # Récupérer le nombre d'excès dans le sheet excès
        exces_records = self.exces_sheet.get_all_records()
        exces_record = next(
            (r for r in exces_records if r.get('Nom') == personnage),
            None
        )
        n_exces = int(exces_record.get('Excès', 0)) if exces_record else 0

        chance = calc_permanent_exces_chance(n_exces)

        # Tirage aléatoire
        if random.random() < chance:
            # Annonce publique dans le salon dédié
            embed = discord.Embed(
                title="💥 EXCÈS PERMANENT 💥",
                description=f"Le personnage **{personnage}** subit un excès permanent !",
                color=discord.Color.red()
            )
            channel = self.bot.get_channel(PERM_EXCES_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
            # Confirmation à l'utilisateur
            await interaction.response.send_message(
                "Ton personnage vient de subir un excès permanent !", ephemeral=True
            )
        else:
            embed = discord.Embed(
                title="✅ Pas d'excès permanent",
                description=(
                    f"Ton personnage **{personnage}** n'a pas subi d'excès permanent.\n"
                    f"Chance : {chance*100:.1f}% pour **{n_exces}** excès précédents."
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Exces(bot))
