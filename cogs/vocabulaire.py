import discord
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from discord import app_commands, Interaction, ButtonStyle
from discord.ext import commands
from discord.ui import View, Button
import json
import os

class VocabulaireView(View):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def interaction_check(self, interaction: Interaction) -> bool:
        admin_role_id = 1017864406987706391
    
        if interaction.data["custom_id"] == "supprimer":
            has_role = any(role.id == admin_role_id for role in interaction.user.roles)
            if not has_role:
                await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)
                return False
        return True

    @discord.ui.button(label="Mots aléatoires", style=ButtonStyle.blurple, custom_id="mots_aleatoires")
    async def mots_aleatoires(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        mots = self.cog.get_random_words(5)
    
        await interaction.followup.send("## Voici 5 mots aléatoires :")
    
        for mot, info in mots:
            embed = discord.Embed(title=mot.upper(), color=0x8543f7)
            embed.add_field(name="Définition", value=info['definition'], inline=False)
            embed.add_field(name="Extrait", value=f"*{info['extrait']}*", inline=False)
            await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Recherche", style=ButtonStyle.blurple, custom_id="recherche")
    async def recherche(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(RechercheModal(self.cog))

    @discord.ui.button(label="Ajouter", style=ButtonStyle.green, custom_id="ajout")
    async def ajout(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(AjoutModal(self.cog))

    @discord.ui.button(label="Supprimer", style=ButtonStyle.red, custom_id="supprimer")
    async def supprimer(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(SuppressionModal(self.cog))

class SuppressionModal(discord.ui.Modal, title="Supprimer un mot"):
    mot = discord.ui.TextInput(label="Mot à supprimer")

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: Interaction):
        mot = self.mot.value.lower()
        if mot in self.cog.vocabulary:
            del self.cog.vocabulary[mot]
            self.cog.save_vocabulary()
            await interaction.response.send_message(f"Le mot '{mot}' a été supprimé avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Le mot '{mot}' n'a pas été trouvé dans le vocabulaire.", ephemeral=True)

class AjoutModal(discord.ui.Modal, title="Ajouter des mots"):
    mot = discord.ui.TextInput(label="Mot", placeholder="Séparez les mots par |")
    definition = discord.ui.TextInput(label="Définition", placeholder="Séparez les définitions par |")
    extrait = discord.ui.TextInput(label="Extrait", placeholder="Séparez les extraits par |")

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        mots = self.mot.value.split('|')
        definitions = self.definition.value.split('|')
        extraits = self.extrait.value.split('|')

        if len(mots) != len(definitions) or len(mots) != len(extraits):
            await interaction.response.send_message("Le nombre de mots, définitions et extraits doit être identique.", ephemeral=True)
            return

        added_words = 0
        for i in range(len(mots)):
            if await self.cog.add_word(mots[i].strip(), definitions[i].strip(), extraits[i].strip()):
                added_words += 1

        await interaction.response.send_message(f"{added_words} mot(s) ajouté(s) avec succès.", ephemeral=True)

class RechercheModal(discord.ui.Modal, title="Rechercher un mot"):
    mot = discord.ui.TextInput(label="Mot à rechercher")

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: Interaction):
        mot = self.mot.value.lower()
        result = self.cog.search_word(mot)
        if result:
            await interaction.response.send_message(embed=self.cog.create_words_embed([(mot, result)]), ephemeral=True)
        else:
            await interaction.response.send_message("Mot non trouvé.", ephemeral=True)

class Vocabulaire(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vocabulary_channel_id = 1273659420101971970
        self.sheet = self.connect_to_sheets()
        self.vocabulary = self.load_vocabulary()

    def connect_to_sheets(self):
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            json.loads(os.getenv('SERVICE_ACCOUNT_JSON')), 
            scope
        )
        
        client = gspread.authorize(credentials)
        return client.open_by_key(os.getenv('GOOGLE_SHEET_ID_VOCABULAIRE')).sheet1

    def load_vocabulary(self):
        # Récupérer toutes les données du Google Sheet
        records = self.sheet.get_all_records()
        
        # Créer le dictionnaire de vocabulaire
        vocabulary = {}
        for row in records:
            mot = row['Mot'].lower()
            vocabulary[mot] = {
                'definition': row['Definition'],
                'extrait': row['Extrait']
            }
        
        return vocabulary
    
    def save_vocabulary(self):
        # Récupérer toutes les données actuelles
        current_data = self.sheet.get_all_records()
        
        # Créer un dictionnaire des données existantes pour une recherche plus rapide
        existing_words = {row['Mot'].lower(): True for row in current_data}
        
        # Pour chaque mot dans le vocabulaire
        for mot, info in self.vocabulary.items():
            # Si le mot n'existe pas déjà dans la feuille
            if mot not in existing_words:
                # Ajouter la nouvelle ligne
                self.sheet.append_row([
                    mot,
                    info['definition'],
                    info['extrait']
                ])

    async def add_word(self, mot, definition, extrait):
        mot = mot.lower()
        if mot not in self.vocabulary:
            self.vocabulary[mot] = {"definition": definition, "extrait": extrait}
            
            # Ajouter au Google Sheet
            self.sheet.append_row([mot, definition, extrait])
            
            # Envoyer dans le canal Discord
            channel = self.bot.get_channel(self.vocabulary_channel_id)
            if channel:
                embed = discord.Embed(title=mot.upper(), color=0x8543f7)
                embed.add_field(name="Définition", value=definition, inline=False)
                embed.add_field(name="Extrait", value=f"*{extrait}*", inline=False)
                await channel.send(embed=embed)
            return True
        return False
    
    def get_random_words(self, n):
        return random.sample(list(self.vocabulary.items()), min(n, len(self.vocabulary)))

    def create_words_embed(self, words):
        embed = discord.Embed(title="Vocabulaire", color=0x8543f7)
        for i, (mot, info) in enumerate(words):
            # Ajouter une ligne de séparation avant chaque mot, sauf le premier
            if i > 0:
                embed.add_field(name="\u200b", value="``` ```\n** **", inline=False)
        
            embed.add_field(
                name=f"{mot.upper()}",
                value=f"**Définition :**\n{info['definition']}\n\n**Extrait :**\n*{info['extrait']}*",
                inline=False
            )
        return embed

    def search_word(self, mot):
        return self.vocabulary.get(mot.lower())
    
    def delete_word(self, mot):
        mot = mot.lower()
        if mot in self.vocabulary:
            del self.vocabulary[mot]
            self.save_vocabulary()
            return True
        return False

    async def show_list(self, interaction: Interaction):
    # Trier les mots par ordre d'ajout inversé (les plus récents en premier)
        words = list(self.vocabulary.items())[::-1]
        pages = [words[i:i+10] for i in range(0, len(words), 10)]
    
        current_page = 0
        max_pages = len(pages)
        buttons_per_row = 5
        max_rows = 5
        max_buttons = buttons_per_row * max_rows

        async def update_message(page):
            embed = self.create_words_embed(pages[page])
            embed.set_footer(text=f"Page {page+1}/{max_pages}")
            return embed

        async def update_view():
            view.clear_items()
            start_button = (current_page // max_buttons) * max_buttons
            for i in range(start_button, min(start_button + max_buttons, max_pages)):
                button = discord.ui.Button(label=str(i+1), style=discord.ButtonStyle.secondary, custom_id=f"page_{i}")
                button.callback = lambda interaction, page=i: change_page(interaction, page)
                view.add_item(button)
    
            if start_button > 0:
                prev_button = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, custom_id="prev_set")
                prev_button.callback = lambda interaction: change_button_set(interaction, start_button - max_buttons)
                view.add_item(prev_button)
    
            if start_button + max_buttons < max_pages:
                next_button = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, custom_id="next_set")
                next_button.callback = lambda interaction: change_button_set(interaction, start_button + max_buttons)
                view.add_item(next_button)

        view = discord.ui.View()

        async def change_page(interaction, page):
            nonlocal current_page
            current_page = page
            await update_view()
            await interaction.response.edit_message(embed=await update_message(current_page), view=view)

        async def change_button_set(interaction, new_start):
            nonlocal current_page
            current_page = new_start
            await update_view()
            await interaction.response.edit_message(embed=await update_message(current_page), view=view)

        await update_view()
        await interaction.response.send_message(embed=await update_message(0), view=view, ephemeral=True)

    async def add_word(self, mot, definition, extrait):
        mot = mot.lower()
        if mot not in self.vocabulary:
            self.vocabulary[mot] = {"definition": definition, "extrait": extrait}
            self.save_vocabulary()
            
            # Envoyer le nouveau mot dans le salon spécifié
            channel = self.bot.get_channel(self.vocabulary_channel_id)
            if channel:
                embed = discord.Embed(title=mot.upper(), color=0x8543f7)
                embed.add_field(name="Définition", value=definition, inline=False)
                embed.add_field(name="Extrait", value=f"*{extrait}*", inline=False)
                await channel.send(embed=embed)
            return True
        return False
    
    @app_commands.command(name="vocabulaire", description="Ouvrir le panel de gestion du vocabulaire")
    async def vocabulaire(self, interaction: Interaction):
        view = VocabulaireView(self)
        await interaction.response.send_message("Choisissez une action :", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Vocabulaire(bot))
    print("Cog Vocabulaire chargé avec succès")