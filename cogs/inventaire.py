import os
import discord
from discord import app_commands
from discord.ext import commands
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials


load_dotenv()

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.CHANNEL_ID = 1018159303422656582
        self.MESSAGE_ID = 1230199030412218398
        self.ALERT_CHANNEL_ID = 1085300906981085366
        
        # Configuration Google Sheets
        self.SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        self.client = self.get_sheets_client()
        self.spreadsheet = self.client.open_by_key(os.getenv('GOOGLE_SHEET_ID_INVENTAIRE'))
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

    def load_students(self):
        try:
            # Récupère toutes les valeurs du tableau
            data = self.sheet.get_all_values()
            
            # Convertit en dictionnaire, en supposant la structure Nom | Médailles
            students = {}
            for row in data[1:]:  # Ignore la première ligne (en-têtes)
                if len(row) >= 2 and row[0].strip():
                    try:
                        # Convertir les médailles, avec une valeur par défaut de 0
                        medals = float(row[1]) if row[1].strip() else 0
                        students[row[0].strip()] = medals
                    except ValueError:
                        print(f"Impossible de convertir les médailles pour {row[0]}: {row[1]}")
            
            return students
        except Exception as e:
            print(f"Erreur lors du chargement des étudiants : {e}")
            return {}

    def save_students(self, students):
        try:
            # Récupérer les données existantes
            existing_data = self.sheet.get_all_values()
            
            # Créer un dictionnaire pour suivre les mises à jour
            updated_students = {}
            
            # Parcourir les données existantes
            for row in existing_data[1:]:  # Ignorer l'en-tête
                if len(row) >= 2:
                    name = row[0].strip()
                    
                    # Si l'étudiant est dans la nouvelle liste et a des médailles
                    if name in students and students[name] > 0:
                        updated_students[name] = students[name]
                        # Mettre à jour la cellule avec le nouveau nombre de médailles
                        cell = self.sheet.find(name)
                        self.sheet.update_cell(cell.row, 2, students[name])
                    
                    # Si l'étudiant a été supprimé (0 médailles), supprimer la ligne
                    elif name in students and students[name] <= 0:
                        cell = self.sheet.find(name)
                        self.sheet.delete_row(cell.row)
            
            # Ajouter les nouveaux étudiants qui n'étaient pas dans la feuille
            for name, medals in students.items():
                if name not in updated_students and medals > 0:
                    self.sheet.append_row([name, medals])
            
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des étudiants : {e}")

    def format_student_list(self, students):
        def get_year(medals):
            if 0 <= medals < 7:
                return "Première années"
            elif 7 <= medals < 18:
                return "Deuxième années"
            elif 18 <= medals < 30:
                return "Troisième années"
            else:
                return "Quatrième années"

        # Trier les étudiants par nombre de médailles
        sorted_students = sorted(students.items(), key=lambda x: x[1], reverse=True)
        
        # Préparer les années
        years = {
            "Quatrième années": [], 
            "Troisième années": [], 
            "Deuxième années": [], 
            "Première années": []
        }

        # Répartir les étudiants par année
        for name, medals in sorted_students:
            year = get_year(medals)
            years[year].append(f"  - ***{name} :** {medals} médailles*")

        # Construire le message
        message = "## ✮ Liste des personnages et leurs médailles ✮\n** **\n"  
        for i, (year, students_list) in enumerate(years.items()):
            if students_list:
                message += f"- **{year} :**\n" + "\n".join(students_list)
                if i < len(years) - 1:  
                    message += "\n\n"  
                else:
                    message += "\n"  

        return message.rstrip()

    def get_year(self, medals):
        if 0 <= medals < 7:
            return 1
        elif 7 <= medals < 18:
            return 2
        elif 18 <= medals < 30:
            return 3
        else:
            return 4

    @app_commands.command(name="medaille", description="Ajouter des médailles à un ou plusieurs élèves")
    async def add_medal(self, interaction: discord.Interaction, noms: str, montant: float):
        # Vérification des permissions en premier
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        # Defer après la vérification des permissions
        await interaction.response.defer(ephemeral=False)

        students = self.load_students()
        noms_list = [nom.strip() for nom in noms.split(',')]
        
        embeds = []

        for nom in noms_list:
            old_medals = students.get(nom, 0)
            if nom in students:
                students[nom] += montant
            else:
                students[nom] = montant
        
            new_medals = students[nom]
            
            embed = discord.Embed(
                title=nom,
                description=f"**{montant}** médailles ajoutées. Total actuel : **{new_medals}** médailles.",
                color=0x8543f7
            )
        
            embeds.append(embed)
        
            await self.check_and_send_year_change_alert(interaction.guild, old_medals, new_medals, nom)

        self.save_students(students)
        await self.update_medal_inventory()

        # Utilisez followup pour envoyer les embeds
        await interaction.followup.send(embeds=embeds)

    @app_commands.command(name="unmedaille", description="Retirer des médailles à un ou plusieurs élèves")
    async def remove_medal(self, interaction: discord.Interaction, noms: str, montant: float):
        await interaction.response.defer()  # Défer l'interaction pour éviter un timeout
        
        # Vérification des permissions
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        # Charger les étudiants existants
        students = self.load_students()
        noms_list = [nom.strip() for nom in noms.split(',')]
        
        embeds = []

        for nom in noms_list:
            if nom in students:
                old_medals = students[nom]
                students[nom] -= montant
                
                if students[nom] <= 0:
                    # Supprimer directement la ligne de Google Sheets
                    try:
                        cell = self.sheet.find(nom)
                        self.sheet.delete_row(cell.row)  # Suppression de la ligne
                        del students[nom]  # Supprimer également de la liste locale
                        embed = discord.Embed(
                            title=nom,
                            description=f"**{montant}** médailles retirées. {nom} a été supprimé de la liste car son total est de 0 ou moins.",
                            color=0xFF0000
                        )
                    except gspread.exceptions.CellNotFound:
                        embed = discord.Embed(
                            title="Erreur",
                            description=f"Impossible de trouver {nom} dans la feuille pour suppression.",
                            color=0xFF0000
                        )
                else:
                    # Mettre à jour le nombre de médailles si > 0
                    self.sheet.update_cell(self.sheet.find(nom).row, 2, students[nom])
                    embed = discord.Embed(
                        title=nom,
                        description=f"**{montant}** médailles retirées. Total actuel : **{students[nom]}** médailles.",
                        color=0x8543f7
                    )
            else:
                # Si l'élève n'est pas trouvé dans la liste
                embed = discord.Embed(
                    title="Erreur",
                    description=f"{nom} n'est pas dans la liste des élèves.",
                    color=0xFF0000
                )
            
            embeds.append(embed)

        # Mettre à jour l'inventaire après toutes les modifications
        await self.update_medal_inventory()

        # Envoyer les résultats sous forme d'embed
        await interaction.followup.send(embeds=embeds)

    async def update_medal_inventory(self):
        students = self.load_students()
        message_content = self.format_student_list(students)
        
        channel = self.bot.get_channel(self.CHANNEL_ID)
        message = await channel.fetch_message(self.MESSAGE_ID)
        await message.edit(content=message_content)

    async def check_and_send_year_change_alert(self, guild, old_medals, new_medals, character_name):
        old_year = self.get_year(old_medals)
        new_year = self.get_year(new_medals)
        
        if new_year > old_year:
            alert_channel = guild.get_channel(self.ALERT_CHANNEL_ID)
            if alert_channel:
                member = next((m for m in guild.members if character_name.lower() in m.display_name.lower()), None)
                
                if member:
                    message = f"Félicitations à **{member.mention}** ({character_name}) pour son passage à la {new_year}ème année !"
                else:
                    message = f"Félicitations à **{character_name}** pour son passage à la {new_year}ème année !"
                
                await alert_channel.send(message)

async def setup(bot):
    await bot.add_cog(Inventory(bot))
    print("Cog Inventaire chargé avec succès")