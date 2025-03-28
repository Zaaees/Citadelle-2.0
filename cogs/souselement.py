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
ALLOWED_CATEGORY_ID = 1020820787583799358

class SubElementModal(discord.ui.Modal):
    def __init__(self, cog, element):
        super().__init__(title=f"Ajouter un sous-élément - {element}")
        self.cog = cog
        self.element = element
        
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
        
        for item in [self.name, self.definition, self.emotional_state, 
                    self.emotional_desc, self.discoverer]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validation du découvreur
            discoverer_input = self.discoverer.value.strip()
            try:
                if '|' not in discoverer_input:
                    raise ValueError("Format incorrect")
                discoverer_id = int(discoverer_input.split('|')[0].strip())
                character_name = discoverer_input.split('|')[1].strip()
                
                # Vérifier que l'utilisateur existe
                discoverer = await interaction.guild.fetch_member(discoverer_id)
                if not discoverer:
                    raise ValueError("Utilisateur introuvable")
                
            except (ValueError, IndexError) as e:
                await interaction.followup.send(
                    "Format incorrect. Utilisez: ID|Nom du personnage",
                    ephemeral=True
                )
                return

            # Création de l'embed dans le thread approprié
            thread = interaction.guild.get_channel(THREAD_CHANNELS[self.element])
            if not thread:
                await interaction.followup.send(
                    f"Erreur : Thread introuvable pour {self.element}",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=self.name.value,
                description=f"**Définition :** {self.definition.value}\n\n"
                           f"**État émotionnel :** {self.emotional_state.value}\n"
                           f"**Description :** {self.emotional_desc.value}\n\n"
                           f"**Découvert par :** <@{discoverer_id}> ({character_name})\n"
                           f"**Utilisé par :** -",
                color=0x6d5380
            )
            
            msg = await thread.send(embed=embed)
            
            # Sauvegarde dans la base de données
            data = {
                'name': self.name.value,
                'element': self.element,
                'definition': self.definition.value,
                'emotional_state': self.emotional_state.value,
                'emotional_desc': self.emotional_desc.value,
                'discovered_by_id': discoverer_id,
                'discovered_by_char': character_name,
                'used_by': [],
                'message_id': msg.id
            }
            await self.cog.save_subelement(data)
            
            await interaction.followup.send(
                f"✅ Sous-élément ajouté avec succès dans {thread.mention}!", 
                ephemeral=True
            )
            
            # Notification au découvreur
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
                f"Erreur lors de la création du sous-élément : {str(e)}",
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
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            process = AddSubElementProcess(self.view.bot, interaction, self.values[0], self.view.cog)
            await process.start()
        except Exception as e:
            await interaction.followup.send(
                f"Une erreur est survenue : {str(e)}",
                ephemeral=True
            )

class AddElementView(discord.ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=300)
        self.bot = bot
        self.cog = cog
        self.add_item(ElementSelect())

class AddSubElementView(discord.ui.View):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.add_item(ElementSelect())

class SousElements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_google_sheets()
        self.setup_views()
        self.subelements_cache = {}  # Cache pour les sous-éléments
        self.last_cache_update = 0  # Timestamp de la dernière mise à jour du cache
        self.cache_duration = 60  # Durée du cache en secondes
        self.bot.add_listener(self.handle_character_sheet_message, 'on_message')
        
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
                        # Obtenir le thread directement à partir de son ID
                        thread_id = THREAD_CHANNELS[element]
                        thread = self.bot.get_channel(thread_id)
                        
                        if thread:
                            # Vérifier si le thread est archivé
                            was_archived = thread.archived
                            locked = thread.locked
                            
                            try:
                                # Désarchiver le thread si nécessaire
                                if was_archived:
                                    await thread.edit(archived=False)
                                if locked:
                                    await thread.edit(locked=False)
                                
                                # Mettre à jour le message
                                try:
                                    message = await thread.fetch_message(message_id)
                                    if message:
                                        embed = message.embeds[0]
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
                                
                                # Remettre le thread dans son état d'origine
                                if was_archived:
                                    await thread.edit(archived=True)
                                if locked:
                                    await thread.edit(locked=True)
                                    
                            except discord.Forbidden:
                                print(f"Permissions insuffisantes pour le thread {element}")
                            except Exception as e:
                                print(f"Erreur lors de la mise à jour du message: {e}")
                    break
                    
        except Exception as e:
            print(f"Erreur lors de la mise à jour des utilisateurs: {e}")

    @app_commands.command(name='ajouter-sous-element', description="Ajouter un nouveau sous-élément à la liste (MJ uniquement)")
    async def add_subelement(self, interaction: discord.Interaction):
        if not interaction.user.get_role(MJ_ROLE_ID):
            await interaction.response.send_message(
                "Cette commande est réservée aux MJ.", 
                ephemeral=True
            )
            return
            
        try:
            view = AddElementView(self.bot, self)
            # Utiliser defer au lieu de send_message
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                "Sélectionnez l'élément principal du sous-élément :", 
                view=view, 
                ephemeral=True
            )
        except Exception as e:
            print(f"Erreur lors de l'ajout du sous-élément: {str(e)}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Une erreur est survenue : {str(e)}", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Une erreur est survenue : {str(e)}", 
                    ephemeral=True
                )

    @app_commands.command(name='sous-éléments', description="Créer un message pour gérer les sous-éléments d'un personnage")
    async def sous_elements(self, interaction: discord.Interaction, character_name: str):
        try:
            if interaction.channel.category_id != ALLOWED_CATEGORY_ID:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que dans la catégorie appropriée.",
                    ephemeral=True
                )
                return
            
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
            await interaction.response.send_message(embed=embed, view=view)
            message = await interaction.original_response()

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

    @app_commands.command(
        name='update-souselements',
        description="Mettre à jour tous les messages de sous-éléments (MJ uniquement)"
    )
    async def update_souselements(self, interaction: discord.Interaction):
        if not interaction.user.get_role(MJ_ROLE_ID):
            await interaction.response.send_message(
                "Cette commande est réservée aux MJ.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            # Récupérer tous les sous-éléments
            worksheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
            all_data = worksheet.get_all_values()[1:]  # Skip header
            
            # Compteurs pour le rapport
            updated = 0
            failed = 0
            not_found = 0
            
            for row in all_data:
                try:
                    name = row[0]
                    element = row[1]
                    definition = row[2]
                    emotional_state = row[3]
                    emotional_desc = row[4]
                    discovered_by_id = int(row[5]) if row[5] != '0' else 0
                    discovered_by_char = row[6]
                    used_by = eval(row[7]) if row[7] else []
                    message_id = int(row[8]) if row[8] else None
                    
                    if not message_id:
                        not_found += 1
                        continue
                        
                    # Construire le texte "Utilisé par"
                    if not used_by:
                        used_by_text = "-"
                    else:
                        character_names = [char for _, char in used_by]
                        used_by_text = ", ".join(character_names)
                    
                    # Construire le texte "Découvert par"
                    discovered_by_text = (
                        f"<@{discovered_by_id}> ({discovered_by_char})" 
                        if discovered_by_id != 0 
                        else discovered_by_char
                    )
                    
                    # Créer le nouvel embed
                    embed = discord.Embed(
                        title=name,
                        description=(
                            f"**Définition :** {definition}\n\n"
                            f"**État émotionnel :** {emotional_state}\n"
                            f"**Description :** {emotional_desc}\n\n"
                            f"**Découvert par :** {discovered_by_text}\n"
                            f"**Utilisé par :** {used_by_text}"
                        ),
                        color=0x6d5380
                    )
                    
                    # Obtenir le thread directement via son ID
                    thread = self.bot.get_channel(THREAD_CHANNELS[element])
                    if thread:
                        try:
                            message = await thread.fetch_message(message_id)
                            await message.edit(embed=embed)
                            updated += 1
                        except discord.NotFound:
                            print(f"Message {message_id} non trouvé dans le thread {element}")
                            not_found += 1
                        except Exception as e:
                            print(f"Erreur lors de la mise à jour de {name}: {e}")
                            failed += 1
                    else:
                        print(f"Thread non trouvé pour l'élément {element}")
                        not_found += 1
                        
# Ajouter une pause pour éviter le rate limit
                    await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"Erreur lors du traitement d'une ligne: {e}")
                    failed += 1
            
            # Envoyer le rapport
            await interaction.followup.send(
                f"Mise à jour terminée !\n"
                f"✅ {updated} messages mis à jour\n"
                f"❌ {failed} échecs\n"
                f"⚠️ {not_found} messages non trouvés",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"Une erreur est survenue : {str(e)}",
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
            
            # S'assurer qu'il y a des données et ignorer l'en-tête
            if len(all_data) > 1:
                for row in all_data[1:]:  # Ignorer la première ligne (en-tête)
                    # Vérifier que la ligne a au moins les colonnes nécessaires
                    if len(row) >= 2:
                        name = row[0].strip()  # Première colonne : nom
                        element = row[1].strip()  # Deuxième colonne : élément
                        
                        # Vérifier que l'élément est valide et que le nom n'est pas vide
                        if element in elements_data and name:
                            # Vérifier si l'entrée existe déjà
                            existing_entries = [item['name'] for item in elements_data[element]]
                            if name not in existing_entries:
                                elements_data[element].append({
                                    'name': name,
                                    'value': f"{element}|{name}",
                                    'description': f"Sous-élément de {element}"
                                })
            
            # Trier les sous-éléments par ordre alphabétique pour chaque élément
            for element in elements_data:
                elements_data[element].sort(key=lambda x: x['name'])
            
            # Mettre à jour le cache
            self.subelements_cache = elements_data
            self.last_cache_update = current_time
            
            return elements_data
            
        except Exception as e:
            print(f"Erreur lors du chargement des sous-éléments: {e}")
            # En cas d'erreur, retourner le cache existant ou un dictionnaire vide
            return self.subelements_cache if self.subelements_cache else {
                'Eau': [], 'Feu': [], 'Vent': [], 'Terre': [], 'Espace': []
            }

    async def handle_character_sheet_message(self, message):
        if message.author.bot:
            return

        try:
            sheet_message = None
            sheet_data = None
            
            async for msg in message.channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    # Vérifie d'abord si le message a des données dans le Google Sheet
                    data = self.get_message_data(str(msg.id))
                    
                    # Ne continue QUE si on a trouvé des données valides
                    # ET si le message a le bon format de titre
                    if (data and 
                        msg.embeds[0].title and 
                        msg.embeds[0].title.startswith("Sous-éléments de ")):
                            sheet_message = msg
                            sheet_data = data
                            break

            if sheet_message and sheet_data:
                # Le reste du code reste identique
                embed = sheet_message.embeds[0]
                view = SousElementsView(self, sheet_data['character_name'])
                new_message = await message.channel.send(embed=embed, view=view)

                self.save_message_data(str(new_message.id), sheet_data)
                await sheet_message.delete()

                # Mettre à jour l'ID du message dans le thread des sous-éléments si nécessaire
                worksheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_SOUSELEMENT_LIST')).sheet1
                all_data = worksheet.get_all_values()

                for idx, row in enumerate(all_data[1:], start=2):
                    if str(sheet_message.id) == row[8]:
                        worksheet.update_cell(idx, 9, str(new_message.id))

        except Exception as e:
            print(f"Erreur dans handle_character_sheet_message: {e}")

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
        message_data = self.view.cog.get_message_data(str(interaction.message.id))
        if not message_data or interaction.user.id != message_data['user_id']:
            response = await interaction.response.send_message(
                "Tu n'es pas autorisé à modifier ces sous-éléments.",
                ephemeral=True
            )
            await asyncio.sleep(2)  # Attendre 5 secondes
            await response.delete()
            return

        await interaction.response.defer(ephemeral=True)
        select_view = SubElementSelectView(self.view.cog, interaction.message.id, interaction.user.id)
        await select_view.setup_menus()
        select_message = await interaction.followup.send(
            "Sélectionnez un sous-élément à ajouter :",
            view=select_view,
            ephemeral=True
        )
        # Stocker l'ID du message pour pouvoir le supprimer plus tard
        select_view.select_message_id = select_message.id

class RemoveSubElementSelect(discord.ui.Select):
    def __init__(self, data, cog):  # Ajout du cog comme paramètre
        options = []
        for element, subelements in data['elements'].items():
            for subelement in subelements:
                options.append(
                    discord.SelectOption(
                        label=subelement,
                        value=f"{element}|{subelement}",
                        description=f"Sous-élément de {element}"
                    )
                )
        
        if not options:
            options = [
                discord.SelectOption(
                    label="Aucun sous-élément",
                    value="none",
                    description="Vous n'avez aucun sous-élément à supprimer"
                )
            ]
            
        super().__init__(
            placeholder="Choisissez un sous-élément à supprimer",
            options=options,
            min_values=1,
            max_values=1
        )
        self.cog = cog  # Stockage du cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # Ajouter defer pour éviter l'erreur 404
        
        if self.values[0] == "none":
            await interaction.followup.send(
                "Vous n'avez aucun sous-élément à supprimer.",
                ephemeral=True,
                delete_after=2
            )
            return

        try:
            element, subelement = self.values[0].split("|")
            # Récupérer l'ID du message parent au lieu du message éphémère
            parent_message_id = str(interaction.message.reference.message_id if interaction.message.reference else interaction.message.id)
            data = self.cog.get_message_data(parent_message_id)

            if subelement in data['elements'][element]:
                data['elements'][element].remove(subelement)
                self.cog.save_message_data(parent_message_id, data)
                
                # Mise à jour du message principal
                parent_message = await interaction.channel.fetch_message(int(parent_message_id))
                await self.cog.update_message(parent_message, data)
                
                # Mise à jour dans le thread des sous-éléments
                forum = interaction.guild.get_channel(FORUM_ID)
                if forum:
                    # Modification ici : Chercher le thread directement
                    thread = None
                    threads = [t for t in forum.threads if t.id == THREAD_CHANNELS[element]]
                    if threads:
                        thread = threads[0]
                        
                    if thread:
                        async for message in thread.history():
                            if message.embeds and message.embeds[0].title == subelement:
                                embed = message.embeds[0]
                                desc_parts = embed.description.split("**Utilisé par :**")
                                used_by_text = desc_parts[1].strip() if len(desc_parts) > 1 else ""
                                
                                current_users = [u.strip() for u in used_by_text.split(",") if u.strip() != "-" and u.strip() != data['character_name']]
                                used_by_text = ", ".join(current_users) if current_users else "-"
                                
                                new_desc = f"{desc_parts[0]}**Utilisé par :** {used_by_text}"
                                embed.description = new_desc
                                await message.edit(embed=embed)  # Éditer au lieu de reposter
                                break
                
                # Mise à jour de la base de données
                await self.cog.update_subelement_users(
                    element,
                    subelement,
                    interaction.user.id,
                    data['character_name'],
                    adding=False
                )
                
                # Supprimer le message avec la liste des sous-éléments
                try:
                    original_message = await interaction.message.channel.fetch_message(interaction.message.id)
                    await original_message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            else:
                await interaction.followup.send(
                    f"Ce sous-élément n'est pas dans votre liste.",
                    ephemeral=True,
                    delete_after=2
                )
        except Exception as e:
            print(f"Erreur lors de la suppression du sous-élément: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de la suppression du sous-élément.",
                ephemeral=True,
                delete_after=2
            )

class RemoveSubElementButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="Supprimer sous-élément",
            custom_id="remove_subelement"
        )

    async def callback(self, interaction: discord.Interaction):
        message_data = self.view.cog.get_message_data(str(interaction.message.id))
        if not message_data or interaction.user.id != message_data['user_id']:
            response = await interaction.response.send_message(
                "Tu n'es pas autorisé à modifier ces sous-éléments.",
                ephemeral=True
            )
            await asyncio.sleep(2)
            await response.delete()
            return

        # Modification ici : utiliser response puis original_response
        view = discord.ui.View(timeout=60)
        select = RemoveSubElementSelect(message_data, self.view.cog)
        view.add_item(select)
        
        await interaction.response.send_message(
            "Sélectionnez le sous-élément à supprimer :",
            view=view,
            ephemeral=True
        )
        # Récupérer le message après l'envoi
        select_message = await interaction.original_response()
        select.select_message_id = select_message.id

class SousElementsView(discord.ui.View):
    def __init__(self, cog, character_name):
        super().__init__(timeout=None)
        self.cog = cog
        self.character_name = character_name
        self.add_item(AddSubElementButton())
        self.add_item(RemoveSubElementButton())

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
            response = await interaction.response.send_message(
                "Tu n'es pas autorisé à modifier ces sous-éléments.",
                ephemeral=True
            )
            await asyncio.sleep(2)
            await response.delete()
            return

        await interaction.response.defer(ephemeral=True)
        
        if self.values[0] == "none|none":
            await interaction.followup.send(
                f"Aucun sous-élément de {self.element_type} n'est disponible pour le moment.", 
                ephemeral=True,
                delete_after=2
            )
            return

        try:
            element, name = self.values[0].split("|")
            data = self.view.cog.get_message_data(str(self.main_message_id))

            if not data:
                await interaction.followup.send("Message data not found.", ephemeral=True, delete_after=2)
                return

            # Vérifier si le sous-élément n'est pas déjà dans la liste
            if name not in data['elements'][element]:
                data['elements'][element].append(name)
                self.view.cog.save_message_data(str(self.main_message_id), data)
                
                # Mettre à jour le message principal
                main_message = await interaction.channel.fetch_message(self.main_message_id)
                await self.view.cog.update_message(main_message, data)
                
                # Mettre à jour l'embed du sous-élément dans le thread correspondant
                forum = interaction.guild.get_channel(FORUM_ID)
                if forum:
                    # Modification ici : Chercher le thread directement
                    thread = None
                    threads = [t for t in forum.threads if t.id == THREAD_CHANNELS[element]]
                    if threads:
                        thread = threads[0]
                        
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
                                    if data['character_name'] not in current_users:
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
                
                # Supprimer le message avec la liste des sous-éléments
                try:
                    original_message = await interaction.message.channel.fetch_message(interaction.message.id)
                    await original_message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            else:
                await interaction.followup.send(
                    f"Le sous-élément '{name}' est déjà dans votre liste.", 
                    ephemeral=True,
                    delete_after=2
                )

        except Exception as e:
            print(f"Erreur dans le callback du select: {str(e)}")
            await interaction.followup.send(
                "Une erreur est survenue lors de l'ajout du sous-élément.",
                ephemeral=True,
                delete_after=2
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
            'discovered_by_id': None,
            'discovered_by_char': None
        }
        self.questions = [
            ("name", "Quel est le nom du sous-élément ?", 100),  # Ajout des limites
            ("definition", "Quelle est la définition scientifique du sous-élément ?", 2000),
            ("emotional_state", "Quel est l'état émotionnel associé ?", 100),
            ("emotional_desc", "Quelle est la description de cet état émotionnel ?", 2000),
            ("discovered_by_id", "Qui a découvert ce sous-élément ? (mentionnez le joueur en le ping @)", 100),
            ("discovered_by_char", "Quel est le nom du personnage qui a fait la découverte ?", 100)
        ]
        self.current_question = 0
        self.message = None

    def create_embed(self):
        embed = discord.Embed(
            title=f"Création d'un sous-élément - {self.element}",
            color=0x6d5380
        )

        # Mettre les réponses longues dans la description
        description = ""
        fields = []

        # Correction ici pour accéder correctement aux éléments du tuple
        for field, question, _ in self.questions[:self.current_question]:
            value = self.data[field]
            if value is not None:
                if field in ["definition", "emotional_desc"]:
                    description += f"**{question}**\n{value}\n\n"
                else:
                    # Modifier l'affichage pour le découvreur
                    if field == "discovered_by_id":
                        display_value = f"<@{value}>" if value != 0 else self.data.get('discovered_by_char', "Non spécifié")
                    else:
                        display_value = value
                    fields.append((question, display_value))

        if description:
            embed.description = description

        for question, value in fields:
            embed.add_field(
                name=question,
                value=value,
                inline=False
            )

        # Correction ici aussi pour accéder à la question actuelle
        if self.current_question < len(self.questions):
            current_field, current_question, _ = self.questions[self.current_question]
            embed.add_field(
                name="Question actuelle",
                value=f"**{current_question}**\n*Tapez 'annuler' pour arrêter le processus*",
                inline=False
            )

        return embed

    async def start(self):
        self.message = await self.interaction.followup.send(
            embed=self.create_embed(),
            ephemeral=True
        )
        await self.wait_for_next_answer()

    async def wait_for_next_answer(self):
        if self.current_question >= len(self.questions):
            await self.finish()
            return

        def check(m):
            return (m.author == self.interaction.user and 
                   m.channel == self.interaction.channel)

        try:
            response = await self.bot.wait_for('message', timeout=300.0, check=check)
            await response.delete()

            if response.content.lower() == 'annuler':
                await self.message.edit(
                    embed=discord.Embed(
                        title="Processus annulé",
                        description="La création du sous-élément a été annulée.",
                        color=0xFF0000
                    )
                )
                return

            field, question, max_length = self.questions[self.current_question]
            
            if field == "discovered_by_id":
                if response.mentions:
                    # Si une mention est présente, utiliser l'ID de l'utilisateur mentionné
                    member = response.mentions[0]
                    self.data[field] = member.id
                else:
                    # Sinon, stocker simplement la réponse comme texte
                    if len(response.content) > max_length:
                        error_embed = self.create_embed()
                        error_embed.add_field(
                            name="Erreur",
                            value=f"La réponse est trop longue (maximum {max_length} caractères).",
                            inline=False
                        )
                        await self.message.edit(embed=error_embed)
                        await self.wait_for_next_answer()
                        return
                    # Stocker 0 comme ID pour indiquer qu'il n'y a pas de mention
                    self.data[field] = 0
                    self.data['discovered_by_char'] = response.content
                    # Passer la prochaine question puisqu'on a déjà le nom
                    self.current_question += 1
            else:
                # Vérifier la longueur de la réponse
                if len(response.content) > max_length:
                    error_embed = self.create_embed()
                    error_embed.add_field(
                        name="Erreur",
                        value=f"La réponse est trop longue (maximum {max_length} caractères).",
                        inline=False
                    )
                    await self.message.edit(embed=error_embed)
                    await self.wait_for_next_answer()
                    return
                
                self.data[field] = response.content

            self.current_question += 1
            await self.message.edit(embed=self.create_embed())
            await self.wait_for_next_answer()

        except asyncio.TimeoutError:
            await self.message.edit(
                embed=discord.Embed(
                    title="Temps écoulé",
                    description="Le processus a été annulé car vous avez mis trop de temps à répondre.",
                    color=0xFF0000
                )
            )

    async def finish(self):
        try:
            # Récupérer le forum
            forum = self.interaction.guild.get_channel(FORUM_ID)
            if not forum:
                raise ValueError(f"Forum introuvable (ID: {FORUM_ID})")

            # Modification ici : Utiliser get_thread_channel au lieu de get_channel
            thread = forum.get_thread(THREAD_CHANNELS[self.element])
            if not thread:
                # Si le thread n'est pas trouvé, essayons de le chercher dans tous les threads du forum
                threads = [t for t in forum.threads if t.id == THREAD_CHANNELS[self.element]]
                thread = threads[0] if threads else None

            if not thread:
                raise ValueError(f"Thread introuvable pour l'élément {self.element} (ID: {THREAD_CHANNELS[self.element]})")

            # Le reste du processus
            discovered_by_text = (
                f"<@{self.data['discovered_by_id']}> ({self.data['discovered_by_char']})" 
                if self.data['discovered_by_id'] != 0 
                else self.data['discovered_by_char']
            )
            embed = discord.Embed(
                title=self.data['name'],
                description=(
                    f"**Définition :** {self.data['definition']}\n\n"
                    f"**État émotionnel :** {self.data['emotional_state']}\n"
                    f"**Description :** {self.data['emotional_desc']}\n\n"
                    f"**Découvert par :** {discovered_by_text}\n"
                    f"**Utilisé par :** -"
                ),
                color=0x6d5380
            )
            
            msg = await thread.send(embed=embed)
            
            # Préparation des données pour la sauvegarde
            save_data = {
                'name': self.data['name'],
                'element': self.element,
                'definition': self.data['definition'],
                'emotional_state': self.data['emotional_state'],
                'emotional_desc': self.data['emotional_desc'],
                'discovered_by_id': self.data['discovered_by_id'],
                'discovered_by_char': self.data['discovered_by_char'],
                'used_by': [],
                'message_id': msg.id
            }
            
            await self.cog.save_subelement(save_data)
            
            final_embed = discord.Embed(
                title="Sous-élément créé avec succès !",
                description=f"Le sous-élément a été ajouté dans {thread.mention}",
                color=0x00FF00
            )
            await self.message.edit(embed=final_embed)

        except Exception as e:
            error_embed = discord.Embed(
                title="Erreur",
                description=f"Une erreur est survenue : {str(e)}",
                color=0xFF0000
            )
            await self.message.edit(embed=error_embed)

async def setup(bot):
    await bot.add_cog(SousElements(bot))
    print("Cog Souselements chargé avec succès")