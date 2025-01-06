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
        
        # Ajout des IDs des rôles d'année
        self.YEAR_ROLES = {
            1: 1018442196904583188,  # Première année
            2: 1018442219612541019,  # Deuxième année
            3: 1018442250851725333,  # Troisième année
            4: 1018442270548176987   # Quatrième année
        }
        
        # Ajout des rôles spéciaux pour le passage en 3ème année
        self.THIRD_YEAR_SPECIAL = {
            'add': 1032713329862512670,
            'remove': 1032713246949515344
        }
        
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
            
        # S'assurer que la colonne Discord ID existe
        headers = self.sheet.row_values(1)
        if 'Discord ID' not in headers:
            self.sheet.insert_cols([[]], 3)  # Ajouter une nouvelle colonne après les médailles
            self.sheet.update('C1', 'Discord ID')
    
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
                        discord_id = row[2].strip() if len(row) > 2 else None
                        students[row[0].strip()] = {
                            'medals': medals,
                            'discord_id': discord_id
                        }
                    except ValueError:
                        print(f"Impossible de convertir les médailles pour {row[0]}: {row[1]}")
            
            return students
        except Exception as e:
            print(f"Erreur lors du chargement des étudiants : {e}")
            return {}

    def save_students(self, students):
        try:
            # Convertir toutes les données en une liste de listes
            all_data = self.sheet.get_all_values()
            headers = all_data[0]  # Première ligne = en-têtes
            
            # Créer un dictionnaire des lignes existantes par nom
            existing_rows = {row[0].strip(): idx + 1 for idx, row in enumerate(all_data[1:], start=1)}
            
            # Préparer les mises à jour
            updates = []
            for name, data in students.items():
                row_data = [name, data['medals'], data['discord_id'] or '']
                
                if name in existing_rows:
                    # Mise à jour d'une ligne existante
                    row_num = existing_rows[name] + 1
                    updates.append({
                        'range': f'A{row_num}:C{row_num}',
                        'values': [row_data]
                    })
                else:
                    # Ajout d'une nouvelle ligne
                    self.sheet.append_row(row_data)
            
            # Exécuter toutes les mises à jour en une seule fois
            if updates:
                self.sheet.batch_update(updates)
                
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des étudiants : {e}")
            raise e  # Propager l'erreur pour déboguer

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

        sorted_students = sorted(students.items(), key=lambda x: x[1]['medals'], reverse=True)
        
        years = {
            "Quatrième années": [], 
            "Troisième années": [], 
            "Deuxième années": [], 
            "Première années": []
        }

        for name, data in sorted_students:
            year = get_year(data['medals'])
            years[year].append(f"  - ***{name} :** {format_medals(data['medals'])}*")

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

    def log_medal_change(self, name: str, change: float, new_total: float, modified_by: str):
        try:
            # Format de la date: DD/MM/YYYY HH:MM
            date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            
            # Préparer la nouvelle ligne
            new_row = [
                date,
                name,
                f"+{change}" if change > 0 else str(change),
                str(new_total),
                modified_by
            ]
            
            # Insérer la nouvelle ligne après les en-têtes
            self.history_sheet.insert_row(new_row, 2)  # 2 pour insérer après les en-têtes
        except Exception as e:
            print(f"Erreur lors de l'enregistrement dans l'historique : {e}")

    @app_commands.command(name="medaille", description="Ajouter des médailles à un ou plusieurs élèves")
    async def add_medal(self, interaction: discord.Interaction, noms: str, montant: float):
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        try:
            students = self.load_students()
            noms_list = [nom.strip() for nom in noms.split(',')]
            embeds = []

            for nom in noms_list:
                student_data = students.get(nom, {'medals': 0, 'discord_id': None})
                old_medals = student_data['medals']
                new_medals = old_medals + montant
                
                students[nom] = {
                    'medals': new_medals,
                    'discord_id': student_data['discord_id']
                }

                # Créer l'embed pour ce student
                embed = discord.Embed(
                    title=nom,
                    description=f"**{montant}** médailles ajoutées. Total actuel : **{new_medals}** médailles.",
                    color=0x8543f7
                )
                embeds.append(embed)

                # Gestion des changements d'année
                if students[nom]['discord_id']:
                    member = interaction.guild.get_member(int(students[nom]['discord_id']))
                    await self.check_and_send_year_change_alert(interaction.guild, old_medals, new_medals, nom, member)

                # Enregistrer dans l'historique
                self.log_medal_change(nom, montant, new_medals, str(interaction.user))

            # Sauvegarder toutes les modifications
            self.save_students(students)
            await self.update_medal_inventory()
            
            await interaction.followup.send(embeds=embeds)

        except Exception as e:
            print(f"Erreur lors de l'ajout de médailles : {e}")
            await interaction.followup.send("Une erreur est survenue lors de l'ajout des médailles.", ephemeral=True)

    @app_commands.command(name="unmedaille", description="Retirer des médailles à un ou plusieurs élèves")
    async def remove_medal(self, interaction: discord.Interaction, noms: str, montant: float):
        try:
            if not self.bot.check_role(interaction):
                await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
                return

            await interaction.response.defer()
            
            students = self.load_students()
            noms_list = [nom.strip() for nom in noms.split(',')]
            embeds = []

            for nom in noms_list:
                try:
                    if nom in students:
                        old_medals = students[nom]['medals']
                        new_medals = max(0, old_medals - montant)
                        
                        self.log_medal_change(nom, -montant, new_medals, str(interaction.user))
                        
                        if new_medals <= 0:
                            cell = self.sheet.find(nom)
                            self.sheet.delete_row(cell.row)
                            del students[nom]
                            embed = discord.Embed(
                                title=nom,
                                description=f"**{montant}** médailles retirées. {nom} a été supprimé de la liste.",
                                color=0xFF0000
                            )
                        else:
                            students[nom]['medals'] = new_medals
                            embed = discord.Embed(
                                title=nom,
                                description=f"**{montant}** médailles retirées. Total actuel : **{new_medals}** médailles.",
                                color=0x8543f7
                            )
                    else:
                        embed = discord.Embed(
                            title="Erreur",
                            description=f"{nom} n'est pas dans la liste des élèves.",
                            color=0xFF0000
                        )
                    embeds.append(embed)
                except Exception as e:
                    print(f"Erreur pour l'élève {nom}: {e}")
                    continue

            # Sauvegarder une seule fois à la fin
            self.save_students(students)
            await self.update_medal_inventory()
            
            await interaction.followup.send(embeds=embeds)
            
        except Exception as e:
            print(f"Erreur globale dans remove_medal: {e}")
            await interaction.followup.send("Une erreur est survenue lors du retrait des médailles.", ephemeral=True)

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

    async def update_member_roles(self, member, old_year, new_year):
        if not member:
            return
            
        try:
            # Récupérer les objets role
            old_role = member.guild.get_role(self.YEAR_ROLES[old_year])
            new_role = member.guild.get_role(self.YEAR_ROLES[new_year])
            
            # Enlever l'ancien rôle si présent
            if old_role and old_role in member.roles:
                await member.remove_roles(old_role)
                
            # Ajouter le nouveau rôle si pas déjà présent
            if new_role and new_role not in member.roles:
                await member.add_roles(new_role)
                
            # Gestion spéciale pour le passage en 3ème année
            if old_year == 2 and new_year == 3:
                role_to_remove = member.guild.get_role(self.THIRD_YEAR_SPECIAL['remove'])
                role_to_add = member.guild.get_role(self.THIRD_YEAR_SPECIAL['add'])
                
                if role_to_remove and role_to_remove in member.roles:
                    await member.remove_roles(role_to_remove)
                if role_to_add and role_to_add not in member.roles:
                    await member.add_roles(role_to_add)
                    
        except Exception as e:
            print(f"Erreur lors de la mise à jour des rôles : {e}")

    async def check_and_send_year_change_alert(self, guild, old_medals, new_medals, character_name, member=None):
        old_year = self.get_year(old_medals)
        new_year = self.get_year(new_medals)
        
        if new_year > old_year:
            try:
                alert_channel = guild.get_channel(self.ALERT_CHANNEL_ID)
                if alert_channel:
                    if member:
                        await self.update_member_roles(member, old_year, new_year)
                        message = f"Félicitations à **{member.mention}** ({character_name}) pour son passage à la {new_year}ème année !"
                    else:
                        message = f"Félicitations à **{character_name}** pour son passage à la {new_year}ème année !"
                    
                    await alert_channel.send(message)
                else:
                    print(f"Canal d'alerte introuvable (ID: {self.ALERT_CHANNEL_ID})")
            except Exception as e:
                print(f"Erreur lors de l'envoi de l'alerte de changement d'année : {e}")

    @app_commands.command(name="lier", description="Lier un personnage à un utilisateur Discord")
    async def link_character(self, interaction: discord.Interaction, nom: str, membre: discord.Member):
        try:
            if not self.bot.check_role(interaction):
                await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
                return

            await interaction.response.defer()
            
            students = self.load_students()
            if nom in students:
                students[nom]['discord_id'] = str(membre.id)
                self.save_students(students)
                
                # Vérifier immédiatement si un changement d'année est nécessaire
                current_medals = students[nom]['medals']
                await self.check_and_send_year_change_alert(
                    interaction.guild,
                    0,  # On part de 0 car c'est une nouvelle liaison
                    current_medals,
                    nom,
                    membre
                )
                
                await interaction.followup.send(f"Le personnage {nom} a été lié à {membre.mention}")
            else:
                await interaction.followup.send(f"Le personnage {nom} n'existe pas dans la liste.", ephemeral=True)
        except Exception as e:
            print(f"Erreur lors de la liaison du personnage : {e}")
            await interaction.followup.send("Une erreur est survenue lors de la liaison du personnage.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Inventory(bot))
    print("Cog Inventaire chargé avec succès")