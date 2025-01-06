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
from gspread.exceptions import CellNotFound
import asyncio
import datetime

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
        
        # Initialisation de la feuille d'historique
        try:
            self.history_sheet = self.spreadsheet.worksheet("Historique")
        except:
            # Créer la feuille si elle n'existe pas
            self.history_sheet = self.spreadsheet.add_worksheet("Historique", 1000, 5)
            # Ajouter les en-têtes
            self.history_sheet.update('A1:E1', [['Date', 'Nom', 'Modification', 'Total', 'Modifié par']])
    
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

    async def async_load_students(self):
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self.sheet.get_all_values)
            
            students = {}
            for row in data[1:]:
                if len(row) >= 2 and row[0].strip():
                    try:
                        medals = float(row[1]) if row[1].strip() else 0
                        students[row[0].strip()] = medals
                    except ValueError:
                        print(f"Impossible de convertir les médailles pour {row[0]}: {row[1]}")
            return students
        except Exception as e:
            print(f"Erreur lors du chargement des étudiants : {e}")
            return {}

    async def async_save_students(self, students):
        try:
            loop = asyncio.get_event_loop()
            all_data = await loop.run_in_executor(None, self.sheet.get_all_values)
            updates = []
            
            for name, medals in students.items():
                try:
                    cell = await loop.run_in_executor(None, self.sheet.find, name)
                    if medals > 0:
                        updates.append({
                            'range': f'B{cell.row}',
                            'values': [[medals]]
                        })
                except CellNotFound:
                    if medals > 0:
                        updates.append({
                            'range': f'A{len(all_data) + 1}:B{len(all_data) + 1}',
                            'values': [[name, medals]]
                        })
            
            if updates:
                await loop.run_in_executor(None, self.sheet.batch_update, updates)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des étudiants : {e}")
            raise

    async def async_log_medal_change(self, name: str, change: float, new_total: float, modified_by: str):
        try:
            date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            new_row = [date, name, f"+{change}" if change > 0 else str(change), str(new_total), modified_by]
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.history_sheet.insert_row, new_row, 2)
        except Exception as e:
            print(f"Erreur lors de l'enregistrement dans l'historique : {e}")

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

        def format_medals(medals):
            # Pour les nombres entiers, convertir en int pour supprimer le .0
            if medals.is_integer():
                medals = int(medals)
            # Gérer le singulier/pluriel
            return f"{medals} médaille" if medals == 1 else f"{medals} médailles"

        sorted_students = sorted(students.items(), key=lambda x: x[1], reverse=True)
        
        years = {
            "Quatrième années": [], 
            "Troisième années": [], 
            "Deuxième années": [], 
            "Première années": []
        }

        for name, medals in sorted_students:
            year = get_year(medals)
            years[year].append(f"  - ***{name} :** {format_medals(medals)}*")

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
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        
        try:
            students = await self.async_load_students()
            noms_list = [nom.strip() for nom in noms.split(',')]
            embeds = []

            for nom in noms_list:
                old_medals = students.get(nom, 0)
                students[nom] = old_medals + montant
                new_medals = students[nom]
                
                await self.async_log_medal_change(nom, montant, new_medals, str(interaction.user))
                
                embed = discord.Embed(
                    title=nom,
                    description=f"**{montant}** médailles ajoutées. Total actuel : **{new_medals}** médailles.",
                    color=0x8543f7
                )
                embeds.append(embed)
                
                await self.check_and_send_year_change_alert(interaction.guild, old_medals, new_medals, nom)

            await self.async_save_students(students)
            await self.update_medal_inventory()
            await interaction.followup.send(embeds=embeds)
            
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue: {str(e)}", ephemeral=True)

    @app_commands.command(name="unmedaille", description="Retirer des médailles à un ou plusieurs élèves")
    async def remove_medal(self, interaction: discord.Interaction, noms: str, montant: float):
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        
        try:
            students = await self.async_load_students()
            noms_list = [nom.strip() for nom in noms.split(',')]
            embeds = []
            loop = asyncio.get_event_loop()

            for nom in noms_list:
                if nom in students:
                    old_medals = students[nom]
                    students[nom] -= montant
                    
                    await self.async_log_medal_change(nom, -montant, max(0, students[nom]), str(interaction.user))
                    
                    if students[nom] <= 0:
                        try:
                            cell = await loop.run_in_executor(None, self.sheet.find, nom)
                            await loop.run_in_executor(None, self.sheet.delete_row, cell.row)
                            del students[nom]
                            embed = discord.Embed(
                                title=nom,
                                description=f"**{montant}** médailles retirées. {nom} a été supprimé de la liste.",
                                color=0xFF0000
                            )
                        except Exception as e:
                            embed = discord.Embed(
                                title="Erreur",
                                description=f"Erreur lors de la suppression de {nom}: {str(e)}",
                                color=0xFF0000
                            )
                    else:
                        students[nom] = max(0, students[nom])
                        embed = discord.Embed(
                            title=nom,
                            description=f"**{montant}** médailles retirées. Total actuel : **{students[nom]}** médailles.",
                            color=0x8543f7
                        )
                else:
                    embed = discord.Embed(
                        title="Erreur",
                        description=f"{nom} n'est pas dans la liste des élèves.",
                        color=0xFF0000
                    )
                embeds.append(embed)

            await self.async_save_students(students)
            await self.update_medal_inventory()
            await interaction.followup.send(embeds=embeds)
            
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue: {str(e)}", ephemeral=True)

    async def update_medal_inventory(self):
        try:
            async with asyncio.timeout(30):  # timeout de 30 secondes
                students = self.load_students()
                message_content = self.format_student_list(students)
                
                channel = self.bot.get_channel(self.CHANNEL_ID)
                message = await channel.fetch_message(self.MESSAGE_ID)
                await message.edit(content=message_content)
        except asyncio.TimeoutError:
            print("Timeout lors de la mise à jour de l'inventaire")
        except Exception as e:
            print(f"Erreur lors de la mise à jour de l'inventaire : {e}")

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