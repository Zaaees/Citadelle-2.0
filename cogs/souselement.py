import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

FORUM_ID = 1137670941820846150
THREAD_CHANNELS = {
    'Feu': 1137675742499573861,
    'Terre': 1137675703630970891,
    'Eau': 1137675658609303552,
    'Vent': 1137675592125399122,
    'Espace': 1137675462076796949
}

MJ_ROLE_ID = 1018179623886000278

class SelectSubElementModal(discord.ui.Modal):
    def __init__(self, view, element):
        super().__init__(title=f"Ajouter un sous-élément - {element}")
        self.view = view
        self.element = element
        
        self.name = discord.ui.TextInput(
            label="Nom du sous-élément",
            required=True
        )
        self.definition = discord.ui.TextInput(
            label="Définition",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.emotional_state = discord.ui.TextInput(
            label="État émotionnel",
            required=True
        )
        self.emotional_desc = discord.ui.TextInput(
            label="Description de l'état émotionnel",
            style=discord.TextStyle.paragraph,
            required=True
        )
        
        for item in [self.name, self.definition, self.emotional_state, self.emotional_desc]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            # Récupération directe du thread via l'ID
            thread = await interaction.guild.fetch_channel(THREAD_CHANNELS[self.element])
            if not thread:
                await interaction.followup.send(
                    f"Erreur : Impossible de trouver le thread pour l'élément {self.element}. "
                    "Contactez un administrateur.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=self.name.value,
                description=f"**Définition :** {self.definition.value}\n\n"
                           f"**État émotionnel :** {self.emotional_state.value}\n"
                           f"**Description :** {self.emotional_desc.value}",
                color=0x8543f7
            )
            
            await thread.send(embed=embed)
            
            data = {
                'name': self.name.value,
                'element': self.element,
                'definition': self.definition.value,
                'emotional_state': self.emotional_state.value,
                'emotional_desc': self.emotional_desc.value
            }
            await self.view.cog.save_subelement(data)
            
            await interaction.followup.send(
                f"Sous-élément ajouté avec succès dans le thread {thread.mention}!", 
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "Je n'ai pas les permissions nécessaires pour envoyer des messages dans le thread.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"Une erreur est survenue lors de l'envoi du message : {str(e)}",
                ephemeral=True
            )

class ElementSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=element, value=element)
            for element in ['Feu', 'Vent', 'Terre', 'Eau', 'Espace']
        ]
        super().__init__(placeholder="Choisir l'élément principal", options=options)

    async def callback(self, interaction: discord.Interaction):
        modal = SelectSubElementModal(self.view, self.values[0])
        await interaction.response.send_modal(modal)

class AddSubElementView(discord.ui.View):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.add_item(ElementSelect())

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
        self.setup_views()
        
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

    def setup_views(self):
        """Initialize persistent views"""
        self.bot.loop.create_task(self.load_persistent_views())

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
        try:
            all_data = self.sheet.get_all_values()[1:]  # Skip header
            processed = set()
            
            for row in all_data:
                message_id = row[0]
                if message_id in processed:
                    continue
                
                processed.add(message_id)
                view = SousElementsView(self, row[3])
                self.bot.add_view(view, message_id=int(message_id))
        except Exception as e:
            print(f"Erreur chargement vues persistantes: {e}")

    async def update_message(self, message, data):
        try:
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
        except Exception as e:
            print(f"Erreur mise à jour message: {e}")

    async def save_subelement(self, data):
        # Nouvelle méthode pour sauvegarder un sous-élément dans la liste principale
        worksheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
        row = [data['name'], data['element'], data['definition'], 
               data['emotional_state'], data['emotional_desc']]
        worksheet.append_row(row)

    @app_commands.command(name='ajouter-sous-element', description="Ajouter un nouveau sous-élément à la liste (MJ uniquement)")
    async def add_subelement(self, interaction: discord.Interaction):
        if not interaction.user.get_role(MJ_ROLE_ID):
            await interaction.response.send_message("Cette commande est réservée aux MJ.", ephemeral=True)
            return
            
        view = AddSubElementView(self)
        await interaction.response.send_message(
            "Sélectionnez l'élément principal du sous-élément :", 
            view=view, 
            ephemeral=True
        )

    @app_commands.command(name='sous-éléments', description="Créer un message pour gérer les sous-éléments d'un personnage")
    async def sous_elements(self, interaction: discord.Interaction, character_name: str):
        await interaction.response.defer()
        try:
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
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue: {e}", ephemeral=True)

class SubElementSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Choisir un sous-élément à ajouter",
            custom_id="subelement_select",
            row=0,
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none|none":
            await interaction.response.send_message(
                "Aucun sous-élément n'est disponible pour le moment.", 
                ephemeral=True
            )
            return

        try:
            element, name = self.values[0].split("|")
            view = self.view
            message_id = str(interaction.message.id)
            data = view.cog.get_message_data(message_id)

            if not data:
                await interaction.response.send_message("Message data not found.", ephemeral=True)
                return

            if interaction.user.id != data['user_id']:
                await interaction.response.send_message("Tu n'es pas autorisé à ajouter des sous-éléments.", ephemeral=True)
                return

            if element not in data['elements']:
                await interaction.response.send_message(f"Élément invalide: {element}", ephemeral=True)
                return

            data['elements'][element].append(name)
            view.cog.save_message_data(message_id, data)
            await view.cog.update_message(interaction.message, data)
            await interaction.response.send_message(f"Sous-élément '{name}' ajouté à {element}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Une erreur est survenue: {str(e)}", ephemeral=True)

class SousElementsView(discord.ui.View):
    def __init__(self, cog, character_name):
        super().__init__(timeout=None)
        self.cog = cog
        self.character_name = character_name
        
        # Charger les options avant de créer le select
        options = self.load_subelement_options()
        print(f"Options chargées: {options}")  # Débogage
        if not options:
            options = [
                discord.SelectOption(
                    label="Aucun sous-élément disponible",
                    value="none|none",
                    description="Contactez un MJ pour ajouter des sous-éléments"
                )
            ]
        
        self.add_item(SubElementSelect(options))

    def load_subelement_options(self):
        try:
            worksheet = self.cog.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
            all_data = worksheet.get_all_values()
            print(f"Données brutes: {all_data}")  # Débogage
            
            if len(all_data) <= 1:  # Si pas de données ou juste l'en-tête
                return []
            
            headers = all_data[0]  # Récupérer les en-têtes
            name_index = headers.index('name') if 'name' in headers else 0
            element_index = headers.index('element') if 'element' in headers else 1
            
            options = []
            for row in all_data[1:]:  # Skip header
                if len(row) > max(name_index, element_index):
                    name = row[name_index].strip()
                    element = row[element_index].strip()
                    if name and element:
                        print(f"Ajout de l'option: {name} - {element}")  # Débogage
                        options.append(
                            discord.SelectOption(
                                label=name,
                                value=f"{element}|{name}",
                                description=f"Élément: {element}"
                            )
                        )
            print(f"Options finales: {options}")  # Débogage
            return options
        except Exception as e:
            print(f"Erreur détaillée lors du chargement des sous-éléments: {str(e)}")
            import traceback
            traceback.print_exc()  # Afficher la stack trace complète
            return []

async def setup(bot):
    await bot.add_cog(SousElements(bot))
    print("Cog Souselements chargé avec succès")


