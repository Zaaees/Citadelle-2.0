"""
Système de surveillance automatique pour les scènes de jeu de rôle Discord.
Permet aux maîtres de jeu (MJ) de suivre l'activité des joueurs et recevoir des notifications.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
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
        
        # Configuration Google Sheets
        try:
            self.credentials = service_account.Credentials.from_service_account_info(
                eval(os.getenv('SERVICE_ACCOUNT_JSON')),
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.gc = gspread.authorize(self.credentials)
            
            # Ouvrir la feuille de calcul
            spreadsheet_id = os.getenv('GOOGLE_SHEET_ID_SURVEILLANCE', os.getenv('GOOGLE_SHEET_ID_ACTIVITE'))
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
            logger.error(f"Erreur initialisation Google Sheets: {e}")
            self.sheet = None
            
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
        # Patterns courants pour les bots RP (Tupperbox, PluralKit, etc.)
        if message.webhook_id:
            # Pour Tupperbox et similaires, chercher dans le nom/contenu
            webhook_name = message.author.display_name.lower()
            
            # Recherche de patterns dans le cache
            if webhook_name in self.webhook_users:
                return self.webhook_users[webhook_name]
                
            # Recherche par patterns dans le contenu ou footer
            if hasattr(message, 'embeds') and message.embeds:
                for embed in message.embeds:
                    if embed.footer and embed.footer.text:
                        # Pattern pour Tupperbox: "Sent by Username"
                        tupperbox_match = re.search(r'Sent by (\w+)', embed.footer.text)
                        if tupperbox_match:
                            username = tupperbox_match.group(1)
                            # Chercher l'utilisateur par nom
                            for member in message.guild.members:
                                if member.display_name.lower() == username.lower():
                                    self.webhook_users[webhook_name] = member.id
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
            color=color,
            timestamp=datetime.now()
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

    @app_commands.command(name="surveiller_scene", description="Démarre la surveillance d'une scène RP")
    @app_commands.describe(
        channel="Le salon, thread ou forum à surveiller (optionnel, utilise le salon actuel si non spécifié)"
    )
    async def start_surveillance(self, interaction: discord.Interaction, 
                               channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]] = None):
        """Commande pour démarrer la surveillance d'une scène."""
        
        if not self.has_mj_permission(interaction.user):
            await interaction.response.send_message("❌ Seuls les MJ peuvent utiliser cette commande.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Utiliser le salon actuel si non spécifié
        target_channel = channel or interaction.channel
        channel_id = str(target_channel.id)
        
        # Vérifier si déjà surveillé
        if channel_id in self.active_scenes:
            await interaction.followup.send(f"❌ Ce salon est déjà surveillé par <@{self.active_scenes[channel_id]['mj_id']}>", 
                                          ephemeral=True)
            return
        
        try:
            # Créer les données de la scène
            now = datetime.now().isoformat()
            scene_data = {
                'channel_id': target_channel.id,
                'mj_id': interaction.user.id,
                'status_channel_id': interaction.channel.id,
                'created_at': now,
                'last_activity': now,
                'participants': [],
                'last_author_id': interaction.user.id,
                'status': 'active'
            }
            
            # Ajouter à active_scenes AVANT de créer l'embed
            self.active_scenes[channel_id] = scene_data
            
            # Créer l'embed de surveillance
            embed = await self.create_scene_embed(channel_id)
            if not embed:
                await interaction.followup.send("❌ Erreur lors de la création du message de surveillance.", ephemeral=True)
                # Nettoyer
                del self.active_scenes[channel_id]
                return
            
            view = SceneSurveillanceView(self, scene_data)
            
            # Envoyer le message de statut
            status_message = await interaction.followup.send(embed=embed, view=view)
            scene_data['status_message_id'] = status_message.id
            
            # Mettre à jour avec l'ID du message
            self.active_scenes[channel_id] = scene_data
            await self.save_scene_to_sheets(scene_data)
            
            # Message de confirmation
            await interaction.followup.send(
                f"✅ Surveillance démarrée pour {target_channel.mention}\n"
                f"📋 Message de suivi créé ci-dessus\n"
                f"🔔 Vous recevrez des notifications privées lors de nouvelle activité",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Erreur lors du démarrage de surveillance: {e}")
            await interaction.followup.send("❌ Erreur lors du démarrage de la surveillance.", ephemeral=True)

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
        if not message.guild or message.author.bot:
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

    async def update_status_message(self, channel_id: str):
        """Met à jour le message de statut d'une scène."""
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
            
            await status_message.edit(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Erreur mise à jour message statut: {e}")

    @tasks.loop(minutes=30)
    async def activity_monitor(self):
        """Tâche de surveillance périodique pour mettre à jour les statuts."""
        for channel_id in list(self.active_scenes.keys()):
            await self.update_status_message(channel_id)

    @tasks.loop(hours=24)
    async def inactivity_checker(self):
        """Vérifie l'inactivité des scènes et envoie des alertes."""
        now = datetime.now()
        
        for channel_id, scene_data in self.active_scenes.items():
            last_activity = scene_data.get('last_activity')
            if not last_activity:
                continue
                
            last_activity_dt = datetime.fromisoformat(last_activity)
            time_diff = now - last_activity_dt
            
            # Alerte après 7 jours d'inactivité
            if time_diff >= timedelta(days=7):
                await self.send_inactivity_alert(scene_data, time_diff.days)

    async def send_inactivity_alert(self, scene_data: dict, days_inactive: int):
        """Envoie une alerte d'inactivité au MJ responsable."""
        mj = self.bot.get_user(scene_data['mj_id'])
        if not mj:
            return
            
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
            
        except Exception as e:
            logger.error(f"Erreur envoi alerte inactivité: {e}")

    @activity_monitor.before_loop
    async def before_activity_monitor(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)  # Attendre 1 minute après le démarrage
        await self.load_active_scenes()  # Charger les scènes existantes

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


async def setup(bot):
    """Fonction d'installation du cog."""
    await bot.add_cog(SceneSurveillance(bot))