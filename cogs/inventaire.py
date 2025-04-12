import os
import discord
from discord import app_commands
from discord.ext import commands
import json
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from gspread.exceptions import CellNotFound
import datetime
import time
import traceback

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
        self.client = None
        self.spreadsheet = None
        self.sheet = None
        self.history_sheet = None
        self.setup_google_sheets()

    def setup_google_sheets(self, max_retries=3, retry_delay=5):
        """Initialize Google Sheets connection with retry mechanism"""
        for attempt in range(max_retries):
            try:
                # Charger les identifiants de service depuis la chaîne JSON d'environnement
                creds = ServiceAccountCredentials.from_service_account_info(
                    json.loads(os.getenv('SERVICE_ACCOUNT_JSON')), 
                    scopes=self.SCOPES
                )
                self.client = gspread.authorize(creds)
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
                
                print("Successfully connected to Google Sheets")
                return
            except gspread.exceptions.APIError as e:
                if attempt < max_retries - 1:
                    print(f"Failed to connect to Google Sheets (attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print(f"Failed to connect to Google Sheets after {max_retries} attempts")
                    # Instead of raising the error, we'll just print it and continue
                    print(f"Error: {str(e)}")
            except Exception as e:
                print(f"Unexpected error during Google Sheets setup: {str(e)}")
                traceback.print_exc()
                break

    async def ensure_sheet_connection(self):
        """Ensure we have a valid connection to the sheet"""
        if self.sheet is None:
            self.setup_google_sheets()
        
        # If still None, raise an error that we can handle
        if self.sheet is None:
            raise RuntimeError("Unable to establish connection to Google Sheets")

    def load_students(self):
        try:
            data = self.sheet.get_all_values()
            students = {}
            for row in data[1:]:  # Ignore la première ligne (en-têtes)
                if len(row) >= 2 and row[0].strip():
                    try:
                        medals = float(row[1]) if row[1].strip() else 0
                        # Convertit l'ID en int si présent, None sinon
                        user_id = int(row[2].replace("'", "")) if len(row) > 2 and row[2].strip() else None
                        students[row[0].strip()] = {'medals': medals, 'user_id': user_id}
                    except ValueError:
                        print(f"Impossible de convertir les données pour {row[0]}")
            return students
        except Exception as e:
            print(f"Erreur lors du chargement des étudiants : {e}")
            return {}

    def save_students(self, students):
        try:
            # Récupérer toutes les données actuelles
            all_data = self.sheet.get_all_values()
            header = all_data[0]  # Sauvegarder l'en-tête
            
            # Préparer les nouvelles données
            new_data = [header]  # Commencer avec l'en-tête
            
            # Ajouter toutes les entrées des étudiants
            for name, data in students.items():
                medals = data['medals']
                user_id = str(data['user_id']) if data['user_id'] else ''
                if medals > 0:  # Ne garder que les étudiants avec des médailles > 0
                    new_data.append([name, str(medals), user_id])
            
            # Mettre à jour la feuille entière
            self.sheet.clear()  # Effacer toutes les données
            self.sheet.update('A1', new_data)  # Mettre à jour avec les nouvelles données
            
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des étudiants : {e}")
            raise  # Propager l'erreur pour la gestion d'erreur

    def format_student_list(self, students):
        sorted_students = sorted(students.items(), key=lambda x: x[1]['medals'], reverse=True)
        
        years = {
            "Quatrième année": [], 
            "Troisième année": [], 
            "Deuxième année": [], 
            "Première année": []
        }

        for name, data in sorted_students:
            level = self.get_year(data['medals'])
            if level == 1:
                category = "Première année"
            elif level == 2:
                category = "Deuxième année"
            elif level == 3:
                category = "Troisième année"
            else:
                category = "Quatrième année"
            years[category].append(f"  - ***{name} :** {self.format_medals_count(data['medals'])}*")
        
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

    def format_medals_count(self, count: float) -> str:
        # Formater le nombre de médailles avec la bonne forme singulier/pluriel
        if isinstance(count, float) and count.is_integer():
            count = int(count)
        return f"{count} médaille" if count == 1 else f"{count} médailles"

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
        # Vérification des permissions en premier
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        # Defer après la vérification des permissions
        await interaction.response.defer(ephemeral=False)

        students = self.load_students()
        noms_list = [nom.strip() for nom in noms.split(',')]
        
        embeds = []

        try:
            for nom in noms_list:
                old_medals = students.get(nom, {'medals': 0})['medals']
                if nom in students:
                    students[nom]['medals'] += montant
                else:
                    students[nom] = {'medals': montant, 'user_id': None}
                
                new_medals = students[nom]['medals']
                self.log_medal_change(nom, montant, new_medals, str(interaction.user))
                
                # Construire la description avec la bonne conjugaison singulier/pluriel
                added_count = montant
                if added_count.is_integer(): added_count = int(added_count)
                total_count = new_medals
                if total_count.is_integer(): total_count = int(total_count)
                desc_change = "ajoutée" if added_count == 1 else "ajoutées"
                desc_total_word = "médaille" if total_count == 1 else "médailles"
                description = f"**{added_count}** médaille{'s' if added_count != 1 else ''} {desc_change}. Total actuel : **{total_count}** {desc_total_word}."
                embed = discord.Embed(title=nom, description=description, color=0x6d5380)
                embeds.append(embed)
                
                # Sauvegarder immédiatement après chaque modification
                self.save_students(students)
                await self.check_and_send_year_change_alert(interaction.guild, old_medals, new_medals, nom)

            # Mettre à jour l'affichage une seule fois à la fin
            await self.update_medal_inventory()
            
            await interaction.followup.send(embeds=embeds)
        except Exception as e:
            print(f"Erreur dans add_medal : {e}")
            await interaction.followup.send("Une erreur s'est produite lors de l'ajout des médailles.", ephemeral=True)

    @app_commands.command(name="unmedaille", description="Retirer des médailles à un ou plusieurs élèves")
    async def remove_medal(self, interaction: discord.Interaction, noms: str, montant: float):
        # Vérification des permissions
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return
            
        # Défer l'interaction après la vérification des permissions
        await interaction.response.defer()

        # Charger les étudiants existants
        students = self.load_students()
        noms_list = [nom.strip() for nom in noms.split(',')]
        
        embeds = []

        for nom in noms_list:
            if nom in students:
                old_medals = students[nom]['medals']
                students[nom]['medals'] -= montant
                
                # Enregistrer dans l'historique avant toute suppression potentielle
                self.log_medal_change(nom, -montant, max(0, students[nom]['medals']), str(interaction.user))
                
                if students[nom]['medals'] <= 0:
                    # Supprimer directement la ligne de Google Sheets
                    try:
                        cell = self.sheet.find(nom)
                        self.sheet.delete_row(cell.row)  # Suppression de la ligne
                        del students[nom]  # Supprimer également de la liste locale
                        # Construire le message de suppression avec pluriel adapté
                        removed_count = montant
                        if removed_count.is_integer(): removed_count = int(removed_count)
                        desc_change = "retirée" if removed_count == 1 else "retirées"
                        description = f"**{removed_count}** médaille{'s' if removed_count != 1 else ''} {desc_change}. {nom} a été supprimé de la liste car son total est de 0 ou moins."
                        embed = discord.Embed(title=nom, description=description, color=0x6d5380)
                    except CellNotFound:
                        embed = discord.Embed(
                            title="Erreur",
                            description=f"Impossible de trouver {nom} dans la feuille pour suppression.",
                            color=0x6d5380
                        )
                else:
                    # Mettre à jour le nombre de médailles si > 0
                    self.sheet.update_cell(self.sheet.find(nom).row, 2, students[nom]['medals'])
                    # Construire le message de retrait avec pluriel adapté
                    removed_count = montant
                    if removed_count.is_integer(): removed_count = int(removed_count)
                    total_count = students[nom]['medals']
                    if total_count.is_integer(): total_count = int(total_count)
                    desc_change = "retirée" if removed_count == 1 else "retirées"
                    desc_total_word = "médaille" if total_count == 1 else "médailles"
                    description = f"**{removed_count}** médaille{'s' if removed_count != 1 else ''} {desc_change}. Total actuel : **{total_count}** {desc_total_word}."
                    embed = discord.Embed(title=nom, description=description, color=0x6d5380)
            else:
                # Si l'élève n'est pas trouvé dans la liste
                embed = discord.Embed(
                    title="Erreur",
                    description=f"{nom} n'est pas dans la liste des élèves.",
                    color=0x6d5380
                )
            
            embeds.append(embed)

        # Mettre à jour l'inventaire après toutes les modifications
        await self.update_medal_inventory()

        # Envoyer les résultats sous forme d'embed
        await interaction.followup.send(embeds=embeds)

    @app_commands.command(name="lier", description="Associer un personnage à un utilisateur Discord")
    async def link_character(self, interaction: discord.Interaction, nom: str, utilisateur: discord.Member):
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        await interaction.response.defer()
        
        students = self.load_students()
        if nom not in students:
            await interaction.followup.send(f"Le personnage {nom} n'existe pas dans la liste.", ephemeral=True)
            return

        # Mettre à jour l'ID utilisateur
        students[nom]['user_id'] = utilisateur.id
        self.save_students(students)

        embed = discord.Embed(
            title="Association réussie",
            description=f"Le personnage **{nom}** a été associé à {utilisateur.mention}",
            color=0x6d5380
        )
        await interaction.followup.send(embed=embed)

    async def update_medal_inventory(self):
        try:
            channel = self.bot.get_channel(self.CHANNEL_ID)
            if not channel:
                print(f"Impossible de trouver le canal {self.CHANNEL_ID}")
                return

            students = self.load_students()
            message_content = self.format_student_list(students)

            try:
                message = await channel.fetch_message(self.MESSAGE_ID)
                await message.edit(content=message_content)
            except discord.NotFound:
                # Si le message n'existe pas, en créer un nouveau
                new_message = await channel.send(message_content)
                self.MESSAGE_ID = new_message.id
                print(f"Nouveau message d'inventaire créé avec l'ID: {self.MESSAGE_ID}")
            except Exception as e:
                print(f"Erreur lors de la mise à jour du message : {e}")
                # Tenter de créer un nouveau message
                new_message = await channel.send(message_content)
                self.MESSAGE_ID = new_message.id

        except Exception as e:
            print(f"Erreur critique dans update_medal_inventory : {e}")

    async def check_and_send_year_change_alert(self, guild, old_medals, new_medals, character_name):
        old_year = self.get_year(old_medals)
        new_year = self.get_year(new_medals)
        
        if new_year > old_year:
            alert_channel = guild.get_channel(self.ALERT_CHANNEL_ID)
            if alert_channel:
                # Charger les données des étudiants pour obtenir l'ID de l'utilisateur
                students = self.load_students()
                student_data = students.get(character_name, {})
                user_id = student_data.get('user_id')
                # Formater l'année (1ère année au lieu de 1ème année)
                year_suffix = "1ère" if new_year == 1 else f"{new_year}ème"
                
                if user_id:
                    # Si l'utilisateur est lié, on utilise son ID pour le ping
                    message = f"Félicitations à <@{user_id}> ({character_name}) pour son passage à la {year_suffix} année !"
                else:
                    # Si aucun utilisateur n'est lié, on affiche juste le nom du personnage
                    message = f"Félicitations à **{character_name}** pour son passage à la {year_suffix} année !"
                
                await alert_channel.send(message)

async def setup(bot):
    try:
        await bot.add_cog(Inventory(bot))
        print("Cog Inventory loaded successfully")
    except Exception as e:
        print(f"Error loading Inventory cog: {str(e)}")
        # Don't raise the error - this allows the bot to continue loading other cogs
        # even if this one fails
