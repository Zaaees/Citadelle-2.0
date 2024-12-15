import os
import discord
from discord import app_commands
from discord.ext import commands
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from dotenv import load_dotenv
load_dotenv()

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.CHANNEL_ID = 1018159303422656582
        self.MESSAGE_ID = 1230199030412218398
        self.ALERT_CHANNEL_ID = 1085300906981085366
        
        # Configuration Google Drive
        self.SCOPES = ['https://www.googleapis.com/auth/drive.file']
        self.FILE_NAME = 'inventaire.json'
        
        # Initialisation du service Drive
        self.drive_service = self.get_drive_service()
        self.FILE_ID = self.find_or_create_file()

    def get_drive_service(self):
        try:
            # Récupération des credentials depuis une variable d'environnement
            if os.getenv('SERVICE_ACCOUNT_JSON'):
                import json
                import tempfile
                
                # Créer un fichier temporaire avec les credentials
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                    json.dump(json.loads(os.getenv('SERVICE_ACCOUNT_JSON')), temp_file)
                    temp_file_path = temp_file.name

                credentials = service_account.Credentials.from_service_account_file(
                    temp_file_path, scopes=self.SCOPES)
                
                # Supprimer le fichier temporaire
                os.unlink(temp_file_path)
            else:
                # Fallback pour le développement local
                credentials = service_account.Credentials.from_service_account_file(
                    'service-account.json', scopes=self.SCOPES)
            
            return build('drive', 'v3', credentials=credentials)
        
        except Exception as e:
            print(f"Erreur d'authentification Google Drive : {e}")
            return None

    def find_or_create_file(self):
        # Trouver ou créer le fichier sur Google Drive
        results = self.drive_service.files().list(
            q=f"name='{self.FILE_NAME}'", 
            spaces='drive',
            fields="files(id)"
        ).execute()
        files = results.get('files', [])

        if files:
            return files[0]['id']
        
        # Créer le fichier s'il n'existe pas
        file_metadata = {
            'name': self.FILE_NAME,
            'mimeType': 'application/json'
        }
        file = self.drive_service.files().create(
            body=file_metadata, 
            fields='id'
        ).execute()
        
        # Initialiser avec un JSON vide
        self.update_file_content({})
        return file['id']

    def load_students(self):
        try:
            # Télécharger le contenu du fichier depuis Google Drive
            request = self.drive_service.files().get_media(fileId=self.FILE_ID)
            file_content = request.execute().decode('utf-8')
            return json.loads(file_content or '{}')
        except Exception as e:
            print(f"Erreur lors du chargement des étudiants : {e}")
            return {}

    def update_file_content(self, content):
        try:
            # Mettre à jour le contenu du fichier sur Google Drive
            file_content = json.dumps(content, ensure_ascii=False, indent=2)
            media = io.BytesIO(file_content.encode('utf-8'))
            
            self.drive_service.files().update(
                fileId=self.FILE_ID,
                media_body=media,
                fields='id'
            ).execute()
        except Exception as e:
            print(f"Erreur lors de la mise à jour du fichier : {e}")

    def save_students(self, students):
        self.update_file_content(students)

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

        sorted_students = sorted(students.items(), key=lambda x: x[1], reverse=True)
        years = {"Quatrième années": [], "Troisième années": [], "Deuxième années": [], "Première années": []}

        for name, medals in sorted_students:
            year = get_year(medals)
            years[year].append(f"  - ***{name} :** {medals} médailles*")

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
        await interaction.response.defer()
        if not self.bot.check_role(interaction):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        students = self.load_students()
        noms_list = [nom.strip() for nom in noms.split(',')]
    
        embeds = []

        for nom in noms_list:
            if nom in students:
                students[nom] -= montant
            
                if students[nom] <= 0:
                    del students[nom]
                    embed = discord.Embed(
                        title=nom,
                        description=f"**{montant}** médailles retirées. {nom} a été retiré de la liste car son total est de 0 ou moins.",
                        color=0xFF0000
                    )
                else:
                    embed = discord.Embed(
                        title=nom,
                        description=f"**{montant}** médailles retirées. Total actuel : **{students[nom]}** médailles.",
                        color=0x8543f7
                    )
            else:
                embed = discord.Embed(title="Erreur", description=f"{nom} n'est pas dans la liste des élèves.", color=0xFF0000)
        
            embeds.append(embed)

        self.save_students(students)
        await self.update_medal_inventory()

        # Use followup instead of response
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