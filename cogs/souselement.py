import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import time

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
        
        # Définition des champs dans l'ordre (maximum 5)
        self.name = discord.ui.TextInput(
            label="Nom du sous-élément",
            required=True,
            max_length=100
        )
        self.definition = discord.ui.TextInput(
            label="Définition",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.emotional_state = discord.ui.TextInput(
            label="État émotionnel",
            required=True,
            max_length=100
        )
        self.emotional_desc = discord.ui.TextInput(
            label="Description émotionnelle",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.discoverer = discord.ui.TextInput(
            label="Découvreur (ID|Nom du personnage)",
            placeholder="Ex: 123456789|Gandalf",
            required=True,
            max_length=100
        )
        
        # Ajout des champs dans l'ordre
        for item in [self.name, self.definition, self.emotional_state, 
                    self.emotional_desc, self.discoverer]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            # Extraire l'ID utilisateur de la mention ou chercher par ID direct
            discoverer_input = self.discoverer.value.strip()
            try:
                if '<@' in discoverer_input:
                    # Extraire l'ID de la mention
                    discoverer_id = int(''.join(filter(str.isdigit, discoverer_input.split('|')[0])))
                    character_name = discoverer_input.split('|')[1].strip()
                else:
                    # Format ID|Nom
                    discoverer_id = int(discoverer_input.split('|')[0].strip())
                    character_name = discoverer_input.split('|')[1].strip()
            except (ValueError, IndexError):
                await interaction.followup.send(
                    "Format incorrect. Utilisez soit une mention suivie du nom du personnage (<@ID>|Nom) "
                    "ou un ID suivi du nom (ID|Nom)",
                    ephemeral=True
                )
                return

            discoverer = await interaction.guild.fetch_member(discoverer_id)
            if not discoverer:
                await interaction.followup.send("Impossible de trouver l'utilisateur spécifié.", ephemeral=True)
                return

            # Récupération du thread et création de l'embed
            thread = interaction.guild.get_channel(THREAD_CHANNELS[self.element])
            if not thread:
                await interaction.followup.send(
                    f"Erreur : Impossible de trouver le thread pour l'élément {self.element}.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=self.name.value,
                description=f"**Définition :** {self.definition.value}\n\n"
                           f"**État émotionnel :** {self.emotional_state.value}\n"
                           f"**Description :** {self.emotional_desc.value}\n\n"
                           f"**Découvert par :** {discoverer.mention} ({character_name})\n"
                           f"**Utilisé par :** -",
                color=0x6d5380
            )
            
            msg = await thread.send(embed=embed)
            
            data = {
                'name': self.name.value,
                'element': self.element,
                'definition': self.definition.value,
                'emotional_state': self.emotional_state.value,
                'emotional_desc': self.emotional_desc.value,
                'discovered_by_id': discoverer_id,
                'discovered_by_char': character_name,
                'used_by': [],
                'message_id': msg.id  # Ajout de l'ID du message
            }
            await self.view.cog.save_subelement(data)
            
            await interaction.followup.send(
                f"✅ Sous-élément ajouté avec succès dans le thread {thread.mention}!", 
                ephemeral=True
            )
            
            # Notifier le découvreur
            if discoverer_id != interaction.user.id:
                try:
                    await discoverer.send(
                        f"Votre personnage {character_name} a été enregistré comme découvreur "
                        f"du sous-élément **{self.name.value}** ({self.element})"
                    )
                except discord.Forbidden:
                    pass  # L'utilisateur a peut-être désactivé ses MPs
            
        except Exception as e:
            await interaction.followup.send(
                f"Une erreur est survenue lors de l'ajout du sous-élément : {str(e)}",
                ephemeral=True
            )

class ElementSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=element, value=element)
            for element in ['Feu', 'Vent', 'Terre', 'Eau', 'Espace']
        ]
        super().__init__(
            placeholder="Choisir l'élément principal",
            options=options,
            min_values=1,
            max_values=1
        )  # Supprimé custom_id car pas besoin de persistance

class AddSubElementView(discord.ui.View):
    def __init__(self, cog):
        super().__init__()  # Supprimé timeout=None car pas besoin de persistance
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
        self.subelements_cache = {}  # Cache pour les sous-éléments
        self.last_cache_update = 0  # Timestamp de la dernière mise à jour du cache
        self.cache_duration = 60  # Durée du cache en secondes
        
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
                    return "-\n\n"  # Ajout d'un saut de ligne supplémentaire
                return ''.join(f'- {item}\n' for item in elements) + '\n'  # Ajout d'un saut de ligne à la fin

            description = (
                "# Sous-éléments :\n"
                "** **\n"
                "## __Eau :__\n"
                f"{format_elements(data['elements']['Eau'])}"
                "## __Feu :__\n"
                f"{format_elements(data['elements']['Feu'])}"
                "## __Vent :__\n"
                f"{format_elements(data['elements']['Vent'])}"
                "## __Terre :__\n"
                f"{format_elements(data['elements']['Terre'])}"
                "## __Espace :__\n"
                f"{format_elements(data['elements']['Espace'])}"
            )
            
            embed = discord.Embed(
                title=f"Sous-éléments de {data['character_name']}", 
                description=description,
                color=0x6d5380
            )
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Erreur mise à jour message: {e}")

    async def save_subelement(self, data):
        try:
            worksheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
            
            # Vérifier si la feuille est vide et ajouter les en-têtes si nécessaire
            if not worksheet.get_all_values():
                headers = ['name', 'element', 'definition', 'emotional_state', 'emotional_desc', 
                          'discovered_by_id', 'discovered_by_char', 'used_by', 'message_id']
                worksheet.append_row(headers)
            
            row = [data['name'], data['element'], data['definition'], 
                   data['emotional_state'], data['emotional_desc'],
                   str(data['discovered_by_id']), data['discovered_by_char'], '[]', str(data['message_id'])]
            worksheet.append_row(row)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du sous-élément: {e}")
            raise e

    async def update_subelement_users(self, element, subelement_name, user_id, character_name, adding=True):
        try:
            worksheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
            all_data = worksheet.get_all_values()
            
            # Trouver la ligne du sous-élément
            for idx, row in enumerate(all_data[1:], start=2):
                if row[0] == subelement_name and row[1] == element:
                    users = eval(row[7]) if len(row) > 7 and row[7] else []
                    if adding:
                        if (user_id, character_name) not in users:
                            users.append((user_id, character_name))
                    else:
                        users = [(uid, char) for uid, char in users if uid != user_id]
                    
                    worksheet.update_cell(idx, 8, str(users))
                    
                    # Utiliser l'ID du message sauvegardé
                    message_id = int(row[8]) if len(row) > 8 and row[8] else None
                    if message_id:
                        thread = self.bot.get_channel(THREAD_CHANNELS[element])
                        if thread:
                            try:
                                message = await thread.fetch_message(message_id)
                                if message:
                                    embed = message.embeds[0]
                                    # Formatage de la liste avec des virgules
                                    if not users:
                                        used_by = "-"
                                    else:
                                        character_names = [char for _, char in users]
                                        used_by = ", ".join(character_names)
                                    
                                    desc_parts = embed.description.split("**Utilisé par :**")
                                    new_desc = f"{desc_parts[0]}**Utilisé par :** {used_by}"
                                    embed.description = new_desc
                                    await message.edit(embed=embed)
                            except discord.NotFound:
                                print(f"Message {message_id} non trouvé dans le thread {element}")
                    break
                    
        except Exception as e:
            print(f"Erreur lors de la mise à jour des utilisateurs: {e}")

    @app_commands.command(name='ajouter-sous-element', description="Ajouter un nouveau sous-élément à la liste (MJ uniquement)")
    async def add_subelement(self, interaction: discord.Interaction):
        try:
            if not interaction.user.get_role(MJ_ROLE_ID):
                await interaction.response.send_message(
                    "Cette commande est réservée aux MJ.", 
                    ephemeral=True
                )
                return
                
            view = AddSubElementView(self)
            # Modification pour enregistrer la vue globalement
            self.bot.add_view(view)
            await interaction.response.send_message(
                "Sélectionnez l'élément principal du sous-élément :", 
                view=view, 
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Erreur détaillée lors de l'ajout du sous-élément: {str(e)}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "Une erreur est survenue lors de l'ajout du sous-élément.",
                        ephemeral=True
                    )
            except:
                pass  # Si on ne peut pas envoyer de message, on ignore silencieusement

    @app_commands.command(name='sous-éléments', description="Créer un message pour gérer les sous-éléments d'un personnage")
    async def sous_elements(self, interaction: discord.Interaction, character_name: str):
        try:
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
                color=0x6d5380
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
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Une erreur est survenue: {str(e)}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Une erreur est survenue: {str(e)}", 
                    ephemeral=True
                )

    async def get_all_subelements(self):
        current_time = int(time.time())
        
        # Si le cache est encore valide, on l'utilise
        if self.subelements_cache and (current_time - self.last_cache_update) < self.cache_duration:
            return self.subelements_cache
            
        try:
            worksheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
            all_data = worksheet.get_all_values()
            
            # Organiser les données par élément
            elements_data = {
                'Eau': [], 'Feu': [], 'Vent': [], 'Terre': [], 'Espace': []
            }
            
            if len(all_data) > 1:  # S'il y a des données après l'en-tête
                for row in all_data[1:]:
                    if len(row) >= 2:
                        name = row[0].strip()
                        element = row[1].strip()
                        if element in elements_data and name:
                            elements_data[element].append({
                                'name': name,
                                'value': f"{element}|{name}",
                                'description': f"Sous-élément de {element}"
                            })
            
            # Mettre à jour le cache
            self.subelements_cache = elements_data
            self.last_cache_update = current_time
            
            return elements_data
            
        except Exception as e:
            print(f"Erreur lors du chargement des sous-éléments: {e}")
            return self.subelements_cache if self.subelements_cache else {
                'Eau': [], 'Feu': [], 'Vent': [], 'Terre': [], 'Espace': []
            }

class SubElementSelectView(discord.ui.View):
    def __init__(self, cog, main_message_id, user_id):
        super().__init__(timeout=300)  # Timeout de 5 minutes
        self.cog = cog
        self.main_message_id = main_message_id
        self.user_id = user_id

    async def setup_menus(self):
        elements_rows = {
            'Eau': 0, 'Feu': 1, 'Vent': 2, 'Terre': 3, 'Espace': 4
        }
        
        all_subelements = await self.cog.get_all_subelements()
        
        for element, row in elements_rows.items():
            options = [
                discord.SelectOption(
                    label=item['name'],
                    value=item['value'],
                    description=item['description']
                )
                for item in all_subelements[element]
            ]
            
            if not options:
                options = [
                    discord.SelectOption(
                        label=f"Aucun sous-élément de {element}",
                        value="none|none",
                        description=f"Contactez un MJ pour ajouter des sous-éléments de {element}"
                    )
                ]
            
            self.add_item(SubElementSelect(element, options, row, self.main_message_id, self.user_id))

class AddSubElementButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Ajouter sous-élément",
            custom_id="add_subelement"
        )

    async def callback(self, interaction: discord.Interaction):
        # Récupérer les données du message pour vérifier le propriétaire
        message_data = self.view.cog.get_message_data(str(interaction.message.id))
        if not message_data or interaction.user.id != message_data['user_id']:
            await interaction.response.send_message(
                "Tu n'es pas autorisé à modifier ces sous-éléments.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        select_view = SubElementSelectView(self.view.cog, interaction.message.id, interaction.user.id)
        await select_view.setup_menus()
        await interaction.followup.send(
            "Sélectionnez un sous-élément à ajouter :",
            view=select_view,
            ephemeral=True
        )

class SousElementsView(discord.ui.View):
    def __init__(self, cog, character_name):
        super().__init__(timeout=None)
        self.cog = cog
        self.character_name = character_name
        self.add_item(AddSubElementButton())

class SubElementSelect(discord.ui.Select):
    def __init__(self, element, options, row_number, main_message_id, user_id):
        super().__init__(
            placeholder=f"Sous-éléments de {element}",
            custom_id=f"subelement_select_{element.lower()}",
            row=row_number,
            options=options,
            min_values=1,
            max_values=1
        )
        self.element_type = element
        self.main_message_id = main_message_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Tu n'es pas autorisé à modifier ces sous-éléments.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        if self.values[0] == "none|none":
            await interaction.followup.send(
                f"Aucun sous-élément de {self.element_type} n'est disponible pour le moment.", 
                ephemeral=True
            )
            return

        try:
            element, name = self.values[0].split("|")
            data = self.view.cog.get_message_data(str(self.main_message_id))

            if not data:
                await interaction.followup.send("Message data not found.", ephemeral=True)
                return

            # Vérifier si le sous-élément n'est pas déjà dans la liste
            if name not in data['elements'][element]:
                data['elements'][element].append(name)
                self.view.cog.save_message_data(str(self.main_message_id), data)
                
                # Mettre à jour le message principal
                main_message = await interaction.channel.fetch_message(self.main_message_id)
                await self.view.cog.update_message(main_message, data)
                
                # Mettre à jour l'embed du sous-élément dans le thread correspondant
                thread = interaction.guild.get_channel(THREAD_CHANNELS[element])
                if thread:
                    async for message in thread.history():
                        if message.embeds and message.embeds[0].title == name:
                            embed = message.embeds[0]
                            desc_parts = embed.description.split("**Utilisé par :**")
                            used_by_text = desc_parts[1].strip() if len(desc_parts) > 1 else ""
                            
                            # Gérer la liste des utilisateurs avec des virgules
                            if used_by_text == "-" or not used_by_text:
                                used_by_text = data['character_name']
                            else:
                                # Supprimer les tirets et les retours à la ligne
                                current_users = [u.strip('- \n') for u in used_by_text.split(',')]
                                current_users.append(data['character_name'])
                                used_by_text = ", ".join(current_users)
                            
                            new_desc = f"{desc_parts[0]}**Utilisé par :** {used_by_text}"
                            embed.description = new_desc
                            await message.edit(embed=embed)
                            break
                
                # Mettre à jour la liste des utilisateurs dans le système
                await self.view.cog.update_subelement_users(
                    element,
                    name,
                    interaction.user.id,
                    data['character_name'],
                    adding=True
                )
                
                await interaction.followup.send(
                    f"Sous-élément '{name}' ajouté à {element}.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Le sous-élément '{name}' est déjà dans votre liste.", 
                    ephemeral=True
                )

        except Exception as e:
            print(f"Erreur dans le callback du select: {str(e)}")
            await interaction.followup.send(
                "Une erreur est survenue lors de l'ajout du sous-élément.",
                ephemeral=True
            )

class AddSubElementProcess:
    def __init__(self, bot, interaction, element, cog):
        self.bot = bot
        self.interaction = interaction
        self.element = element
        self.cog = cog
        self.data = {
            'name': None,
            'definition': None,
            'emotional_state': None,
            'emotional_desc': None,
            'discovered_by': None,
            'character_name': None
        }
        self.questions = [
            ("name", "Quel est le nom du sous-élément ?"),
            ("definition", "Quelle est la définition scientifique du sous-élément ?"),
            ("emotional_state", "Quel est l'état émotionnel associé ?"),
            ("emotional_desc", "Quelle est la description de cet état émotionnel ?"),
            ("discovered_by", "Qui a découvert ce sous-élément ? (mentionnez le joueur)"),
            ("character_name", "Quel est le nom du personnage qui a découvert ce sous-élément ?"),
        ]
        self.current_message = None
        self.current_question = 0

    def create_question_embed(self, question):
        return discord.Embed(
            title="Création d'un sous-élément",
            description=question,
            color=0x6d5380
        ).add_field(
            name="Élément", 
            value=self.element
        ).add_field(
            name="Note", 
            value="Tapez votre réponse dans le chat. Le message sera automatiquement supprimé."
        )

    async def start(self):
        await self.interaction.response.defer(ephemeral=True)
        await self.ask_next_question()

    async def ask_next_question(self):
        if self.current_question >= len(self.questions):
            await self.finish()
            return

        field, question = self.questions[self.current_question]
        embed = self.create_question_embed(question)
        
        if self.current_message:
            await self.current_message.edit(embed=embed)
        else:
            self.current_message = await self.interaction.followup.send(embed=embed)

        def check(m):
            return m.author == self.interaction.user and m.channel == self.interaction.channel

        try:
            response = await self.bot.wait_for('message', timeout=300.0, check=check)
            await response.delete()
            
            if (field == "discovered_by"):
                try:
                    # Extraire l'ID de la mention
                    mentioned_id = int(''.join(filter(str.isdigit, response.content)))
                    discoverer = await self.interaction.guild.fetch_member(mentioned_id)
                    
                    if not discoverer:
                        await self.handle_error("Utilisateur introuvable. Veuillez mentionner un utilisateur valide.")
                        return
                        
                    self.data['discovered_by'] = discoverer
                except ValueError:
                    await self.handle_error("Format incorrect. Veuillez mentionner l'utilisateur (@User).")
                    return
            else:
                self.data[field] = response.content

            self.current_question += 1
            await self.ask_next_question()

        except asyncio.TimeoutError:
            await self.handle_error("Temps écoulé. Processus annulé.")

    async def handle_error(self, error_message):
        error_embed = discord.Embed(
            title="Erreur",
            description=error_message,
            color=0xFF0000
        )
        await self.current_message.edit(embed=error_embed)

    async def finish(self):
        thread = await self.interaction.guild.fetch_channel(THREAD_CHANNELS[self.element])
        embed = discord.Embed(
            title=self.data['name'],
            description=f"**Définition :** {self.data['definition']}\n\n"
                       f"**État émotionnel :** {self.data['emotional_state']}\n"
                       f"**Description :** {self.data['emotional_desc']}\n\n"
                       f"**Découvert par :** {self.data['discovered_by'].mention} ({self.data['character_name']})\n"
                       f"**Utilisé par :** -",
            color=0x6d5380
        )
        
        msg = await thread.send(embed=embed)
        
        data = {
            'name': self.data['name'],
            'element': self.element,
            'definition': self.data['definition'],
            'emotional_state': self.data['emotional_state'],
            'emotional_desc': self.data['emotional_desc'],
            'discovered_by_id': self.data['discovered_by'].id,
            'discovered_by_char': self.data['character_name'],
            'used_by': [],
            'message_id': msg.id  # Ajout de l'ID du message
        }
        
        await self.cog.save_subelement(data)  # Use stored cog reference
        
        success_embed = discord.Embed(
            title="Sous-élément créé !",
            description=f"Le sous-élément **{self.data['name']}** a été ajouté avec succès dans le salon {thread.mention}",
            color=0x00FF00
        )
        await self.current_message.edit(embed=success_embed)

async def setup(bot):
    await bot.add_cog(SousElements(bot))
    print("Cog Souselements chargé avec succès")



