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
        scope = ['https://www.googleapis.com/auth/spreadsheets']
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

        # Sheet excès : lecture/écriture du nombre d'excès par personnage
        exces_sheet_id = os.getenv('GOOGLE_SHEET_ID_EXCES')
        if not exces_sheet_id:
            raise RuntimeError("L'ENV GOOGLE_SHEET_ID_EXCES n'est pas défini.")
        self.exces_sheet = gc.open_by_key(exces_sheet_id).sheet1

    @app_commands.command(name='excès', description="Vérifier si un personnage subit un excès permanent")
    async def exces(self, interaction: discord.Interaction, nom_du_personnage: str):
        user_id = str(interaction.user.id)

        # Vérification du personnage dans le sheet inventaire
        inv_records = self.inv_sheet.get_all_records()
        inv_record = next(
            (r for r in inv_records if r.get('Nom', '').lower() == nom_du_personnage.lower()),
            None
        )
        if not inv_record:
            await interaction.response.send_message(
                "❌ Personnage non trouvé.", ephemeral=True
            )
            return

        # Vérification du propriétaire du personnage
        if str(inv_record.get('DiscordID', '')) != user_id:
            await interaction.response.send_message(
                "❌ Ce personnage ne t'appartient pas.", ephemeral=True
            )
            return

        personnage = inv_record.get('Nom', 'Inconnu')

        # Récupérer le nombre d'excès dans le sheet excès
        exces_records = self.exces_sheet.get_all_records()
        exces_record = next(
            (r for r in exces_records if r.get('Nom', '').lower() == personnage.lower()),
            None
        )

        n_exces = int(exces_record.get('Excès', 0)) if exces_record else 0
        chance = calc_permanent_exces_chance(n_exces)

        # Tirage aléatoire
        permanent = random.random() < chance

        # Mise à jour du nombre d'excès dans le sheet
        if exces_record:
            # Trouver précisément la ligne pour mise à jour
            for idx, record in enumerate(exces_records, start=2):  # start=2 car la première ligne est celle des titres
                if record.get('Nom', '').strip().lower() == personnage.strip().lower():
                    self.exces_sheet.update_cell(idx, 2, n_exces + 1)
                    break
        else:
            self.exces_sheet.append_row([personnage, 1])

        if permanent:
            # Annonce publique dans le salon dédié
            embed = discord.Embed(
                title="💥 EXCÈS PERMANENT 💥",
                description=f"Le personnage **{personnage}** subit un excès permanent !",
                color=discord.Color.red()
            )
            channel = self.bot.get_channel(PERM_EXCES_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
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