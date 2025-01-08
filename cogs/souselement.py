import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

class SubElementModal(discord.ui.Modal):
    def __init__(self, view, element):
        super().__init__(title=f"Ajouter un sous-élément pour {element}")
        self.view = view
        self.element = element
        self.sub_element = discord.ui.TextInput(
            label="Sous-élément",
            placeholder="Entrez le nom du sous-élément",
            required=True,
            max_length=100
        )
        self.add_item(self.sub_element)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.add_sub_element(interaction, self.element, self.sub_element.value)

class SousElements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_google_sheets()
        self.bot.loop.create_task(self.load_persistent_views())
        
    def setup_google_sheets(self):
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(
            eval(os.getenv('SERVICE_ACCOUNT_JSON')),
            scopes=scope
        )
        self.gc = gspread.authorize(credentials)
        self.sheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT')).sheet1

    def get_message_data(self, message_id):
        try:
            # Assurons-nous que message_id est une chaîne
            message_id = str(message_id)
            cells = self.sheet.findall(message_id, in_column=1)
            if not cells:
                print(f"Aucune donnée trouvée pour le message ID: {message_id}")
                # Initialiser des données par défaut si rien n'est trouvé
                return {
                    'channel_id': None,
                    'user_id': None,
                    'character_name': None,
                    'elements': {
                        'Eau': [], 'Feu': [], 'Vent': [], 'Terre': [], 'Espace': []
                    }
                }
            
            data = {
                'channel_id': None,
                'user_id': None,
                'character_name': None,
                'elements': {
                    'Eau': [], 'Feu': [], 'Vent': [], 'Terre': [], 'Espace': []
                }
            }
            
            rows = self.sheet.get_all_values()
            for cell in cells:
                row = rows[cell.row - 1]
                data['channel_id'] = int(row[1])
                data['user_id'] = int(row[2])
                data['character_name'] = row[3]
                element = row[4]
                sub_element = row[5]
                if sub_element and element in data['elements']:
                    if sub_element not in data['elements'][element]:
                        data['elements'][element].append(sub_element)
                        
            return data
        except Exception as e:
            print(f"Erreur détaillée lors de la récupération des données: {str(e)}")
            return None

    def save_message_data(self, message_id, data):
        try:
            # Supprimer les anciennes entrées
            cells = self.sheet.findall(str(message_id), in_column=1)
            rows_to_delete = [cell.row for cell in cells]
            for row in sorted(rows_to_delete, reverse=True):
                self.sheet.delete_rows(row)

            # Préparer les nouvelles lignes
            rows_to_add = []
            for element, sub_elements in data['elements'].items():
                if not sub_elements:
                    rows_to_add.append([
                        str(message_id),
                        str(data['channel_id']),
                        str(data['user_id']),
                        data['character_name'],
                        element,
                        ''
                    ])
                for sub_element in sub_elements:
                    rows_to_add.append([
                        str(message_id),
                        str(data['channel_id']),
                        str(data['user_id']),
                        data['character_name'],
                        element,
                        sub_element
                    ])

            if rows_to_add:
                self.sheet.append_rows(rows_to_add)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des données: {e}")

    async def load_persistent_views(self):
        await self.bot.wait_until_ready()
        all_data = self.sheet.get_all_values()
        processed_messages = set()
        
        for row in all_data[1:]:  # Skip header row
            message_id = row[0]
            if message_id in processed_messages:
                continue
                
            processed_messages.add(message_id)
            try:
                channel = self.bot.get_channel(int(row[1]))
                if channel:
                    message = await channel.fetch_message(int(message_id))
                    view = SousElementsView(self, row[3])
                    self.bot.add_view(view, message_id=int(message_id))
            except Exception as e:
                print(f"Erreur lors du chargement du message {message_id}: {e}")

    async def update_message(self, message, data):
        def format_elements(elements):
            if not elements:
                return "-\n"
            return ''.join(f'- {item}\n' for item in elements)

        description = (
            "# Sous-éléments :\n"
            "** **\n"
            "## __Eau :__\n"
            f"{format_elements(data['elements']['Eau'])}\n"
            "## __Feu :__\n"
            f"{format_elements(data['elements']['Feu'])}\n"
            "## __Vent :__\n"
            f"{format_elements(data['elements']['Vent'])}\n"
            "## __Terre :__\n"
            f"{format_elements(data['elements']['Terre'])}\n"
            "## __Espace :__\n"
            f"{format_elements(data['elements']['Espace'])}\n"
        )
        
        embed = discord.Embed(
            title=f"Sous-éléments de {data['character_name']}", 
            description=description,
            color=0x8543f7
        )
        await message.edit(embed=embed)

    @app_commands.command(name='sous-éléments', description="Créer un message pour gérer les sous-éléments d'un personnage")
    async def sous_elements(self, interaction: discord.Interaction, character_name: str):
        await interaction.response.defer()

        description = (
            "# Sous-éléments :\n"
            "** **\n"
            "## __Eau :__\n"
            "-\n\n"
            "## __Feu :__\n"
            "-\n\n"
            "## __Vent :__\n"
            "-\n\n"
            "## __Terre :__\n"
            "-\n\n"
            "## __Espace :__\n"
            "-\n"
        )
        embed = discord.Embed(
            title=f"Sous-éléments de {character_name}", 
            description=description, 
            color=0x8543f7
        )
    
        view = SousElementsView(self, character_name)
        message = await interaction.followup.send(embed=embed, view=view)

        data = {
            "channel_id": interaction.channel.id,
            "user_id": interaction.user.id,
            "character_name": character_name,
            "elements": {
                "Eau": [],
                "Feu": [],
                "Vent": [],
                "Terre": [],
                "Espace": []
            }
        }

        self.save_message_data(message.id, data)
        self.bot.add_view(view, message_id=message.id)

class SousElementsView(discord.ui.View):
    def __init__(self, cog, character_name):
        super().__init__(timeout=None)
        self.cog = cog
        self.character_name = character_name

        self.add_item(ElementButton("Eau", 0))
        self.add_item(ElementButton("Feu", 0))
        self.add_item(ElementButton("Vent", 0))
        self.add_item(ElementButton("Terre", 1))
        self.add_item(ElementButton("Espace", 1))

    async def add_sub_element(self, interaction: discord.Interaction, element: str, sub_element: str):
        message_id = str(interaction.message.id)
        data = self.cog.get_message_data(message_id)

        if not data:
            await interaction.followup.send("Message data not found.", ephemeral=True)
            return

        if interaction.user.id != data['user_id']:
            await interaction.followup.send("Tu n'es pas autorisé à ajouter des sous-éléments.", ephemeral=True)
            return

        data['elements'][element].append(sub_element)
        self.cog.save_message_data(message_id, data)

        await self.cog.update_message(interaction.message, data)
        await interaction.followup.send(f"Sous-élément '{sub_element}' ajouté à {element}.", ephemeral=True)

class ElementButton(discord.ui.Button):
    def __init__(self, label, row):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{label.lower()}_button", row=row)

    async def callback(self, interaction: discord.Interaction):
        modal = SubElementModal(self.view, self.label)
        await interaction.response.send_modal(modal)

async def setup(bot):
    await bot.add_cog(SousElements(bot))
    print("Cog Souselements chargé avec succès")

