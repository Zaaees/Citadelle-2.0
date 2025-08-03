"""
Cog de surveillance de scènes RP.
Permet de surveiller l'activité dans les salons, threads et forums.
"""

import discord
from discord.ext import commands, tasks
import os
import json
import logging
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
import re
from typing import Optional, Dict, List, Union

# Configuration
SURVEILLANCE_CHANNEL_ID = 1380704586016362626
PARIS_TZ = pytz.timezone('Europe/Paris')

class SceneSurveillanceView(discord.ui.View):
    """Vue avec boutons pour la surveillance de scène."""
    
    def __init__(self, cog, scene_data: dict):
        super().__init__(timeout=None)
        self.cog = cog
        self.scene_data = scene_data
        
    @discord.ui.button(label="📝 Reprendre la scène", style=discord.ButtonStyle.primary, custom_id="take_scene")
    async def take_scene(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Permet à un utilisateur de reprendre la direction d'une scène."""
        try:
            # Mettre à jour le MJ dans les données
            old_gm_id = self.scene_data.get('gm_id')
            new_gm_id = str(interaction.user.id)
            
            # Mettre à jour dans Google Sheets
            await self.cog.update_scene_gm(self.scene_data['channel_id'], new_gm_id)
            
            # Mettre à jour les données locales
            self.scene_data['gm_id'] = new_gm_id
            
            # Notifier l'ancien et le nouveau MJ
            if old_gm_id != new_gm_id:
                old_gm = self.cog.bot.get_user(int(old_gm_id)) if old_gm_id else None
                if old_gm:
                    try:
                        await old_gm.send(f"📝 **Changement de MJ**\n{interaction.user.mention} a repris la direction de la scène **{self.scene_data['scene_name']}**.")
                    except:
                        pass
                
                try:
                    await interaction.user.send(f"📝 **Scène reprise**\nVous dirigez maintenant la scène **{self.scene_data['scene_name']}**.")
                except:
                    pass
            
            # Mettre à jour l'embed
            embed = await self.cog.create_surveillance_embed(self.scene_data)
            await interaction.response.edit_message(embed=embed, view=self)
            
        except Exception as e:
            logging.error(f"Erreur lors de la reprise de scène: {e}")
            await interaction.response.send_message("❌ Erreur lors de la reprise de la scène.", ephemeral=True)
    
    @discord.ui.button(label="🔒 Clôturer la scène", style=discord.ButtonStyle.danger, custom_id="close_scene")
    async def close_scene(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Clôture la surveillance d'une scène."""
        try:
            # Supprimer de Google Sheets
            await self.cog.remove_scene_surveillance(self.scene_data['channel_id'])
            
            # Notifier le MJ
            gm = self.cog.bot.get_user(int(self.scene_data['gm_id']))
            if gm:
                try:
                    await gm.send(f"🔒 **Scène clôturée**\nLa surveillance de la scène **{self.scene_data['scene_name']}** a été fermée par {interaction.user.mention}.")
                except:
                    pass
            
            # Désactiver tous les boutons et mettre à jour le message
            for child in self.children:
                child.disabled = True
            
            embed = discord.Embed(
                title="🔒 Surveillance clôturée",
                description=f"La surveillance de **{self.scene_data['scene_name']}** a été fermée.",
                color=0x95a5a6,
                timestamp=datetime.now(PARIS_TZ)
            )
            embed.set_footer(text=f"Clôturée par {interaction.user.display_name}")
            
            await interaction.response.edit_message(embed=embed, view=self)
            
        except Exception as e:
            logging.error(f"Erreur lors de la clôture de scène: {e}")
            await interaction.response.send_message("❌ Erreur lors de la clôture de la scène.", ephemeral=True)

class SurveillanceScene(commands.Cog):
    """Cog pour la surveillance des scènes RP."""
    
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = PARIS_TZ
        
        # Configuration Google Sheets
        self.setup_google_sheets()
        
        # Cache des scènes surveillées
        self.monitored_scenes: Dict[str, dict] = {}
        
        # Démarrer les tâches
        self.update_surveillance.start()
        self.check_inactive_scenes.start()
        
    def setup_google_sheets(self):
        """Configure la connexion Google Sheets."""
        try:
            credentials = Credentials.from_service_account_info(
                json.loads(os.getenv('SERVICE_ACCOUNT_JSON')),
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.gc = gspread.authorize(credentials)
            self.spreadsheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_VALIDATION'))
            
            # Créer ou récupérer la feuille "Scene surveillance"
            try:
                self.sheet = self.spreadsheet.worksheet("Scene surveillance")
            except gspread.exceptions.WorksheetNotFound:
                self.sheet = self.spreadsheet.add_worksheet(
                    title="Scene surveillance", rows="1000", cols="10"
                )
                # Initialiser l'en-tête
                self.sheet.append_row([
                    "channel_id", "scene_name", "gm_id", "start_date",
                    "participants", "last_activity_user", "last_activity_date",
                    "message_id", "channel_type", "guild_id"
                ])
                logging.info("En-tête créé pour la feuille Scene surveillance")
                
        except Exception as e:
            logging.error(f"Erreur lors de la configuration Google Sheets: {e}")
            self.sheet = None
    
    def cog_unload(self):
        """Nettoie les tâches lors du déchargement du cog."""
        self.update_surveillance.cancel()
        self.check_inactive_scenes.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Événement déclenché quand le bot est prêt."""
        logging.info("SurveillanceScene: Bot prêt, démarrage de la mise à jour...")
        await asyncio.sleep(15)  # Attendre que tout soit initialisé
        try:
            await self.refresh_monitored_scenes()
            await self.update_all_scenes()
            logging.info("SurveillanceScene: Mise à jour initiale terminée")
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour initiale: {e}")
    
    @tasks.loop(hours=1)
    async def update_surveillance(self):
        """Met à jour la surveillance toutes les heures."""
        if not self.sheet:
            return
            
        try:
            await self.refresh_monitored_scenes()
            await self.update_all_scenes()
        except Exception as e:
            logging.error(f"Erreur dans update_surveillance: {e}")
    
    @update_surveillance.before_loop
    async def before_update_surveillance(self):
        """Attend que le bot soit prêt avant de démarrer la tâche."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)  # Attendre un peu plus pour s'assurer que tout est initialisé
        await self.refresh_monitored_scenes()
        # Forcer une mise à jour complète au démarrage
        logging.info("Mise à jour complète des scènes au démarrage du bot")
        await self.update_all_scenes()
    
    @tasks.loop(hours=24)
    async def check_inactive_scenes(self):
        """Vérifie les scènes inactives depuis 7 jours."""
        if not self.sheet:
            return
            
        try:
            now = datetime.now(self.paris_tz)
            seven_days_ago = now - timedelta(days=7)
            
            for scene_data in self.monitored_scenes.values():
                last_activity = datetime.fromisoformat(scene_data.get('last_activity_date', now.isoformat()))
                if last_activity.replace(tzinfo=self.paris_tz) < seven_days_ago:
                    await self.notify_inactive_scene(scene_data)
                    
        except Exception as e:
            logging.error(f"Erreur dans check_inactive_scenes: {e}")
    
    @check_inactive_scenes.before_loop
    async def before_check_inactive_scenes(self):
        """Attend que le bot soit prêt."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)

    async def refresh_monitored_scenes(self):
        """Recharge les scènes surveillées depuis Google Sheets."""
        if not self.sheet:
            logging.error("Aucune feuille Google Sheets configurée")
            return

        try:
            records = self.sheet.get_all_records()
            logging.info(f"Récupération de {len(records)} enregistrements depuis Google Sheets")
            self.monitored_scenes.clear()

            for i, record in enumerate(records):
                channel_id = record.get('channel_id')
                logging.info(f"Enregistrement {i+1}: channel_id='{channel_id}', scene_name='{record.get('scene_name', 'N/A')}'")

                if channel_id and str(channel_id).strip():  # Vérifier que channel_id n'est pas vide
                    self.monitored_scenes[str(channel_id)] = record
                    logging.info(f"Scène ajoutée: {channel_id} - {record.get('scene_name', 'N/A')}")
                else:
                    logging.warning(f"Enregistrement {i+1} ignoré: channel_id vide ou invalide")

            logging.info(f"Total des scènes chargées: {len(self.monitored_scenes)}")

        except Exception as e:
            logging.error(f"Erreur lors du rechargement des scènes: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

    async def get_channel_from_link(self, channel_link: str) -> Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]]:
        """Récupère un canal à partir d'un lien Discord."""
        try:
            # Extraire l'ID du canal depuis le lien (support discord.com et discordapp.com)
            match = re.search(r'(?:discord(?:app)?\.com)/channels/(\d+)/(\d+)(?:/(\d+))?', channel_link)
            if not match:
                logging.error(f"Format de lien non reconnu: {channel_link}")
                return None

            logging.info(f"Lien analysé - Guild: {match.group(1)}, Channel: {match.group(2)}, Thread/Post: {match.group(3) or 'None'}")

            guild_id = int(match.group(1))
            channel_id = int(match.group(2))
            thread_id = int(match.group(3)) if match.group(3) else None

            guild = self.bot.get_guild(guild_id)
            if not guild:
                logging.error(f"Guild {guild_id} non trouvée")
                logging.info(f"Guildes disponibles: {[g.id for g in self.bot.guilds]}")
                return None

            logging.info(f"Guild trouvée: {guild.name} (ID: {guild.id})")

            # Si c'est un thread ou un post de forum (3ème ID présent)
            if thread_id:
                # D'abord essayer de récupérer directement le thread/post
                try:
                    thread = await self.bot.fetch_channel(thread_id)
                    if thread:
                        logging.info(f"Thread/Post trouvé directement: {thread.name} (ID: {thread.id})")
                        return thread
                except discord.NotFound:
                    logging.error(f"Thread/Post {thread_id} non trouvé via fetch_channel")
                except discord.Forbidden:
                    logging.error(f"Pas d'autorisation pour accéder au thread/post {thread_id}")
                except Exception as e:
                    logging.error(f"Erreur lors de la récupération du thread/post {thread_id}: {e}")

                # Essayer via le canal parent
                channel = guild.get_channel(channel_id)
                if channel:
                    logging.info(f"Canal parent trouvé: {channel.name} (Type: {type(channel).__name__})")

                    # Pour les forums, essayer de récupérer le post
                    if isinstance(channel, discord.ForumChannel):
                        try:
                            # Récupérer tous les threads du forum
                            async for thread in channel.archived_threads(limit=None):
                                if thread.id == thread_id:
                                    logging.info(f"Post de forum trouvé dans les archives: {thread.name}")
                                    return thread

                            # Vérifier les threads actifs
                            for thread in channel.threads:
                                if thread.id == thread_id:
                                    logging.info(f"Post de forum trouvé dans les actifs: {thread.name}")
                                    return thread

                        except Exception as e:
                            logging.error(f"Erreur lors de la recherche dans le forum: {e}")

                    # Pour les canaux texte, essayer de récupérer le thread
                    elif isinstance(channel, discord.TextChannel):
                        try:
                            # Vérifier les threads actifs
                            for thread in channel.threads:
                                if thread.id == thread_id:
                                    logging.info(f"Thread trouvé dans les actifs: {thread.name}")
                                    return thread

                            # Vérifier les threads archivés
                            async for thread in channel.archived_threads(limit=None):
                                if thread.id == thread_id:
                                    logging.info(f"Thread trouvé dans les archives: {thread.name}")
                                    return thread

                        except Exception as e:
                            logging.error(f"Erreur lors de la recherche de thread: {e}")

                logging.error(f"Impossible de trouver le thread/post {thread_id}")
                return None

            # Sinon, récupérer le canal principal
            channel = guild.get_channel(channel_id)
            if channel:
                logging.info(f"Canal principal trouvé: {channel.name} (Type: {type(channel).__name__})")
                return channel
            else:
                logging.error(f"Canal {channel_id} non trouvé dans la guild {guild_id}")
                logging.info(f"Canaux disponibles dans la guild: {[(c.id, c.name, type(c).__name__) for c in guild.channels[:10]]}")

                # Essayer de récupérer via l'API Discord
                try:
                    logging.info(f"Tentative de récupération via fetch_channel pour {channel_id}")
                    fetched_channel = await self.bot.fetch_channel(channel_id)
                    if fetched_channel:
                        logging.info(f"Canal récupéré via API: {fetched_channel.name} (Type: {type(fetched_channel).__name__})")
                        return fetched_channel
                except discord.NotFound:
                    logging.error(f"Canal {channel_id} n'existe pas ou n'est pas accessible")
                except discord.Forbidden:
                    logging.error(f"Pas d'autorisation pour accéder au canal {channel_id}")
                except Exception as e:
                    logging.error(f"Erreur lors de fetch_channel: {e}")

                return None

        except Exception as e:
            logging.error(f"Erreur lors de la récupération du canal: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return None

    def parse_date(self, date_str: str) -> datetime:
        """Parse une date au format JJ/MM/AA."""
        try:
            # Parser la date et la mettre au début de la journée (00:00:00)
            parsed_date = datetime.strptime(date_str, "%d/%m/%y").replace(hour=0, minute=0, second=0, microsecond=0)
            # Ajouter la timezone Paris
            return self.paris_tz.localize(parsed_date)
        except ValueError:
            # Si le format est incorrect, utiliser la date d'aujourd'hui au début de la journée
            today = datetime.now(self.paris_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            return today

    async def get_webhook_username(self, message: discord.Message) -> Optional[str]:
        """Récupère le nom d'utilisateur d'un webhook (pour Tupperbox)."""
        try:
            if message.webhook_id:
                # Pour Tupperbox, le nom du personnage est généralement dans le nom d'affichage
                return message.author.display_name
        except:
            pass
        return None

    def get_user_display_name(self, message: discord.Message) -> str:
        """Récupère le nom d'affichage d'un utilisateur (avec gestion des webhooks)."""
        if message.author.bot and message.webhook_id:
            # C'est un webhook (Tupperbox), utiliser le nom du personnage
            # Le nom du personnage est dans message.author.name pour Tupperbox
            return message.author.name if message.author.name else message.author.display_name
        else:
            # Utilisateur normal
            return message.author.display_name

    async def get_channel_participants(self, channel: Union[discord.TextChannel, discord.Thread], start_date: datetime) -> List[str]:
        """Récupère la liste des participants depuis une date donnée."""
        participants = set()

        try:
            # Vérifier si le canal existe et est accessible
            if not channel:
                logging.error("Canal non fourni pour get_channel_participants")
                return []

            logging.info(f"Récupération des participants pour {channel.name} (Type: {type(channel).__name__}) depuis {start_date}")
            logging.info(f"Date de surveillance (timezone): {start_date} - Timezone: {start_date.tzinfo}")

            # Tester d'abord sans filtre de date pour voir s'il y a des messages
            total_messages = 0
            async for message in channel.history(limit=10):
                total_messages += 1
                if total_messages <= 3:
                    logging.info(f"Message récent {total_messages}: '{self.get_user_display_name(message)}' le {message.created_at} (après {start_date}? {message.created_at > start_date})")

            logging.info(f"Total des messages récents dans le canal: {total_messages}")

            # Maintenant récupérer avec le filtre de date
            message_count = 0
            async for message in channel.history(limit=None, after=start_date):
                message_count += 1
                # Utiliser la nouvelle fonction pour obtenir le nom d'affichage
                user_name = self.get_user_display_name(message)

                # Ignorer le webhook "Maître du Jeu"
                if user_name != "Maître du Jeu":
                    participants.add(user_name)

                # Log détaillé pour debug
                if message_count <= 10:  # Log les 10 premiers pour mieux diagnostiquer
                    logging.info(f"Message {message_count}: '{user_name}' le {message.created_at} - Bot: {message.author.bot}, Webhook: {message.webhook_id is not None}, Author.name: '{message.author.name}', Author.display_name: '{message.author.display_name}'")

            # Convertir en liste triée et dédoublonnée (le set garantit déjà l'unicité)
            participants_list = sorted(list(participants))  # Trier pour plus de lisibilité
            logging.info(f"Analysé {message_count} messages depuis {start_date}, trouvé {len(participants_list)} participants: {participants_list}")

        except discord.Forbidden:
            logging.error(f"Pas d'autorisation pour lire l'historique de {channel.name}")
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des participants: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

        return list(participants)

    async def get_last_activity(self, channel: Union[discord.TextChannel, discord.Thread]) -> Optional[dict]:
        """Récupère la dernière activité dans un canal."""
        try:
            if not channel:
                logging.error("Canal non fourni pour get_last_activity")
                return None

            logging.info(f"Récupération de la dernière activité pour {channel.name}")

            async for message in channel.history(limit=1):
                # Utiliser la nouvelle fonction pour obtenir le nom d'affichage
                user_name = self.get_user_display_name(message)

                activity = {
                    'user': user_name,
                    'date': message.created_at.astimezone(self.paris_tz),
                    'message_id': message.id
                }

                logging.info(f"Dernière activité trouvée: {user_name} le {activity['date']}")
                return activity

        except discord.Forbidden:
            logging.error(f"Pas d'autorisation pour lire l'historique de {channel.name}")
        except Exception as e:
            logging.error(f"Erreur lors de la récupération de la dernière activité: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

        return None

    async def create_surveillance_embed(self, scene_data: dict) -> discord.Embed:
        """Crée l'embed de surveillance d'une scène."""
        try:
            embed = discord.Embed(
                title="🎭 Surveillance de Scène",
                color=0x3498db,
                timestamp=datetime.now(self.paris_tz)
            )

            # Nom de la scène
            embed.add_field(
                name="📍 Scène",
                value=scene_data.get('scene_name', 'Nom inconnu'),
                inline=True
            )

            # MJ responsable
            gm_id = scene_data.get('gm_id')
            gm_mention = f"<@{gm_id}>" if gm_id else "Aucun"
            embed.add_field(
                name="🎯 MJ Responsable",
                value=gm_mention,
                inline=True
            )

            # Date de début
            start_date = scene_data.get('start_date', '')
            if start_date:
                try:
                    date_obj = datetime.fromisoformat(start_date)
                    formatted_date = date_obj.strftime("%d/%m/%Y")
                except:
                    formatted_date = start_date
            else:
                formatted_date = "Date inconnue"

            embed.add_field(
                name="📅 Début de surveillance",
                value=formatted_date,
                inline=True
            )

            # Participants
            participants = scene_data.get('participants', '[]')
            if isinstance(participants, str):
                try:
                    participants = json.loads(participants)
                except:
                    participants = []

            if participants:
                participants_text = "\n".join([f"• {p}" for p in participants])  # Afficher tous les participants
            else:
                participants_text = "Aucun participant"

            embed.add_field(
                name=f"🎭 Personnages ({len(participants)})",
                value=participants_text,
                inline=False
            )

            # Dernière activité
            last_activity_user = scene_data.get('last_activity_user', 'Aucune activité')
            last_activity_date = scene_data.get('last_activity_date', '')

            if last_activity_date:
                try:
                    activity_date = datetime.fromisoformat(last_activity_date)
                    now = datetime.now(self.paris_tz)
                    time_diff = now - activity_date.replace(tzinfo=self.paris_tz)

                    if time_diff.days > 0:
                        time_ago = f"il y a {time_diff.days} jour(s)"
                    elif time_diff.seconds > 3600:
                        hours = time_diff.seconds // 3600
                        time_ago = f"il y a {hours} heure(s)"
                    else:
                        minutes = time_diff.seconds // 60
                        time_ago = f"il y a {minutes} minute(s)"

                    activity_text = f"{last_activity_user}\n{activity_date.strftime('%d/%m/%Y à %H:%M')} ({time_ago})"
                except:
                    activity_text = f"{last_activity_user}\n{last_activity_date}"
            else:
                activity_text = "Aucune activité détectée"

            embed.add_field(
                name="⏰ Dernière Activité",
                value=activity_text,
                inline=False
            )

            embed.set_footer(text="Mise à jour automatique toutes les heures")

            return embed

        except Exception as e:
            logging.error(f"Erreur lors de la création de l'embed: {e}")
            return discord.Embed(title="❌ Erreur", description="Impossible de créer l'embed de surveillance.")

    @commands.command(name='scene')
    async def scene_command(self, ctx, channel_link: str = None, date: str = None, gm_id: str = None):
        """
        Commande pour initier la surveillance d'une scène.
        Usage: !scene [Lien du salon] [Date JJ/MM/AA] [ID du MJ]
        """
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        if not channel_link:
            await ctx.send("❌ Veuillez fournir un lien vers le salon à surveiller.")
            return

        try:
            logging.info(f"Tentative de surveillance pour le lien: {channel_link}")

            # Récupérer le canal
            channel = await self.get_channel_from_link(channel_link)
            if not channel:
                logging.error(f"Canal non trouvé pour le lien: {channel_link}")

                # Analyser le lien pour donner plus d'infos
                match = re.search(r'(?:discord(?:app)?\.com)/channels/(\d+)/(\d+)(?:/(\d+))?', channel_link)
                if match:
                    guild_id = int(match.group(1))
                    channel_id = int(match.group(2))

                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        error_msg = f"❌ **Serveur non trouvé**\nLe bot n'a pas accès au serveur avec l'ID `{guild_id}`.\n\n**Vérifiez que :**\n• Le bot est bien présent sur ce serveur\n• L'ID du serveur est correct"
                    else:
                        error_msg = f"❌ **Canal non trouvé**\nLe canal avec l'ID `{channel_id}` n'existe pas ou n'est pas accessible sur le serveur **{guild.name}**.\n\n**Causes possibles :**\n• Le canal a été supprimé\n• Le bot n'a pas les permissions pour voir ce canal\n• L'ID du canal est incorrect"
                else:
                    error_msg = f"❌ **Format de lien invalide**\n**Lien fourni:** {channel_link}\n\n**Formats supportés:**\n• Salon: `https://discord.com/channels/GUILD_ID/CHANNEL_ID`\n• Thread: `https://discord.com/channels/GUILD_ID/CHANNEL_ID/THREAD_ID`\n• Post de forum: `https://discord.com/channels/GUILD_ID/FORUM_ID/POST_ID`\n• Également supporté: `discordapp.com` au lieu de `discord.com`"

                await ctx.send(error_msg)
                return

            logging.info(f"Canal trouvé: {channel.name} (ID: {channel.id}, Type: {type(channel).__name__})")

            # Parser la date
            if date:
                start_date = self.parse_date(date)
            else:
                start_date = datetime.now(self.paris_tz)

            # Déterminer le MJ
            if gm_id:
                try:
                    gm_id = str(int(gm_id.strip('<@!>')))  # Nettoyer les mentions
                except ValueError:
                    await ctx.send("❌ ID du MJ invalide.")
                    return
            else:
                gm_id = str(ctx.author.id)

            # Vérifier si la scène est déjà surveillée
            if str(channel.id) in self.monitored_scenes:
                await ctx.send("❌ Cette scène est déjà sous surveillance.")
                return

            # Récupérer les participants et la dernière activité
            participants = await self.get_channel_participants(channel, start_date)
            last_activity = await self.get_last_activity(channel)

            # Déterminer le type de canal
            if isinstance(channel, discord.Thread):
                channel_type = "Thread"
            elif isinstance(channel, discord.ForumChannel):
                channel_type = "Forum"
            else:
                channel_type = "TextChannel"

            # Créer les données de la scène
            scene_data = {
                'channel_id': str(channel.id),
                'scene_name': channel.name,
                'gm_id': gm_id,
                'start_date': start_date.isoformat(),
                'participants': json.dumps(participants),
                'last_activity_user': last_activity['user'] if last_activity else 'Aucune activité',
                'last_activity_date': last_activity['date'].isoformat() if last_activity else '',
                'message_id': '',  # Sera mis à jour après l'envoi
                'channel_type': channel_type,
                'guild_id': str(channel.guild.id)
            }

            # Ajouter à Google Sheets
            self.sheet.append_row([
                scene_data['channel_id'],
                scene_data['scene_name'],
                scene_data['gm_id'],
                scene_data['start_date'],
                scene_data['participants'],
                scene_data['last_activity_user'],
                scene_data['last_activity_date'],
                scene_data['message_id'],
                scene_data['channel_type'],
                scene_data['guild_id']
            ])

            # Ajouter au cache local
            self.monitored_scenes[str(channel.id)] = scene_data

            # Envoyer le message de surveillance
            surveillance_channel = self.bot.get_channel(SURVEILLANCE_CHANNEL_ID)
            if surveillance_channel:
                embed = await self.create_surveillance_embed(scene_data)
                view = SceneSurveillanceView(self, scene_data)

                message = await surveillance_channel.send(embed=embed, view=view)

                # Mettre à jour l'ID du message dans Google Sheets
                scene_data['message_id'] = str(message.id)
                await self.update_scene_message_id(str(channel.id), str(message.id))

            await ctx.send(f"✅ Surveillance initiée pour **{channel.name}**.")

            # Notifier le MJ
            gm = self.bot.get_user(int(gm_id))
            if gm and gm.id != ctx.author.id:
                try:
                    await gm.send(f"🎭 **Nouvelle surveillance de scène**\nVous avez été désigné comme MJ pour la scène **{channel.name}**.")
                except:
                    pass

        except Exception as e:
            logging.error(f"Erreur dans la commande scene: {e}")
            await ctx.send("❌ Une erreur est survenue lors de l'initialisation de la surveillance.")

    @commands.command(name='update_scenes')
    @commands.has_permissions(administrator=True)
    async def update_scenes_command(self, ctx):
        """
        Commande pour forcer la mise à jour de toutes les scènes surveillées.
        Usage: !update_scenes
        """
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            await ctx.send("🔄 Mise à jour de toutes les scènes en cours...")

            # Recharger les scènes depuis Google Sheets
            await self.refresh_monitored_scenes()

            # Mettre à jour toutes les scènes
            await self.update_all_scenes()

            await ctx.send(f"✅ Mise à jour terminée ! {len(self.monitored_scenes)} scène(s) mise(s) à jour.")

        except Exception as e:
            logging.error(f"Erreur dans la commande update_scenes: {e}")
            await ctx.send("❌ Une erreur est survenue lors de la mise à jour des scènes.")

    @commands.command(name='debug_scenes')
    @commands.has_permissions(administrator=True)
    async def debug_scenes_command(self, ctx):
        """
        Commande pour déboguer les scènes surveillées.
        Usage: !debug_scenes
        """
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            # Récupérer les données brutes
            all_values = self.sheet.get_all_values()
            records = self.sheet.get_all_records()

            embed = discord.Embed(
                title="🔍 Debug des scènes surveillées",
                color=0xe74c3c
            )

            embed.add_field(
                name="📊 Statistiques",
                value=f"• Lignes totales: {len(all_values)}\n• Enregistrements: {len(records)}\n• Scènes en cache: {len(self.monitored_scenes)}",
                inline=False
            )

            if len(all_values) > 0:
                embed.add_field(
                    name="📋 En-têtes",
                    value=f"```{', '.join(all_values[0])}```",
                    inline=False
                )

            if len(records) > 0:
                scenes_info = []
                for i, record in enumerate(records[:3]):  # Limiter à 3 pour éviter les messages trop longs
                    channel_id = record.get('channel_id', 'N/A')
                    scene_name = record.get('scene_name', 'N/A')
                    scenes_info.append(f"{i+1}. ID: {channel_id} | Nom: {scene_name}")

                embed.add_field(
                    name="🎭 Premières scènes",
                    value="```" + "\n".join(scenes_info) + "```",
                    inline=False
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Erreur dans la commande debug_scenes: {e}")
            await ctx.send(f"❌ Erreur lors du debug: {e}")

    @commands.command(name='list_sheet_data')
    @commands.has_permissions(administrator=True)
    async def list_sheet_data_command(self, ctx):
        """
        Commande pour voir toutes les données brutes du Google Sheet.
        Usage: !list_sheet_data
        """
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            # Récupérer toutes les valeurs brutes
            all_values = self.sheet.get_all_values()

            embed = discord.Embed(
                title="📋 Données brutes du Google Sheet",
                color=0x3498db
            )

            if len(all_values) == 0:
                embed.add_field(name="❌ Aucune donnée", value="Le Google Sheet est complètement vide", inline=False)
            elif len(all_values) == 1:
                embed.add_field(name="📋 En-tête seulement", value=f"```{', '.join(all_values[0])}```", inline=False)
                embed.add_field(name="ℹ️ Info", value="Il n'y a que l'en-tête, aucune scène surveillée", inline=False)
            else:
                # Afficher l'en-tête
                embed.add_field(name="📋 En-tête", value=f"```{', '.join(all_values[0])}```", inline=False)

                # Afficher les données (limiter à 5 lignes pour éviter les messages trop longs)
                data_lines = []
                for i, row in enumerate(all_values[1:6]):  # Lignes 2 à 6 max
                    if any(cell.strip() for cell in row):  # Ignorer les lignes complètement vides
                        data_lines.append(f"Ligne {i+2}: {', '.join(row)}")

                if data_lines:
                    embed.add_field(
                        name="📊 Données (5 premières lignes)",
                        value="```" + "\n".join(data_lines) + "```",
                        inline=False
                    )
                else:
                    embed.add_field(name="❌ Aucune donnée", value="Toutes les lignes de données sont vides", inline=False)

                if len(all_values) > 6:
                    embed.add_field(name="ℹ️ Info", value=f"... et {len(all_values) - 6} autres lignes", inline=False)

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Erreur dans la commande list_sheet_data: {e}")
            await ctx.send(f"❌ Erreur lors de la récupération des données: {e}")

    @commands.command(name='fix_sheet_header')
    @commands.has_permissions(administrator=True)
    async def fix_sheet_header_command(self, ctx):
        """
        Commande pour réparer l'en-tête du Google Sheet.
        Usage: !fix_sheet_header
        """
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            # Vérifier l'état actuel
            all_values = self.sheet.get_all_values()

            if len(all_values) == 0:
                await ctx.send("❌ Le Google Sheet est complètement vide.")
                return

            # Vérifier si l'en-tête existe déjà
            expected_header = ["channel_id", "scene_name", "gm_id", "start_date", "participants", "last_activity_user", "last_activity_date", "message_id", "channel_type", "guild_id"]

            if len(all_values) > 0 and all_values[0] == expected_header:
                await ctx.send("✅ L'en-tête est déjà correct.")
                return

            # Insérer l'en-tête en première ligne
            self.sheet.insert_row(expected_header, 1)

            await ctx.send("✅ En-tête ajouté avec succès ! Vous pouvez maintenant utiliser `!update_scenes`.")

            # Optionnel : recharger automatiquement les scènes
            await self.refresh_monitored_scenes()
            await ctx.send(f"🔄 Scènes rechargées : {len(self.monitored_scenes)} scène(s) trouvée(s).")

        except Exception as e:
            logging.error(f"Erreur dans la commande fix_sheet_header: {e}")
            await ctx.send(f"❌ Erreur lors de la réparation de l'en-tête: {e}")

    async def update_scene_message_id(self, channel_id: str, message_id: str):
        """Met à jour l'ID du message de surveillance dans Google Sheets."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):  # Start=2 car ligne 1 = en-tête
                if record.get('channel_id') == channel_id:
                    self.sheet.update(f'H{i}', message_id)  # Colonne H = message_id
                    break
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de l'ID du message: {e}")

    async def update_scene_gm(self, channel_id: str, new_gm_id: str):
        """Met à jour le MJ d'une scène dans Google Sheets."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                if record.get('channel_id') == channel_id:
                    self.sheet.update(f'C{i}', new_gm_id)  # Colonne C = gm_id
                    break
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour du MJ: {e}")

    async def remove_scene_surveillance(self, channel_id: str):
        """Supprime une scène de la surveillance."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                if record.get('channel_id') == channel_id:
                    self.sheet.delete_rows(i)
                    break

            # Supprimer du cache local
            if channel_id in self.monitored_scenes:
                del self.monitored_scenes[channel_id]

        except Exception as e:
            logging.error(f"Erreur lors de la suppression de la surveillance: {e}")

    async def update_scene_data(self, channel_id: str, scene_data: dict):
        """Met à jour les données d'une scène dans Google Sheets."""
        try:
            logging.info(f"Mise à jour des données pour le canal {channel_id}")

            # Décoder les participants pour logging
            participants_data = scene_data.get('participants', '[]')
            if isinstance(participants_data, str):
                try:
                    participants_list = json.loads(participants_data)
                    logging.info(f"Participants à sauvegarder: {participants_list}")
                except:
                    logging.error(f"Erreur lors du décodage des participants: {participants_data}")

            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                if record.get('channel_id') == channel_id:
                    # Mettre à jour toute la ligne
                    self.sheet.update(f'A{i}:J{i}', [[
                        scene_data['channel_id'],
                        scene_data['scene_name'],
                        scene_data['gm_id'],
                        scene_data['start_date'],
                        scene_data['participants'],
                        scene_data['last_activity_user'],
                        scene_data['last_activity_date'],
                        scene_data['message_id'],
                        scene_data['channel_type'],
                        scene_data['guild_id']
                    ]])
                    logging.info(f"Données mises à jour dans Google Sheets ligne {i}")
                    break
            else:
                logging.error(f"Canal {channel_id} non trouvé dans Google Sheets pour mise à jour")

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour des données: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

    async def update_all_scenes(self):
        """Met à jour toutes les scènes surveillées."""
        logging.info(f"Mise à jour de {len(self.monitored_scenes)} scènes surveillées")

        for channel_id, scene_data in self.monitored_scenes.items():
            try:
                logging.info(f"Mise à jour de la scène {channel_id} ({scene_data.get('scene_name', 'Nom inconnu')})")

                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    # Essayer de récupérer via l'API
                    try:
                        channel = await self.bot.fetch_channel(int(channel_id))
                    except:
                        logging.error(f"Impossible de récupérer le canal {channel_id}")
                        continue

                # Récupérer les nouvelles données
                start_date = datetime.fromisoformat(scene_data['start_date'])
                # S'assurer que la date a une timezone
                if start_date.tzinfo is None:
                    start_date = self.paris_tz.localize(start_date)

                logging.info(f"Récupération des participants depuis {start_date} (timezone: {start_date.tzinfo})")

                participants = await self.get_channel_participants(channel, start_date)
                last_activity = await self.get_last_activity(channel)

                # Mettre à jour les données locales
                old_participants = scene_data.get('participants', '[]')
                scene_data['participants'] = json.dumps(participants)

                if last_activity:
                    scene_data['last_activity_user'] = last_activity['user']
                    scene_data['last_activity_date'] = last_activity['date'].isoformat()

                logging.info(f"Participants mis à jour: {len(participants)} trouvés")

                # Mettre à jour Google Sheets
                await self.update_scene_data(channel_id, scene_data)

                # Mettre à jour le message de surveillance
                await self.update_surveillance_message(scene_data)

            except Exception as e:
                logging.error(f"Erreur lors de la mise à jour de la scène {channel_id}: {e}")
                import traceback
                logging.error(f"Traceback: {traceback.format_exc()}")

        logging.info("Mise à jour de toutes les scènes terminée")

    async def update_surveillance_message(self, scene_data: dict):
        """Met à jour le message de surveillance dans le canal dédié."""
        try:
            surveillance_channel = self.bot.get_channel(SURVEILLANCE_CHANNEL_ID)
            if not surveillance_channel:
                return

            message_id = scene_data.get('message_id')
            if not message_id:
                return

            try:
                message = await surveillance_channel.fetch_message(int(message_id))
                embed = await self.create_surveillance_embed(scene_data)
                view = SceneSurveillanceView(self, scene_data)
                await message.edit(embed=embed, view=view)
            except discord.NotFound:
                # Le message a été supprimé, en créer un nouveau
                embed = await self.create_surveillance_embed(scene_data)
                view = SceneSurveillanceView(self, scene_data)
                new_message = await surveillance_channel.send(embed=embed, view=view)
                scene_data['message_id'] = str(new_message.id)
                await self.update_scene_message_id(scene_data['channel_id'], str(new_message.id))

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour du message de surveillance: {e}")

    async def notify_inactive_scene(self, scene_data: dict):
        """Notifie le MJ d'une scène inactive depuis 7 jours."""
        try:
            gm = self.bot.get_user(int(scene_data['gm_id']))
            if gm:
                embed = discord.Embed(
                    title="⚠️ Scène Inactive",
                    description=f"La scène **{scene_data['scene_name']}** n'a pas eu d'activité depuis 7 jours.",
                    color=0xf39c12,
                    timestamp=datetime.now(self.paris_tz)
                )

                last_activity_date = scene_data.get('last_activity_date', '')
                if last_activity_date:
                    try:
                        activity_date = datetime.fromisoformat(last_activity_date)
                        embed.add_field(
                            name="Dernière activité",
                            value=f"{activity_date.strftime('%d/%m/%Y à %H:%M')}",
                            inline=False
                        )
                    except:
                        pass

                await gm.send(embed=embed)

        except Exception as e:
            logging.error(f"Erreur lors de la notification d'inactivité: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Écoute les nouveaux messages dans les canaux surveillés."""
        if message.author == self.bot.user:
            return

        channel_id = str(message.channel.id)
        if channel_id not in self.monitored_scenes:
            return

        try:
            scene_data = self.monitored_scenes[channel_id]

            # Mettre à jour la dernière activité
            user_name = self.get_user_display_name(message)

            scene_data['last_activity_user'] = user_name
            scene_data['last_activity_date'] = message.created_at.astimezone(self.paris_tz).isoformat()

            # Mettre à jour les participants
            start_date = datetime.fromisoformat(scene_data['start_date'])
            participants = await self.get_channel_participants(message.channel, start_date)
            scene_data['participants'] = json.dumps(participants)

            # Mettre à jour Google Sheets
            await self.update_scene_data(channel_id, scene_data)

            # Mettre à jour le message de surveillance
            await self.update_surveillance_message(scene_data)

            # Notifier le MJ
            gm = self.bot.get_user(int(scene_data['gm_id']))
            if gm and gm.id != message.author.id:
                try:
                    embed = discord.Embed(
                        title="📝 Nouvelle activité",
                        description=f"Nouveau message dans **{scene_data['scene_name']}**",
                        color=0x2ecc71
                    )
                    embed.add_field(name="Auteur", value=user_name, inline=True)
                    embed.add_field(name="Canal", value=message.channel.mention, inline=True)
                    embed.add_field(name="Aperçu", value=message.content[:100] + "..." if len(message.content) > 100 else message.content, inline=False)

                    await gm.send(embed=embed)
                except:
                    pass

        except Exception as e:
            logging.error(f"Erreur lors du traitement du message: {e}")

async def setup(bot):
    await bot.add_cog(SurveillanceScene(bot))
