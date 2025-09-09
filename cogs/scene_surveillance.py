"""
Système de surveillance automatique pour les scènes de jeu de rôle Discord.
Permet aux maîtres de jeu (MJ) de suivre l'activité des joueurs et recevoir des notifications.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import traceback
import os
import asyncio
import gspread
from google.oauth2 import service_account
import logging
import json
from typing import Dict, List, Optional, Set, Tuple, Union
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SceneSurveillanceView(discord.ui.View):
    """Vue avec boutons interactifs pour la surveillance des scènes."""
    
    def __init__(self, cog, scene_data: dict):
        super().__init__(timeout=None)
        self.cog = cog
        self.scene_data = scene_data

    @discord.ui.button(label="🟢 Reprendre la scène", style=discord.ButtonStyle.green, custom_id="take_over_scene")
    async def take_over_scene(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Permet à un autre MJ de reprendre la responsabilité d'une scène."""
        await interaction.response.defer(ephemeral=True)
        
        if not self.cog.has_mj_permission(interaction.user):
            await interaction.followup.send("❌ Seuls les MJ peuvent utiliser cette fonction.", ephemeral=True)
            return
            
        channel_id = str(self.scene_data['channel_id'])
        old_mj_id = self.scene_data['mj_id']
        new_mj_id = interaction.user.id
        
        if old_mj_id == new_mj_id:
            await interaction.followup.send("❌ Vous êtes déjà le MJ responsable de cette scène.", ephemeral=True)
            return
            
        try:
            # Mettre à jour dans Google Sheets
            await self.cog.update_scene_mj(channel_id, new_mj_id)
            
            # Mettre à jour les données locales
            self.scene_data['mj_id'] = new_mj_id
            self.cog.active_scenes[channel_id]['mj_id'] = new_mj_id
            
            # Mettre à jour le message
            embed = await self.cog.create_scene_embed(channel_id)
            await interaction.edit_original_response(embed=embed, view=self)
            
            # Notification à l'ancien et nouveau MJ
            old_mj = self.cog.bot.get_user(old_mj_id)
            if old_mj:
                try:
                    await old_mj.send(f"📋 **Transfert de scène**\n"
                                    f"{interaction.user.mention} a repris la responsabilité de la scène dans <#{channel_id}>")
                except:
                    pass
                    
            await interaction.followup.send(f"✅ Vous êtes maintenant responsable de la scène dans <#{channel_id}>", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Erreur lors du transfert de scène: {e}")
            await interaction.followup.send("❌ Erreur lors du transfert de la scène.", ephemeral=True)

    @discord.ui.button(label="🔴 Clôturer la scène", style=discord.ButtonStyle.red, custom_id="close_scene")
    async def close_scene(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Clôture une scène surveillée."""
        await interaction.response.defer(ephemeral=True)
        
        if not self.cog.has_mj_permission(interaction.user):
            await interaction.followup.send("❌ Seuls les MJ peuvent utiliser cette fonction.", ephemeral=True)
            return
            
        channel_id = str(self.scene_data['channel_id'])
        
        try:
            # Supprimer la surveillance
            await self.cog.stop_scene_surveillance(channel_id)
            
            # Mettre à jour le message pour indiquer que la scène est fermée
            embed = discord.Embed(
                title="🔴 Scène Clôturée",
                description=f"La surveillance de <#{channel_id}> a été arrêtée.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Clôturée par", value=interaction.user.mention, inline=True)
            
            # Désactiver les boutons
            for item in self.children:
                item.disabled = True
                
            await interaction.edit_original_response(embed=embed, view=self)
            await interaction.followup.send("✅ Scène clôturée avec succès.", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Erreur lors de la clôture de scène: {e}")
            await interaction.followup.send("❌ Erreur lors de la clôture de la scène.", ephemeral=True)


class SceneSurveillance(commands.Cog):
    """Système de surveillance automatique pour les scènes de jeu de rôle."""
    
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone('Europe/Paris')
        self.active_scenes: Dict[str, dict] = {}  # channel_id -> scene_data
        self.webhook_users: Dict[str, int] = {}  # webhook_name -> real_user_id
        self.mj_role_id = 1018179623886000278  # ID du rôle MJ (à adapter)
        
        # Configuration Google Sheets (optionnelle)
        try:
            service_account_json = os.getenv('SERVICE_ACCOUNT_JSON', '{}')
            if service_account_json == '{}':
                raise ValueError("SERVICE_ACCOUNT_JSON non configuré")
                
            self.credentials = service_account.Credentials.from_service_account_info(
                eval(service_account_json),
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.gc = gspread.authorize(self.credentials)
            
            # Ouvrir la feuille de calcul
            spreadsheet_id = os.getenv('GOOGLE_SHEET_ID_SURVEILLANCE', os.getenv('GOOGLE_SHEET_ID_ACTIVITE'))
            if not spreadsheet_id:
                raise ValueError("GOOGLE_SHEET_ID non configuré")
                
            spreadsheet = self.gc.open_by_key(spreadsheet_id)
            
            # Essayer d'accéder à la feuille SceneSurveillance, la créer si elle n'existe pas
            try:
                self.sheet = spreadsheet.worksheet('SceneSurveillance')
                logger.info("Feuille SceneSurveillance trouvée")
            except gspread.WorksheetNotFound:
                logger.info("Création de la feuille SceneSurveillance...")
                self.sheet = spreadsheet.add_worksheet('SceneSurveillance', rows=1000, cols=10)
                
                # Ajouter les en-têtes
                headers = [
                    'channel_id', 'mj_id', 'status_message_id', 'status_channel_id',
                    'created_at', 'last_activity', 'participants', 'last_author_id', 'status'
                ]
                self.sheet.insert_row(headers, 1)
                
                # Formater les en-têtes
                self.sheet.format('A1:I1', {
                    'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.9},
                    'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
                    'horizontalAlignment': 'CENTER'
                })
                
                logger.info("✅ Feuille SceneSurveillance créée et configurée")
                
        except Exception as e:
            logger.warning(f"Google Sheets non disponible: {e}")
            logger.info("SceneSurveillance fonctionnera en mode dégradé (sans persistance)")
            self.sheet = None
            self.gc = None
            
        # Démarrer les tâches de surveillance
        self.activity_monitor.start()
        self.inactivity_checker.start()

    def cog_unload(self):
        """Nettoie les ressources lors du déchargement du cog."""
        try:
            if self.activity_monitor.is_running():
                self.activity_monitor.cancel()
            if self.inactivity_checker.is_running():
                self.inactivity_checker.cancel()
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt des tâches: {e}")

    def has_mj_permission(self, user: discord.Member) -> bool:
        """Vérifie si un utilisateur a le rôle MJ."""
        # Vérifier que c'est bien un Member (pas juste un User)
        if not isinstance(user, discord.Member):
            return False
        return any(role.id == self.mj_role_id for role in user.roles)

    async def load_active_scenes(self):
        """Charge les scènes actives depuis Google Sheets."""
        if not self.sheet:
            logger.warning("Aucune feuille Google Sheets disponible pour charger les scènes")
            return
            
        try:
            records = self.sheet.get_all_records()
            scenes_loaded = 0
            for record in records:
                if record.get('status') == 'active' and record.get('channel_id'):
                    try:
                        channel_id = str(record['channel_id'])
                        self.active_scenes[channel_id] = {
                            'channel_id': int(channel_id),
                            'mj_id': int(record.get('mj_id', 0)),
                            'status_message_id': int(record.get('status_message_id', 0)),
                            'status_channel_id': int(record.get('status_channel_id', 0)),
                            'created_at': record.get('created_at', ''),
                            'last_activity': record.get('last_activity', ''),
                            'participants': json.loads(record.get('participants', '[]')),
                            'last_author_id': int(record.get('last_author_id', 0)),
                            'status': record.get('status', 'active')
                        }
                        scenes_loaded += 1
                    except (ValueError, json.JSONDecodeError) as e:
                        logger.warning(f"Erreur parsing scène {record.get('channel_id')}: {e}")
                        continue
            logger.info(f"✅ {scenes_loaded} scènes actives chargées depuis Google Sheets")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des scènes: {e}")
            logger.info("Le système fonctionnera en mode dégradé (sans persistance)")

    async def save_scene_to_sheets(self, scene_data: dict):
        """Sauvegarde une scène dans Google Sheets."""
        if not self.sheet:
            logger.warning("Impossible de sauvegarder la scène: Google Sheets non disponible")
            return
            
        try:
            channel_id = str(scene_data['channel_id'])
            
            # Chercher si la scène existe déjà
            try:
                cell = self.sheet.find(channel_id)
                row = cell.row
            except gspread.CellNotFound:
                # Nouvelle scène, ajouter une nouvelle ligne
                row = len(self.sheet.get_all_values()) + 1
                
            # Préparer les données (convertir les ID en strings pour éviter la notation scientifique)
            row_data = [
                channel_id,
                str(scene_data['mj_id']),  # Convertir en string
                str(scene_data.get('status_message_id', '')),  # Convertir en string
                str(scene_data.get('status_channel_id', '')),  # Convertir en string
                scene_data['created_at'],
                scene_data.get('last_activity', ''),
                json.dumps(scene_data.get('participants', [])),
                str(scene_data.get('last_author_id', '')),  # Convertir en string
                scene_data['status']
            ]
            
            # Headers pour référence
            if row == 1:
                headers = ['channel_id', 'mj_id', 'status_message_id', 'status_channel_id', 
                          'created_at', 'last_activity', 'participants', 'last_author_id', 'status']
                self.sheet.insert_row(headers, 1)
                row = 2
                
            self.sheet.insert_row(row_data, row)
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde Google Sheets: {e}")

    async def update_scene_mj(self, channel_id: str, new_mj_id: int):
        """Met à jour le MJ responsable d'une scène."""
        if not self.sheet:
            logger.warning("Impossible de mettre à jour le MJ: Google Sheets non disponible")
            return
            
        try:
            cell = self.sheet.find(channel_id)
            self.sheet.update_cell(cell.row, 2, str(new_mj_id))  # Colonne MJ - convertir en string
        except Exception as e:
            logger.error(f"Erreur mise à jour MJ: {e}")

    async def update_scene_activity(self, channel_id: str, last_activity: str, 
                                  participants: List[int], last_author_id: int):
        """Met à jour l'activité d'une scène."""
        if not self.sheet:
            logger.debug("Impossible de mettre à jour l'activité: Google Sheets non disponible")
            return
            
        try:
            cell = self.sheet.find(channel_id)
            row = cell.row
            self.sheet.update_cell(row, 6, last_activity)  # last_activity
            self.sheet.update_cell(row, 7, json.dumps(participants))  # participants
            self.sheet.update_cell(row, 8, str(last_author_id))  # last_author_id - convertir en string
        except Exception as e:
            logger.error(f"Erreur mise à jour activité: {e}")

    def detect_webhook_user(self, message: discord.Message) -> Optional[int]:
        """Détecte l'utilisateur réel derrière un message de webhook/bot RP."""
        # Patterns courants pour les bots RP (Tupperbox, PluralKit, Carl-bot, etc.)
        if message.webhook_id:
            # Pour Tupperbox et similaires, chercher dans le nom/contenu
            webhook_name = message.author.display_name.lower()
            
            # Recherche de patterns dans le cache
            if webhook_name in self.webhook_users:
                return self.webhook_users[webhook_name]
                
            # Patterns pour différents bots RP
            patterns_to_check = []
            
            # Recherche par patterns dans le contenu ou footer
            if hasattr(message, 'embeds') and message.embeds:
                for embed in message.embeds:
                    if embed.footer and embed.footer.text:
                        patterns_to_check.append(embed.footer.text)
                    if embed.author and embed.author.name:
                        patterns_to_check.append(embed.author.name)
            
            # Ajouter le nom du webhook aux patterns à vérifier
            patterns_to_check.append(message.author.display_name)
            
            # Patterns de détection pour différents bots RP
            for pattern_text in patterns_to_check:
                # Tupperbox: "Sent by Username"
                tupperbox_match = re.search(r'Sent by (\w+)', pattern_text)
                if tupperbox_match:
                    username = tupperbox_match.group(1)
                    user_id = self._find_user_by_name(message.guild, username)
                    if user_id:
                        self.webhook_users[webhook_name] = user_id
                        return user_id
                
                # PluralKit: "username#1234" dans footer ou nom
                pluralkit_match = re.search(r'(\w+)#(\d{4})', pattern_text)
                if pluralkit_match:
                    username, discriminator = pluralkit_match.groups()
                    user_id = self._find_user_by_tag(message.guild, username, discriminator)
                    if user_id:
                        self.webhook_users[webhook_name] = user_id
                        return user_id
                
                # Carl-bot et autres: chercher par mention <@user_id>
                mention_match = re.search(r'<@!?(\d+)>', pattern_text)
                if mention_match:
                    user_id = int(mention_match.group(1))
                    # Vérifier que l'utilisateur existe dans le serveur
                    if message.guild.get_member(user_id):
                        self.webhook_users[webhook_name] = user_id
                        return user_id
            
            # Si aucun pattern trouvé, essayer de deviner par le nom du webhook
            user_id = self._find_user_by_name(message.guild, message.author.display_name)
            if user_id:
                self.webhook_users[webhook_name] = user_id
                return user_id
                                    
        return None
    
    def _find_user_by_name(self, guild: discord.Guild, username: str) -> Optional[int]:
        """Trouve un utilisateur par nom d'affichage ou nom d'utilisateur."""
        username_lower = username.lower()
        for member in guild.members:
            if (member.display_name.lower() == username_lower or 
                member.name.lower() == username_lower):
                return member.id
        return None
    
    def _find_user_by_tag(self, guild: discord.Guild, username: str, discriminator: str) -> Optional[int]:
        """Trouve un utilisateur par tag complet (username#discriminator)."""
        for member in guild.members:
            if (member.name.lower() == username.lower() and 
                member.discriminator == discriminator):
                return member.id
        return None

    async def create_scene_embed(self, channel_id: str) -> discord.Embed:
        """Crée un embed élégant pour une scène surveillée."""
        if channel_id not in self.active_scenes:
            return None
            
        scene_data = self.active_scenes[channel_id]
        channel = self.bot.get_channel(int(channel_id))
        mj = self.bot.get_user(scene_data['mj_id'])
        
        # Couleur basée sur l'activité récente
        try:
            last_activity_str = scene_data.get('last_activity', scene_data.get('created_at', datetime.now().isoformat()))
            last_activity = datetime.fromisoformat(last_activity_str)
        except (ValueError, TypeError):
            last_activity = datetime.now()
            logger.warning(f"Erreur parsing last_activity pour scène {channel_id}")
            
        now = datetime.now()
        
        # Uniformiser les timezones pour éviter l'erreur offset-naive vs offset-aware
        if last_activity.tzinfo is not None and now.tzinfo is None:
            # last_activity a une timezone, now n'en a pas → convertir last_activity en naive
            last_activity = last_activity.replace(tzinfo=None)
        elif last_activity.tzinfo is None and now.tzinfo is not None:
            # now a une timezone, last_activity n'en a pas → convertir now en naive  
            now = now.replace(tzinfo=None)
            
        time_diff = now - last_activity
        
        if time_diff < timedelta(hours=6):
            color = discord.Color.green()  # Actif récemment
        elif time_diff < timedelta(days=1):
            color = discord.Color.yellow()  # Activité modérée
        elif time_diff < timedelta(days=3):
            color = discord.Color.orange()  # Peu actif
        else:
            color = discord.Color.red()  # Inactif
            
        embed = discord.Embed(
            title="🎭 Surveillance de Scène RP",
            description=f"**Salon:** {channel.mention if channel else f'<#{channel_id}>'}\n"
                       f"**Type:** {channel.type.name.title() if channel else 'Inconnu'}",
            color=color
            # Timestamp sera défini par la fonction appelante pour le tri
        )
        
        # MJ responsable
        embed.add_field(
            name="🎪 Maître de Jeu",
            value=mj.mention if mj else f"<@{scene_data['mj_id']}>",
            inline=True
        )
        
        # Participants actifs
        participants = scene_data.get('participants', [])
        if participants:
            participant_mentions = []
            for p_id in participants[:10]:  # Limiter à 10 pour éviter les messages trop longs
                participant_mentions.append(f"<@{p_id}>")
            
            participants_text = ", ".join(participant_mentions)
            if len(participants) > 10:
                participants_text += f" et {len(participants) - 10} autres..."
                
            embed.add_field(
                name=f"👥 Participants ({len(participants)})",
                value=participants_text,
                inline=False
            )
        else:
            embed.add_field(
                name="👥 Participants",
                value="*Aucun participant détecté*",
                inline=False
            )
        
        # Dernière activité
        last_activity_str = scene_data.get('last_activity', 'Jamais')
        if last_activity_str != 'Jamais' and last_activity_str:
            try:
                last_activity_dt = datetime.fromisoformat(last_activity_str)
                embed.add_field(
                    name="⏰ Dernière activité",
                    value=f"<t:{int(last_activity_dt.timestamp())}:R>",
                    inline=True
                )
            except (ValueError, TypeError):
                embed.add_field(
                    name="⏰ Dernière activité",
                    value="Erreur de format",
                    inline=True
                )
        else:
            embed.add_field(
                name="⏰ Dernière activité",
                value="Jamais",
                inline=True
            )
        
        # Dernière action
        last_author_id = scene_data.get('last_author_id')
        if last_author_id:
            embed.add_field(
                name="✍️ Dernière action par",
                value=f"<@{last_author_id}>",
                inline=True
            )
        
        # Status indicator
        status_emoji = {
            timedelta(hours=6): "🟢 Très actif",
            timedelta(days=1): "🟡 Modérément actif", 
            timedelta(days=3): "🟠 Peu actif",
            timedelta(days=7): "🔴 Inactif"
        }
        
        for threshold, status in status_emoji.items():
            if time_diff < threshold:
                embed.add_field(name="📊 Statut", value=status, inline=True)
                break
        else:
            embed.add_field(name="📊 Statut", value="🔴 Très inactif", inline=True)
        
        embed.set_footer(text="Surveillance automatique • Utilisez les boutons pour gérer la scène")
        
        return embed

    @app_commands.command(name="mj", description="Affiche la liste des commandes MJ disponibles")
    async def mj_commands(self, interaction: discord.Interaction):
        """Commande pour lister toutes les commandes MJ disponibles."""
        
        if not self.has_mj_permission(interaction.user):
            await interaction.response.send_message("❌ Seuls les MJ peuvent utiliser cette commande.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎭 Commandes MJ Disponibles",
            description="Liste des commandes préfixées `!` accessibles aux MJ et Admins",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        # Commandes de surveillance
        embed.add_field(
            name="🎬 Surveillance de Scènes",
            value="`!surveiller_scene [canal]` - Démarre la surveillance automatique d'une scène RP\n"
                  "`!scenes_actives` - Liste les scènes actuellement surveillées\n"
                  "`!reattribuer_scene @nouveau_mj [canal]` - Réattribue une scène à un autre MJ\n"
                  "📡 *Scanner automatique toutes les 15 min pour détecter l'activité réelle*",
            inline=False
        )
        
        # Commandes d'inventaire
        embed.add_field(
            name="🏅 Gestion Inventaire", 
            value="`!medaille @user nombre` - Ajouter des médailles\n"
                  "`!unmedaille @user nombre` - Retirer des médailles\n"
                  "`!lier nom_personnage @user` - Associer personnage à utilisateur",
            inline=False
        )
        
        # Commandes cartes (Admin uniquement)
        embed.add_field(
            name="🎴 Gestion Cartes (Admin)",
            value="`!initialiser_forum_cartes` - Initialise structure forum cartes\n"
                  "`!reconstruire_mur [catégorie]` - Reconstruit le mur de cartes\n"
                  "`!galerie [@user]` - Affiche galerie cartes d'un utilisateur\n"
                  "`!give_bonus @user nombre source` - Donner cartes bonus\n"
                  "`!logs_cartes [user_id] [limit]` - Voir logs cartes\n"
                  "`!stats_logs` - Statistiques des logs\n"
                  "`!verifier_full_automatique` - Vérifie conversions Full auto\n"
                  "`!verifier_integrite` - Vérifie intégrité données cartes",
            inline=False
        )
        
        # Commandes système
        embed.add_field(
            name="⚙️ Système",
            value="`!validation` - Envoie le message de validation\n"
                  "`!ajouter-sous-element` - Ajouter un nouveau sous-élément\n"
                  "`!verifier_inactifs` - Vérifier utilisateurs inactifs\n"
                  "`!bumpstatus` - État du système de bump",
            inline=False
        )
        
        embed.set_footer(text="💡 Utilisez ! devant chaque commande • Commandes visibles uniquement par vous")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="sync_commands", help="Force la synchronisation des commandes slash (MJ uniquement)")
    async def sync_commands(self, ctx):
        """Commande pour forcer la synchronisation des commandes slash."""
        
        if not self.has_mj_permission(ctx.author):
            await ctx.send("❌ Seuls les MJ peuvent utiliser cette commande.")
            return
        
        try:
            # Nettoyer d'abord les commandes du serveur pour éviter les doublons
            await ctx.send("🧹 Nettoyage des commandes du serveur...")
            self.bot.tree.clear_commands(guild=ctx.guild)
            
            # Synchronisation propre pour ce serveur spécifiquement
            await ctx.send("🔄 Synchronisation propre des commandes...")
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"✅ {len(synced)} commandes synchronisées PROPREMENT pour ce serveur !")
            logger.info(f"🔄 Sync forcée PROPRE par {ctx.author}: {len(synced)} commandes (sans doublons)")
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la synchronisation: {e}")
            logger.error(f"❌ Erreur sync forcée: {e}")

    @commands.command(name="debug_commands", help="Diagnostiquer les commandes du bot (MJ uniquement)")
    async def debug_commands(self, ctx):
        """Commande pour diagnostiquer l'état des commandes du bot."""
        
        if not self.has_mj_permission(ctx.author):
            await ctx.send("❌ Seuls les MJ peuvent utiliser cette commande.")
            return
        
        try:
            # Compter les commandes dans le tree
            guild_commands = self.bot.tree.get_commands(guild=ctx.guild)
            global_commands = self.bot.tree.get_commands(guild=None)
            
            embed = discord.Embed(
                title="🔍 Diagnostic des Commandes",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="📊 Commandes dans le Tree",
                value=f"Serveur: {len(guild_commands)}\nGlobales: {len(global_commands)}",
                inline=True
            )
            
            # Lister les commandes du serveur
            if guild_commands:
                guild_names = [f"`/{cmd.name}`" for cmd in guild_commands[:10]]
                embed.add_field(
                    name="🎯 Commandes Serveur",
                    value="\n".join(guild_names) + ("..." if len(guild_commands) > 10 else ""),
                    inline=False
                )
            
            # Informations sur les cogs
            cog_count = len(self.bot.cogs)
            embed.add_field(
                name="🧩 Extensions Chargées",
                value=f"{cog_count} cogs actifs",
                inline=True
            )
            
            await ctx.send(embed=embed)
            logger.info(f"🔍 Debug commandes par {ctx.author}: {len(guild_commands)} serveur, {len(global_commands)} global")
            
        except Exception as e:
            await ctx.send(f"❌ Erreur lors du diagnostic: {e}")
            logger.error(f"❌ Erreur debug commandes: {e}")

    @commands.command(name="surveiller_scene", help="Démarre la surveillance d'une scène RP")
    async def start_surveillance(self, ctx: commands.Context, 
                               channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]] = None):
        """Commande pour démarrer la surveillance d'une scène."""
        
        if not self.has_mj_permission(ctx.author):
            await ctx.send("❌ Seuls les MJ peuvent utiliser cette commande.")
            return
        
        # Utiliser le salon actuel si non spécifié
        target_channel = channel or ctx.channel
        channel_id = str(target_channel.id)
        
        # Vérifier si déjà surveillé
        if channel_id in self.active_scenes:
            await ctx.send(f"❌ Ce salon est déjà surveillé par <@{self.active_scenes[channel_id]['mj_id']}>")
            return
        
        try:
            logger.info(f"🚀 Démarrage surveillance pour canal {target_channel.id} par {ctx.author.id}")
            
            # Scanner l'historique récent pour initialiser les données correctement
            participants = []
            last_activity = datetime.now().isoformat()
            last_author_id = ctx.author.id
            
            try:
                logger.info(f"📋 Scan historique canal {target_channel.name}...")
                # Récupérer les 50 derniers messages pour analyser l'activité
                first_message = True
                async for message in target_channel.history(limit=50):
                    if message.author.bot and not message.webhook_id:
                        continue  # Ignorer les bots non-webhook
                    
                    # Détecter l'utilisateur réel (webhook ou utilisateur normal)
                    real_user_id = self.detect_webhook_user(message) or message.author.id
                    
                    # Ajouter aux participants s'il n'y est pas déjà
                    if real_user_id not in participants:
                        participants.append(real_user_id)
                    
                    # Le premier message valide (le plus récent) définit la dernière activité
                    if first_message:
                        last_activity = message.created_at.isoformat()
                        last_author_id = real_user_id
                        first_message = False
                        
            except Exception as e:
                logger.warning(f"Erreur lors du scan de l'historique: {e}")
            
            logger.info(f"✅ Scan terminé: {len(participants)} participants trouvés")
            
            # Créer les données de la scène avec les vraies données
            now = datetime.now().isoformat()
            scene_data = {
                'channel_id': target_channel.id,
                'mj_id': ctx.author.id,
                'status_channel_id': ctx.channel.id,
                'created_at': now,
                'last_activity': last_activity,
                'participants': participants,
                'last_author_id': last_author_id,
                'status': 'active'
            }
            
            # Ajouter à active_scenes AVANT de créer l'embed
            logger.info(f"💾 Ajout scène aux actives: {channel_id}")
            self.active_scenes[channel_id] = scene_data
            
            # Créer l'embed de surveillance
            logger.info(f"🎨 Création embed surveillance...")
            embed = await self.create_scene_embed(channel_id)
            if not embed:
                await ctx.send("❌ Erreur lors de la création du message de surveillance.")
                # Nettoyer
                del self.active_scenes[channel_id]
                return
            
            # Appliquer le timestamp de tri dès la création
            sort_timestamp = self.calculate_sort_timestamp(scene_data)
            embed.timestamp = sort_timestamp
            
            view = SceneSurveillanceView(self, scene_data)
            
            # Envoyer le message de statut comme message indépendant (pas de réponse)
            logger.info(f"📤 Envoi message surveillance...")
            status_message = await ctx.channel.send(embed=embed, view=view)
            scene_data['status_message_id'] = status_message.id
            logger.info(f"✅ Message envoyé: {status_message.id}")
            
            # Mettre à jour avec l'ID du message
            self.active_scenes[channel_id] = scene_data
            await self.save_scene_to_sheets(scene_data)
            
            # Réponse silencieuse - pas de message de confirmation
            logger.info(f"✅ Surveillance démarrée pour {target_channel.name}")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage de surveillance: {e}")
            logger.error(f"🔍 Type erreur: {type(e).__name__}")
            logger.error(f"🔍 Détails: {str(e)}")
            import traceback
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            await ctx.send(f"❌ Erreur lors du démarrage de la surveillance: {e}")

    async def stop_scene_surveillance(self, channel_id: str):
        """Arrête la surveillance d'une scène."""
        if channel_id in self.active_scenes:
            # Mettre à jour le statut dans Google Sheets
            if self.sheet:
                try:
                    cell = self.sheet.find(channel_id)
                    self.sheet.update_cell(cell.row, 9, 'closed')  # Status
                except:
                    pass
                    
            # Supprimer des scènes actives
            del self.active_scenes[channel_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Surveille les nouveaux messages dans les scènes surveillées."""
        if not message.guild:
            return
            
        # Ignorer les bots SAUF les webhooks RP (qui sont des bots techniques mais représentent des joueurs)
        if message.author.bot and not message.webhook_id:
            return
            
        channel_id = str(message.channel.id)
        if channel_id not in self.active_scenes:
            return
            
        scene_data = self.active_scenes[channel_id]
        
        # Déterminer l'auteur réel (gestion webhooks)
        real_author_id = message.author.id
        if message.webhook_id:
            detected_user = self.detect_webhook_user(message)
            if detected_user:
                real_author_id = detected_user
        
        # Ignorer les messages du système et des bots (sauf webhooks RP)
        if message.type != discord.MessageType.default and not message.webhook_id:
            return
            
        # Mettre à jour les données de la scène
        now = datetime.now().isoformat()
        participants = scene_data.get('participants', [])
        
        if real_author_id not in participants:
            participants.append(real_author_id)
            
        scene_data['last_activity'] = now
        scene_data['participants'] = participants
        scene_data['last_author_id'] = real_author_id
        
        # Mettre à jour Google Sheets
        await self.update_scene_activity(channel_id, now, participants, real_author_id)
        
        # Notifier le MJ responsable
        await self.notify_mj(scene_data, message, real_author_id)
        
        # Mettre à jour le message de statut
        await self.update_status_message(channel_id)

    # Les événements on_message_delete sont remplacés par le scanner périodique
    # qui détecte automatiquement tous les changements d'activité

    async def notify_mj(self, scene_data: dict, message: discord.Message, real_author_id: int):
        """Envoie une notification privée au MJ responsable."""
        mj = self.bot.get_user(scene_data['mj_id'])
        if not mj:
            return
            
        # Éviter le spam - ne notifier que si la dernière activité date de plus de 30 minutes
        last_activity = scene_data.get('last_activity')
        if last_activity:
            last_dt = datetime.fromisoformat(last_activity)
            if (datetime.now() - last_dt) < timedelta(minutes=30):
                return
        
        try:
            channel = message.channel
            author = self.bot.get_user(real_author_id) or message.author
            
            embed = discord.Embed(
                title="🔔 Nouvelle activité dans une scène surveillée",
                description=f"**Salon:** {channel.mention}\n"
                           f"**Auteur:** {author.mention}\n"
                           f"**Message:** {message.content[:200]}{'...' if len(message.content) > 200 else ''}",
                color=discord.Color.blue(),
                timestamp=message.created_at
            )
            
            embed.add_field(name="🔗 Lien direct", value=f"[Aller au message]({message.jump_url})", inline=True)
            
            await mj.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Erreur notification MJ: {e}")

    def calculate_sort_timestamp(self, scene_data: dict) -> datetime:
        """Calcule un timestamp de tri pour que les scènes inactives remontent."""
        try:
            last_activity_str = scene_data.get('last_activity', scene_data.get('created_at', datetime.now().isoformat()))
            last_activity = datetime.fromisoformat(last_activity_str)
        except (ValueError, TypeError):
            last_activity = datetime.now()
        
        now = datetime.now()
        
        # Uniformiser les timezones pour éviter l'erreur offset-naive vs offset-aware
        if last_activity.tzinfo is not None and now.tzinfo is None:
            # last_activity a une timezone, now n'en a pas → convertir now en naive
            last_activity = last_activity.replace(tzinfo=None)
        elif last_activity.tzinfo is None and now.tzinfo is not None:
            # now a une timezone, last_activity n'en a pas → convertir last_activity en naive  
            now = now.replace(tzinfo=None)
            
        time_diff = now - last_activity
        
        # Logique de tri : plus c'est inactif, plus le timestamp est récent (pour remonter)
        # Base : timestamp actuel moins l'inactivité (inversé)
        if time_diff < timedelta(hours=6):
            # Très actif : timestamp ancien (reste en bas)
            sort_timestamp = now - timedelta(days=7)
        elif time_diff < timedelta(days=1):
            # Modérément actif : timestamp un peu plus récent
            sort_timestamp = now - timedelta(days=5)
        elif time_diff < timedelta(days=3):
            # Peu actif : timestamp plus récent
            sort_timestamp = now - timedelta(days=2)
        else:
            # Inactif : timestamp très récent (remonte en haut)
            # Plus c'est inactif, plus ça remonte
            days_inactive = min(time_diff.days, 30)  # Cap à 30 jours
            sort_timestamp = now - timedelta(hours=days_inactive)
            
        return sort_timestamp

    async def update_status_message(self, channel_id: str, force_reorder: bool = False):
        """Met à jour le message de statut d'une scène avec tri intelligent."""
        if channel_id not in self.active_scenes:
            return
            
        scene_data = self.active_scenes[channel_id]
        status_message_id = scene_data.get('status_message_id')
        status_channel_id = scene_data.get('status_channel_id')
        
        if not status_message_id or not status_channel_id:
            return
            
        try:
            status_channel = self.bot.get_channel(status_channel_id)
            if not status_channel:
                return
                
            status_message = await status_channel.fetch_message(status_message_id)
            embed = await self.create_scene_embed(channel_id)
            view = SceneSurveillanceView(self, scene_data)
            
            # Calculer le timestamp de tri pour l'embed
            sort_timestamp = self.calculate_sort_timestamp(scene_data)
            embed.timestamp = sort_timestamp
            
            await status_message.edit(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Erreur mise à jour message statut: {e}")

    @tasks.loop(minutes=5)
    async def activity_monitor(self):
        """Tâche de surveillance périodique qui scanne l'historique réel des canaux."""
        logger.info(f"🔄 Scanner périodique de {len(self.active_scenes)} scènes surveillées...")
        
        for channel_id in list(self.active_scenes.keys()):
            try:
                # Scanner l'historique réel du canal pour détecter les changements
                await self.scan_channel_activity(channel_id)
                # Mettre à jour le message de statut
                await self.update_status_message(channel_id)
                # Petit délai pour éviter le rate limiting
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Erreur lors du scan de la scène {channel_id}: {e}")
                
        logger.info("✅ Scanner périodique terminé")

    async def scan_channel_activity(self, channel_id: str):
        """Scanne l'historique réel d'un canal pour détecter l'activité actuelle."""
        if channel_id not in self.active_scenes:
            return
            
        scene_data = self.active_scenes[channel_id]
        channel = self.bot.get_channel(int(channel_id))
        
        if not channel:
            logger.warning(f"Canal {channel_id} introuvable pour scan activité")
            return
            
        try:
            # Scanner les 100 derniers messages pour être sûr de capturer l'activité
            current_participants = []
            current_last_activity = None
            current_last_author_id = None
            
            logger.debug(f"🔍 Scan historique canal {channel.name}...")
            
            async for message in channel.history(limit=100):
                # Ignorer les bots système mais garder les webhooks RP
                if message.author.bot and not message.webhook_id:
                    continue
                    
                # Ignorer les messages système (sauf pour les webhooks qui peuvent avoir des types spéciaux)
                if message.type != discord.MessageType.default and not message.webhook_id:
                    continue
                    
                # Déterminer l'auteur réel
                real_author_id = message.author.id
                if message.webhook_id:
                    detected_user = self.detect_webhook_user(message)
                    if detected_user:
                        real_author_id = detected_user
                
                # Ajouter aux participants
                if real_author_id not in current_participants:
                    current_participants.append(real_author_id)
                
                # Le premier message valide est le plus récent (dernière activité)
                if current_last_activity is None:
                    current_last_activity = message.created_at.isoformat()
                    current_last_author_id = real_author_id
                    
            # Vérifier s'il y a eu des changements
            old_last_activity = scene_data.get('last_activity')
            old_participants = set(scene_data.get('participants', []))
            new_participants = set(current_participants)
            
            changes_detected = False
            
            # Détecter les changements d'activité
            if current_last_activity != old_last_activity:
                changes_detected = True
                logger.info(f"🔄 Changement d'activité détecté pour {channel_id}")
                
            # Détecter les changements de participants
            if old_participants != new_participants:
                changes_detected = True
                added = new_participants - old_participants
                removed = old_participants - new_participants
                if added:
                    logger.info(f"➕ Nouveaux participants détectés pour {channel_id}: {len(added)}")
                if removed:
                    logger.info(f"➖ Participants supprimés détectés pour {channel_id}: {len(removed)}")
            
            # Mettre à jour les données si nécessaire
            if changes_detected:
                if current_last_activity:
                    scene_data['last_activity'] = current_last_activity
                    scene_data['last_author_id'] = current_last_author_id
                else:
                    # Aucun message trouvé, marquer comme inactive depuis la création
                    scene_data['last_activity'] = scene_data.get('created_at', datetime.now().isoformat())
                    scene_data['last_author_id'] = scene_data.get('mj_id')
                
                scene_data['participants'] = current_participants
                self.active_scenes[channel_id] = scene_data
                
                # Sauvegarder dans Google Sheets
                await self.update_scene_activity(
                    channel_id, 
                    scene_data['last_activity'], 
                    current_participants, 
                    scene_data['last_author_id']
                )
                
                logger.info(f"✅ Données mises à jour pour {channel_id}: {len(current_participants)} participants")
            else:
                logger.debug(f"✓ Aucun changement pour {channel_id}")
                
        except Exception as e:
            logger.error(f"Erreur lors du scan d'activité pour {channel_id}: {e}")

    @tasks.loop(hours=24)
    async def inactivity_checker(self):
        """Vérifie l'inactivité des scènes et envoie des alertes."""
        try:
            logger.info("🔍 Démarrage vérification inactivité des scènes...")
            now = datetime.now()
            
            for channel_id, scene_data in self.active_scenes.items():
                last_activity = scene_data.get('last_activity')
                if not last_activity:
                    continue
                
                try:
                    last_activity_dt = datetime.fromisoformat(last_activity)
                except (ValueError, TypeError):
                    continue
                
                # Uniformiser les timezones pour éviter l'erreur offset-naive vs offset-aware
                if last_activity_dt.tzinfo is not None and now.tzinfo is None:
                    # last_activity_dt a une timezone, now n'en a pas → convertir last_activity_dt en naive
                    last_activity_dt = last_activity_dt.replace(tzinfo=None)
                elif last_activity_dt.tzinfo is None and now.tzinfo is not None:
                    # now a une timezone, last_activity_dt n'en a pas → convertir now en naive  
                    now = now.replace(tzinfo=None)
                    
                time_diff = now - last_activity_dt
                
                # Alerte après 7 jours d'inactivité
                if time_diff >= timedelta(days=7):
                    # Vérifier si une alerte a déjà été envoyée récemment
                    last_alert = scene_data.get('last_alert_sent')
                    should_send_alert = True
                    
                    if last_alert:
                        try:
                            last_alert_dt = datetime.fromisoformat(last_alert)
                            # Uniformiser les timezones - CORRECTION BUG CRITIQUE
                            if last_alert_dt.tzinfo is not None and now.tzinfo is None:
                                last_alert_dt = last_alert_dt.replace(tzinfo=None)
                                now_for_alert = now  # CORRIGÉ: now_for_alert était non défini
                            elif last_alert_dt.tzinfo is None and now.tzinfo is not None:
                                now_for_alert = now.replace(tzinfo=None)
                            else:
                                now_for_alert = now
                                
                            time_since_alert = now_for_alert - last_alert_dt
                            # Ne envoyer qu'une alerte par jour maximum
                            should_send_alert = time_since_alert >= timedelta(hours=23)
                        except (ValueError, TypeError):
                            should_send_alert = True
                    
                    if should_send_alert:
                        success = await self.send_inactivity_alert(scene_data, time_diff.days)
                        if success:
                            # Mettre à jour la date de dernière alerte
                            scene_data['last_alert_sent'] = now.isoformat()
                            self.active_scenes[channel_id] = scene_data
                            # Sauvegarder en Google Sheets si possible
                            await self.update_scene_alert_date(channel_id, now.isoformat())
            
            logger.info("✅ Vérification inactivité terminée")
        except Exception as e:
            logger.error(f"❌ ERREUR CRITIQUE dans inactivity_checker: {e}")
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            # Ne pas faire planter le bot, juste logger l'erreur

    async def send_inactivity_alert(self, scene_data: dict, days_inactive: int) -> bool:
        """Envoie une alerte d'inactivité au MJ responsable. Retourne True si envoyée avec succès."""
        mj = self.bot.get_user(scene_data['mj_id'])
        if not mj:
            logger.warning(f"MJ {scene_data['mj_id']} introuvable pour alerte inactivité")
            return False
            
        try:
            channel_id = scene_data['channel_id']
            
            embed = discord.Embed(
                title="⚠️ Alerte d'inactivité - Scène RP",
                description=f"La scène dans <#{channel_id}> n'a pas eu d'activité depuis **{days_inactive} jours**.",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="🎯 Actions recommandées",
                value="• Relancer la scène avec les participants\n"
                      "• Clôturer la scène si elle est terminée\n"
                      "• Transférer à un autre MJ si nécessaire",
                inline=False
            )
            
            embed.add_field(
                name="🔗 Gérer la scène",
                value=f"Utilisez les boutons du message de surveillance pour clôturer ou transférer la scène.",
                inline=False
            )
            
            await mj.send(embed=embed)
            logger.info(f"📨 Alerte inactivité envoyée au MJ {mj.display_name} pour scène {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi alerte inactivité: {e}")
            return False

    async def update_scene_alert_date(self, channel_id: str, alert_date: str):
        """Met à jour la date de dernière alerte d'une scène dans Google Sheets."""
        if not self.sheet:
            logger.debug("Impossible de mettre à jour date alerte: Google Sheets non disponible")
            return
            
        try:
            # Trouver la ligne de la scène et mettre à jour la colonne de dernière alerte
            # (On assumera qu'une nouvelle colonne sera ajoutée au Google Sheets pour cela)
            cell = self.sheet.find(channel_id)
            # Colonne 8 pour last_alert_sent (à ajuster selon votre structure)
            self.sheet.update_cell(cell.row, 8, alert_date)
        except Exception as e:
            logger.error(f"Erreur mise à jour date alerte: {e}")

    @activity_monitor.before_loop
    async def before_activity_monitor(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)  # Attendre 1 minute après le démarrage
        await self.load_active_scenes()  # Charger les scènes existantes
        
        # Faire un scan initial complet pour détecter les changements pendant que le bot était hors ligne
        logger.info("🚀 Scanner initial complet au démarrage...")
        for channel_id in list(self.active_scenes.keys()):
            try:
                await self.scan_channel_activity(channel_id)
                await asyncio.sleep(2)  # Délai plus long pour éviter le rate limiting au démarrage
            except Exception as e:
                logger.error(f"Erreur scan initial {channel_id}: {e}")
        logger.info("✅ Scanner initial terminé")

    @inactivity_checker.before_loop
    async def before_inactivity_checker(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(300)  # Attendre 5 minutes après le démarrage


    @app_commands.command(name="scenes_actives", description="Affiche la liste des scènes actuellement surveillées")
    async def list_active_scenes(self, interaction: discord.Interaction):
        """Commande pour lister les scènes actives."""
        if not self.has_mj_permission(interaction.user):
            await interaction.response.send_message("❌ Seuls les MJ peuvent utiliser cette commande.", ephemeral=True)
            return
            
        if not self.active_scenes:
            await interaction.response.send_message("📭 Aucune scène n'est actuellement surveillée.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="📋 Scènes RP Surveillées",
            description=f"Total: {len(self.active_scenes)} scène(s) active(s)",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        for channel_id, scene_data in self.active_scenes.items():
            channel = self.bot.get_channel(int(channel_id))
            mj = self.bot.get_user(scene_data['mj_id'])
            
            last_activity = scene_data.get('last_activity', 'Jamais')
            if last_activity != 'Jamais':
                last_activity_dt = datetime.fromisoformat(last_activity)
                time_since = f"<t:{int(last_activity_dt.timestamp())}:R>"
            else:
                time_since = "Jamais"
                
            embed.add_field(
                name=f"🎭 {channel.name if channel else f'Canal #{channel_id}'}",
                value=f"**MJ:** {mj.mention if mj else 'Inconnu'}\n"
                      f"**Participants:** {len(scene_data.get('participants', []))}\n"
                      f"**Dernière activité:** {time_since}",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="reattribuer_scene", help="Réattribue une scène surveillée à un autre MJ")
    async def reassign_scene(self, ctx: commands.Context, 
                           nouveau_mj: discord.Member,
                           channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]] = None):
        """Commande pour réattribuer une scène surveillée à un autre MJ."""
        
        # Vérifier que l'utilisateur a les permissions MJ
        if not self.has_mj_permission(ctx.author):
            await ctx.send("❌ Seuls les MJ peuvent utiliser cette commande.")
            return
        
        # Vérifier que le nouveau MJ a aussi les permissions MJ
        if not self.has_mj_permission(nouveau_mj):
            await ctx.send(f"❌ {nouveau_mj.mention} n'a pas le rôle MJ requis.")
            return
        
        # Utiliser le salon actuel si non spécifié
        target_channel = channel or ctx.channel
        channel_id = str(target_channel.id)
        
        # Vérifier que la scène est surveillée
        if channel_id not in self.active_scenes:
            await ctx.send(f"❌ Le salon {target_channel.mention} n'est pas actuellement surveillé.")
            return
        
        scene_data = self.active_scenes[channel_id]
        ancien_mj_id = scene_data['mj_id']
        
        # Vérifier qu'il y a effectivement un changement
        if ancien_mj_id == nouveau_mj.id:
            await ctx.send(f"❌ {nouveau_mj.mention} est déjà le MJ responsable de cette scène.")
            return
        
        try:
            # Mettre à jour les données locales
            scene_data['mj_id'] = nouveau_mj.id
            self.active_scenes[channel_id] = scene_data
            
            # Mettre à jour dans Google Sheets
            await self.update_scene_mj(channel_id, nouveau_mj.id)
            
            # Mettre à jour le message de surveillance s'il existe
            await self.update_status_message(channel_id)
            
            # Notifications
            ancien_mj = self.bot.get_user(ancien_mj_id)
            
            # Message de confirmation publique
            embed = discord.Embed(
                title="🔄 Scène Réattribuée",
                description=f"La responsabilité de la surveillance de {target_channel.mention} a été transférée.",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="🎭 Ancien MJ", 
                value=ancien_mj.mention if ancien_mj else f"<@{ancien_mj_id}>", 
                inline=True
            )
            embed.add_field(
                name="🎪 Nouveau MJ", 
                value=nouveau_mj.mention, 
                inline=True
            )
            embed.add_field(
                name="👤 Réattribué par", 
                value=ctx.author.mention, 
                inline=True
            )
            
            await ctx.send(embed=embed)
            
            # Notification privée à l'ancien MJ
            if ancien_mj and ancien_mj.id != ctx.author.id:
                try:
                    embed_notification = discord.Embed(
                        title="📋 Transfert de Responsabilité",
                        description=f"La surveillance de {target_channel.mention} vous a été retirée.",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    embed_notification.add_field(
                        name="🎪 Nouveau MJ responsable", 
                        value=nouveau_mj.mention, 
                        inline=True
                    )
                    embed_notification.add_field(
                        name="👤 Changement effectué par", 
                        value=ctx.author.mention, 
                        inline=True
                    )
                    await ancien_mj.send(embed=embed_notification)
                except discord.HTTPException:
                    logger.warning(f"Impossible d'envoyer notification à l'ancien MJ {ancien_mj_id}")
            
            # Notification privée au nouveau MJ (si différent de celui qui fait la commande)
            if nouveau_mj.id != ctx.author.id:
                try:
                    embed_notification = discord.Embed(
                        title="🎭 Nouvelle Responsabilité",
                        description=f"Vous êtes maintenant responsable de la surveillance de {target_channel.mention}.",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed_notification.add_field(
                        name="👤 Attribué par", 
                        value=ctx.author.mention, 
                        inline=True
                    )
                    embed_notification.add_field(
                        name="📊 Participants actuels", 
                        value=f"{len(scene_data.get('participants', []))} participant(s)", 
                        inline=True
                    )
                    await nouveau_mj.send(embed=embed_notification)
                except discord.HTTPException:
                    logger.warning(f"Impossible d'envoyer notification au nouveau MJ {nouveau_mj.id}")
            
            logger.info(f"🔄 Scène {channel_id} réattribuée: {ancien_mj_id} → {nouveau_mj.id} par {ctx.author.id}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la réattribution de scène: {e}")
            await ctx.send("❌ Erreur lors de la réattribution de la scène. Consultez les logs pour plus de détails.")


async def setup(bot):
    """Fonction d'installation du cog."""
    await bot.add_cog(SceneSurveillance(bot))