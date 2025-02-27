import discord
import random
import gspread
import csv
import io
from difflib import SequenceMatcher
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
            embed = discord.Embed(title=mot.upper(), color=0x6d5380)
            embed.add_field(name="Définition", value=info['definition'], inline=False)
            embed.add_field(name="Extrait", value=f"*{info['extrait']}*", inline=False)
            await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Recherche", style=ButtonStyle.blurple, custom_id="recherche")
    async def recherche(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(RechercheModal(self.cog))

    @discord.ui.button(label="Ajouter", style=ButtonStyle.green, custom_id="ajout")
    async def ajout(self, interaction: Interaction, button: Button):
        view = AjoutOptionsView(self.cog)
        await interaction.response.send_message("Comment souhaitez-vous ajouter des mots ?", view=view, ephemeral=True)

    @discord.ui.button(label="Supprimer", style=ButtonStyle.red, custom_id="supprimer")
    async def supprimer(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(SuppressionModal(self.cog))

class AjoutOptionsView(View):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    @discord.ui.button(label="Ajouter un mot", style=ButtonStyle.primary)
    async def ajouter_mot(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(MotForm(self.cog))

    @discord.ui.button(label="Importer CSV", style=ButtonStyle.primary)
    async def importer_csv(self, interaction: Interaction, button: Button):
        # Enregistrer l'utilisateur comme attendant un fichier CSV
        self.cog.file_waiting_users[interaction.user.id] = True
        
        await interaction.response.send_message(
            "Veuillez téléverser un fichier CSV avec les colonnes suivantes (séparées par des point-virgules `;`):\n"
            "**mot;définition;extrait**\n\n"
            "⚠️ **Pour éviter les problèmes avec les virgules dans le texte, utilisez des point-virgules comme séparateurs!**\n\n"
            "Le fichier doit être encodé en UTF-8.\n"
            "📤 **Envoyez simplement votre fichier dans le canal actuel.**",
            ephemeral=True
        )

class MotForm(discord.ui.Modal, title="Ajouter un mot"):
    mot = discord.ui.TextInput(label="Mot")
    definition = discord.ui.TextInput(label="Définition", style=discord.TextStyle.paragraph)
    extrait = discord.ui.TextInput(label="Extrait", style=discord.TextStyle.paragraph)
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: Interaction):
        mot = self.mot.value.strip().lower()
        definition = self.definition.value.strip()
        extrait = self.extrait.value.strip()
        
        # Vérifier si le mot existe déjà
        if mot in self.cog.vocabulary:
            await interaction.response.send_message(f"Le mot '{mot}' existe déjà dans le vocabulaire.", ephemeral=True)
            return
        
        # Rechercher des mots similaires
        similar_words = self.cog.find_similar_words(mot)
        
        if similar_words:
            # Créer un aperçu du mot à ajouter
            embed = discord.Embed(title=f"Nouveau mot : {mot.upper()}", color=0x6d5380)
            embed.add_field(name="Définition", value=definition, inline=False)
            embed.add_field(name="Extrait", value=f"*{extrait}*", inline=False)
            
            # Ajouter les mots similaires
            similar_text = "\n".join([f"• **{word}** (similarité: {sim:.0%})" for word, sim in similar_words[:3]])
            embed.add_field(name="⚠️ Mots similaires déjà existants", value=similar_text, inline=False)
            
            # Créer une vue pour confirmer ou annuler
            view = ConfirmationView(self.cog, [(mot, definition, extrait)])
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            # Aucun mot similaire, prévisualisation simple
            embed = discord.Embed(title=f"Nouveau mot : {mot.upper()}", color=0x6d5380)
            embed.add_field(name="Définition", value=definition, inline=False)
            embed.add_field(name="Extrait", value=f"*{extrait}*", inline=False)
            
            view = ConfirmationView(self.cog, [(mot, definition, extrait)])
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConfirmationView(View):
    def __init__(self, cog, words_data):
        super().__init__()
        self.cog = cog
        self.words_data = words_data  # Liste de tuples (mot, definition, extrait)

    @discord.ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirmer(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        # Utiliser batch_add_words pour ajouter tous les mots d'un coup
        added_words, errors = await self.cog.batch_add_words(self.words_data)
        
        if errors:
            error_msg = "\n".join([f"• {error}" for error in errors])
            await interaction.followup.send(f"✅ {added_words} mot(s) ajouté(s) avec succès.\n\n❌ Erreurs:\n{error_msg}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ {added_words} mot(s) ajouté(s) avec succès.", ephemeral=True)
        
        self.stop()

    @discord.ui.button(label="Annuler", style=ButtonStyle.red)
    async def annuler(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Ajout annulé.", ephemeral=True)
        self.stop()

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
            # Chercher des mots similaires
            similar_words = self.cog.find_similar_words(mot)
            if similar_words:
                similar_text = "\n".join([f"• **{word}** (similarité: {sim:.0%})" for word, sim in similar_words[:5]])
                await interaction.response.send_message(f"Mot non trouvé. Voici des suggestions :\n{similar_text}", ephemeral=True)
            else:
                await interaction.response.send_message("Mot non trouvé.", ephemeral=True)

class Vocabulaire(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vocabulary_channel_id = 1273659420101971970
        self.sheet = self.connect_to_sheets()
        self.vocabulary = self.load_vocabulary()
        self.file_waiting_users = {}  # Pour suivre les utilisateurs qui doivent envoyer un fichier

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
    
    def find_similar_words(self, mot, threshold=0.8):
        """Trouve des mots similaires dans le vocabulaire."""
        similar = []
        for existing_mot in self.vocabulary.keys():
            similarity = SequenceMatcher(None, mot.lower(), existing_mot.lower()).ratio()
            if similarity >= threshold and mot.lower() != existing_mot.lower():
                similar.append((existing_mot, similarity))
        
        return sorted(similar, key=lambda x: x[1], reverse=True)

    async def batch_add_words(self, words_data):
        """Ajoute plusieurs mots en une seule opération."""
        added_words = 0
        errors = []
        words_to_add = []
        
        # Vérifier les mots déjà existants
        for mot, definition, extrait in words_data:
            mot = mot.lower()
            if mot in self.vocabulary:
                errors.append(f"Le mot '{mot}' existe déjà")
            else:
                self.vocabulary[mot] = {"definition": definition, "extrait": extrait}
                words_to_add.append([mot, definition, extrait])
                added_words += 1
        
        if words_to_add:
            # Ajouter les mots au Google Sheet en une seule opération
            self.sheet.append_rows(words_to_add)
            
            # Envoyer les mots dans le canal Discord
            channel = self.bot.get_channel(self.vocabulary_channel_id)
            if channel:
                for mot, definition, extrait in words_to_add:
                    embed = discord.Embed(title=mot.upper(), color=0x6d5380)
                    embed.add_field(name="Définition", value=definition, inline=False)
                    embed.add_field(name="Extrait", value=f"*{extrait}*", inline=False)
                    await channel.send(embed=embed)
        
        return added_words, errors

    async def process_csv_file(self, message):
        """Traite un fichier CSV téléversé."""
        if not message.attachments or not message.attachments[0].filename.endswith('.csv'):
            await message.channel.send("Veuillez téléverser un fichier CSV valide.", reference=message)
            return
        
        attachment = message.attachments[0]
        csv_content = await attachment.read()
        
        try:
            # Décoder le contenu CSV
            csv_text = csv_content.decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_text), delimiter=';')  # Utiliser point-virgule
            
            # Ignorer l'en-tête si présent
            header = next(csv_reader, None)
            if header and any(h.lower() in ['mot', 'definition', 'extrait'] for h in header):
                # C'est probablement un en-tête
                pass
            else:
                # Ce n'est pas un en-tête, revenir au début du fichier
                csv_reader = csv.reader(io.StringIO(csv_text), delimiter=';')  # Utiliser point-virgule
            
            words_data = []
            errors = []
            
            for i, row in enumerate(csv_reader, 1):
                if len(row) < 3:
                    errors.append(f"Ligne {i}: Nombre de colonnes insuffisant")
                    continue
                
                mot, definition, extrait = row[0].strip(), row[1].strip(), row[2].strip()
                if not mot or not definition:
                    errors.append(f"Ligne {i}: Mot ou définition manquante")
                    continue
                
                words_data.append((mot.lower(), definition, extrait))
            
            if not words_data:
                await message.channel.send("Aucun mot valide trouvé dans le fichier CSV.", reference=message)
                return
            
            # Prévisualisation des mots
            embed = discord.Embed(title="Prévisualisation des mots à ajouter", color=0x6d5380)
            
            preview_count = min(10, len(words_data))
            for i in range(preview_count):
                mot, definition, extrait = words_data[i]
                embed.add_field(
                    name=f"{i+1}. {mot.upper()}", 
                    value=f"**Déf.**: {definition[:100]}{'...' if len(definition) > 100 else ''}\n**Ex.**: {extrait[:100]}{'...' if len(extrait) > 100 else ''}", 
                    inline=False
                )
            
            if len(words_data) > preview_count:
                embed.set_footer(text=f"... et {len(words_data) - preview_count} mot(s) supplémentaire(s)")
            
            view = ConfirmationView(self, words_data)
            await message.channel.send(embed=embed, view=view, reference=message)
            
        except Exception as e:
            await message.channel.send(f"Erreur lors du traitement du fichier CSV: {str(e)}", reference=message)

    def get_random_words(self, n):
        return random.sample(list(self.vocabulary.items()), min(n, len(self.vocabulary)))

    def create_words_embed(self, words):
        embed = discord.Embed(title="Vocabulaire", color=0x6d5380)
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
    
    @app_commands.command(name="vocabulaire", description="Ouvrir le panel de gestion du vocabulaire")
    async def vocabulaire(self, interaction: Interaction):
        view = VocabulaireView(self)
        await interaction.response.send_message("Choisissez une action :", view=view, ephemeral=True)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignorer les messages du bot
        if message.author.bot:
            return
            
        # Gérer les fichiers CSV envoyés après la commande d'importation
        if message.author.id in self.file_waiting_users:
            if message.attachments:
                del self.file_waiting_users[message.author.id]
                await self.process_csv_file(message)
            else:
                # Si l'utilisateur envoie un message sans pièce jointe, ne pas consommer son "statut d'attente"
                pass

async def setup(bot):
    await bot.add_cog(Vocabulaire(bot))
    print("Cog Vocabulaire chargé avec succès") 