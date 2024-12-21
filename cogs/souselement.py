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
        # Initialisation de la connexion Google Sheets
        self.gc = self.setup_google_sheets()
        self.sheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT')).sheet1
        self.bot.loop.create_task(self.load_persistent_views())

    def setup_google_sheets(self):
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(
            eval(os.getenv('SERVICE_ACCOUNT_JSON')),
            scopes=scope
        )
        return gspread.authorize(credentials)

    def load_data(self):
        # Charger toutes les données du Google Sheet
        all_records = self.sheet.get_all_records()
        data = {}
        for record in all_records:
            message_id = str(record['message_id'])
            if message_id not in data:
                data[message_id] = {
                    'channel_id': record['channel_id'],
                    'user_id': record['user_id'],
                    'character_name': record['character_name'],
                    'elements': {
                        'Eau': [], 'Feu': [], 'Vent': [], 'Terre': [], 'Espace': []
                    }
                }
            element = record['element']
            sub_element = record['sub_element']
            if sub_element:
                data[message_id]['elements'][element].append(sub_element)
        return data

    def save_data(self, message_id, data):
        # Supprimer les anciennes entrées pour ce message_id
        self.sheet.delete_rows(
            self.find_rows_by_message_id(message_id)
        )
        
        # Ajouter les nouvelles données
        rows_to_add = []
        for element, sub_elements in data['elements'].items():
            if not sub_elements:
                rows_to_add.append([
                    message_id,
                    data['channel_id'],
                    data['user_id'],
                    data['character_name'],
                    element,
                    ''
                ])
            for sub_element in sub_elements:
                rows_to_add.append([
                    message_id,
                    data['channel_id'],
                    data['user_id'],
                    data['character_name'],
                    element,
                    sub_element
                ])
        
        if rows_to_add:
            self.sheet.append_rows(rows_to_add)
    
    def find_rows_by_message_id(self, message_id):
        cell_list = self.sheet.findall(str(message_id), in_column=1)
        return [cell.row for cell in cell_list]

    async def load_persistent_views(self):
        await self.bot.wait_until_ready()
        data = self.load_data()
        for message_id, message_data in data.items():
            channel = self.bot.get_channel(message_data['channel_id'])
            if channel:
                try:
                    message = await channel.fetch_message(int(message_id))
                    view = SousElementsView(self, message_data['character_name'])
                    self.bot.add_view(view, message_id=int(message_id))
                except Exception as e:
                    print(f"Erreur lors du chargement du message {message_id}: {e}")

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
        print(f"Message {message.id} sent in channel {interaction.channel.id}.")

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

        self.messages_data[str(message.id)] = data
        self.save_data_file()

        self.bot.add_view(view, message_id=message.id)
        print(f"Data for message {message.id} saved.")

    async def update_message(self, message, data):
        def format_elements(elements):
            if not elements:
                return "-\n"
            return ''.join(f'- {item}\n' for item in elements)

        description = (
            "# Sous-éléments :\n"
            "** **\n"
            "## __Eau :__\n"
            + format_elements(data['elements']['Eau']) + "\n"
            "## __Feu :__\n"
            + format_elements(data['elements']['Feu']) + "\n"
            "## __Vent :__\n"
            + format_elements(data['elements']['Vent']) + "\n"
            "## __Terre :__\n"
            + format_elements(data['elements']['Terre']) + "\n"
            "## __Espace :__\n"
            + format_elements(data['elements']['Espace']) + "\n"
        )
        
        embed = discord.Embed(
            title=f"Sous-éléments de {data['character_name']}",  # Utilisez 'character_name' au lieu de 'nom du personnage'
            description=description,
            color=0x8543f7
        )
        await message.edit(embed=embed)

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

        if message_id not in self.cog.messages_data:
            await interaction.followup.send("Message data not found.", ephemeral=True)
            return

        data = self.cog.messages_data[message_id]

        if interaction.user.id != data['user_id']:
            await interaction.followup.send("Tu n'es pas autorisé à ajouter des sous-éléments.", ephemeral=True)
            return

        data['elements'][element].append(sub_element)
        self.cog.save_data_file()

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