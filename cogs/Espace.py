import discord
from discord import app_commands
from discord.ext import commands
import random
import os
import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

TROUBLES = [
    {
        "nom": "Trouble de l'anxiété généralisée",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_anxieux_g%C3%A9n%C3%A9ralis%C3%A9"
    },
    {
        "nom": "Trouble obsessionnel compulsif",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_obsessionnel_compulsif"
    },
    {
        "nom": "Trouble de la personnalité borderline",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalit%C3%A9_borderline"
    },
    {
        "nom": "Syndrome de stress post-traumatique",
        "lien": "https://fr.wikipedia.org/wiki/État_de_stress_post-traumatique"
    },
    {
        "nom": "Trouble bipolaire",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_bipolaire"
    },
    {
        "nom": "Trouble dissociatif de l'identité",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_dissociatif_de_l%27identit%C3%A9"
    },
    {
        "nom": "Trouble du contrôle des impulsions",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_du_contrôle_des_impulsions"
    },
    {
        "nom": "Dépression majeure",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_dépressif_caractérisé"
    },
    {
        "nom": "Schizophrénie",
        "lien": "https://fr.wikipedia.org/wiki/Schizophrénie"
    },
    {
        "nom": "Trouble panique",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_panique"
    },
    {
        "nom": "Trouble du déficit de l'attention avec hyperactivité",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_du_déficit_de_l%27attention_avec_ou_sans_hyperactivité"
    },
    {
        "nom": "Anorexie mentale",
        "lien": "https://fr.wikipedia.org/wiki/Anorexie_mentale"
    },
    {
        "nom": "Boulimie",
        "lien": "https://fr.wikipedia.org/wiki/Boulimie"
    },
    {
        "nom": "Trouble de la personnalité narcissique",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_narcissique"
    },
    {
        "nom": "Trouble de la personnalité antisociale",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_antisociale"
    },
    {
        "nom": "Agoraphobie",
        "lien": "https://fr.wikipedia.org/wiki/Agoraphobie"
    },
    {
        "nom": "Phobie sociale",
        "lien": "https://fr.wikipedia.org/wiki/Phobie_sociale"
    },
    {
        "nom": "Trouble du spectre de l'autisme",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_du_spectre_de_l%27autisme"
    },
    {
        "nom": "Trouble dysphorique prémenstruel",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_dysphorique_prémenstruel"
    },
    {
        "nom": "Kleptomanie",
        "lien": "https://fr.wikipedia.org/wiki/Kleptomanie"
    },
    {
        "nom": "Trichotillomanie",
        "lien": "https://fr.wikipedia.org/wiki/Trichotillomanie"
    },
    {
        "nom": "Trouble de la personnalité histrionique",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_histrionique"
    },
    {
        "nom": "Trouble de la personnalité évitante",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_évitante"
    },
    {
        "nom": "Trouble de la personnalité dépendante",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_dépendante"
    },
    {
        "nom": "Trouble de la personnalité paranoïaque",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_paranoïaque"
    },
    {
        "nom": "Trouble de la personnalité schizoïde",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_schizoïde"
    },
    {
        "nom": "Trouble de la personnalité schizotypique",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_schizotypique"
    },
    {
        "nom": "Trouble du comportement alimentaire non spécifié",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_des_conduites_alimentaires_non_spécifié"
    },
    {
        "nom": "Trouble d'hyperphagie boulimique",
        "lien": "https://fr.wikipedia.org/wiki/Hyperphagie_boulimique"
    },
    {
        "nom": "Trouble de l'adaptation",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_l%27adaptation"
    },
    {
        "nom": "Trouble de la communication sociale",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_communication_sociale"
    },
    {
        "nom": "Trouble du développement de la coordination",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_développemental_de_la_coordination"
    },
    {
        "nom": "Trouble spécifique des apprentissages",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_spécifique_des_apprentissages"
    },
    {
        "nom": "Trouble de la régulation émotionnelle",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_régulation_émotionnelle"
    },
    {
        "nom": "Trouble de l'attachement",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_l%27attachement"
    },
    {
        "nom": "Trouble du sommeil",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_du_sommeil"
    },
    {
        "nom": "Trouble de stress aigu",
        "lien": "https://fr.wikipedia.org/wiki/État_de_stress_aigu"
    },
    {
        "nom": "Trouble de conversion",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_conversion"
    },
    {
        "nom": "Trouble factice",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_factice"
    },
    {
        "nom": "Trouble de l'identité sexuelle",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_l%27identité_sexuelle"
    },
    {
        "nom": "Trouble de la préférence sexuelle",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_préférence_sexuelle"
    },
    {
        "nom": "Trouble de l'excitation sexuelle",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_l%27excitation_sexuelle"
    },
    {
        "nom": "Trouble dysthymique",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_dysthymique"
    },
    {
        "nom": "Trouble cyclothymique",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_cyclothymique"
    },
    {
        "nom": "Trouble de la personnalité obsessionnelle-compulsive",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_obsessionnelle-compulsive"
    },
    {
        "nom": "Trouble oppositionnel avec provocation",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_oppositionnel_avec_provocation"
    },
    {
        "nom": "Trouble explosif intermittent",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_explosif_intermittent"
    },
    {
        "nom": "Trouble de l'usage de substances",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_l%27usage_d%27une_substance"
    },
    {
        "nom": "Trouble neurocognitif",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_neurocognitif"
    },
    {
        "nom": "Trouble somatoforme",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_somatoforme"
    },
    {
        "nom": "Trouble délirant",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_délirant"
    },
    {
        "nom": "Trouble catatonique",
        "lien": "https://fr.wikipedia.org/wiki/Catatonie"
    },
    {
        "nom": "Trouble de la personnalité mixte",
        "lien": "https://fr.wikipedia.org/wiki/Trouble_de_la_personnalité_mixte"
    }
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
    @app_commands.checks.has_role(1328059488615534683)
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
                embed = discord.Embed(description="Vous n'avez aucun personnage avec des troubles.", color=0x6d5380)
                await interaction.followup.send(embed=embed)
                return
                
            embed = discord.Embed(title="Troubles psychologiques de vos personnages", color=0x6d5380)
            for perso, troubles in user_troubles_dict.items():
                # Rechercher les liens pour chaque trouble
                troubles_avec_liens = []
                for trouble in troubles:
                    trouble_info = next((t for t in TROUBLES if t["nom"] == trouble), None)
                    if trouble_info:
                        troubles_avec_liens.append(f"• [{trouble_info['nom']}]({trouble_info['lien']})")
                    else:
                        troubles_avec_liens.append(f"• {trouble}")
                embed.add_field(name=perso, value="\n".join(troubles_avec_liens), inline=False)
            await interaction.followup.send(embed=embed)
            return

        # Normaliser le nom du personnage
        personnage_norm = personnage.lower()
        
        # Récupérer les troubles existants
        existing_troubles = [row[2] for row in troubles_data 
                           if row[0] == str(interaction.user.id) 
                           and row[1].lower() == personnage_norm]
        
        # Calculer les troubles disponibles
        available_troubles = [t for t in TROUBLES if t["nom"] not in existing_troubles]
        
        if not available_troubles:
            troubles_avec_liens = []
            for trouble in existing_troubles:
                trouble_info = next((t for t in TROUBLES if t["nom"] == trouble), None)
                if trouble_info:
                    troubles_avec_liens.append(f"• [{trouble_info['nom']}]({trouble_info['lien']})")
                else:
                    troubles_avec_liens.append(f"• {trouble}")
            
            embed = discord.Embed(title=f"Troubles de {personnage}", color=0x6d5380)
            embed.description = f"**{personnage}** a déjà tous les troubles possibles !\n\n**Troubles actuels:**\n" + "\n".join(troubles_avec_liens)
            await interaction.followup.send(embed=embed)
            return

        # Déterminer si nouveau trouble (1/5)
        if random.randint(1, 5) != 1:
            embed = discord.Embed(title=f"Résultat pour {personnage}", color=0x6d5380)
            if existing_troubles:
                troubles_avec_liens = []
                for trouble in existing_troubles:
                    trouble_info = next((t for t in TROUBLES if t["nom"] == trouble), None)
                    if trouble_info:
                        troubles_avec_liens.append(f"• [{trouble_info['nom']}]({trouble_info['lien']})")
                    else:
                        troubles_avec_liens.append(f"• {trouble}")
                embed.description = f"**{personnage}** ne développe pas de nouveau trouble psychologique.\n\n**Troubles actuels:**\n" + "\n".join(troubles_avec_liens)
            else:
                embed.description = f"**{personnage}** ne développe pas de trouble psychologique."
            await interaction.followup.send(embed=embed)
            return

        # Attribuer un nouveau trouble
        nouveau_trouble = random.choice(available_troubles)
        self.sheet.append_row([str(interaction.user.id), personnage, nouveau_trouble["nom"]])
        
        # Créer l'embed de réponse
        troubles_avec_liens = []
        for trouble in existing_troubles + [nouveau_trouble["nom"]]:
            trouble_info = next((t for t in TROUBLES if t["nom"] == trouble), None)
            if trouble_info:
                troubles_avec_liens.append(f"• [{trouble_info['nom']}]({trouble_info['lien']})")
            else:
                troubles_avec_liens.append(f"• {trouble}")

        embed = discord.Embed(title=f"Nouveau trouble pour {personnage}", color=0x6d5380)
        embed.description = f"**{personnage}** développe un nouveau trouble : [{nouveau_trouble['nom']}]({nouveau_trouble['lien']})\n\n**Troubles actuels:**\n" + "\n".join(troubles_avec_liens)
        
        await interaction.followup.send(embed=embed)

    @espace.error
    async def espace_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            embed = discord.Embed(description="Vous n'avez pas la permission d'utiliser cette commande.", color=0x6d5380)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(description=f"Une erreur est survenue : {error}", color=0x6d5380)
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Espace(bot))
