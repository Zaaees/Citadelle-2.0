"""
Cog de surveillance des salons Discord.
Permet aux MJ de surveiller des salons et d'être notifiés quand des messages y sont envoyés.
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import logging
from datetime import datetime
from typing import Dict, Set, List
import gspread
from google.oauth2.service_account import Credentials
import asyncio
from discord.ext import tasks

# Configuration
NOTIFICATION_CHANNEL_ID = 1380704586016362626  # Salon de notification
MJ_ROLE_ID = 1018179623886000278  # ID du rôle MJ

class SceneCloseButton(discord.ui.Button):
    """Bouton pour clôturer une scène."""

    def __init__(self, cog, channel_id: int):
        super().__init__(
            label="Clôturer la scène",
            style=discord.ButtonStyle.danger,
            custom_id=f"close_scene_{channel_id}"
        )
        self.cog = cog
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        # Vérifier les permissions MJ
        if not self.cog.is_mj(interaction.user):
            await interaction.response.send_message(
                "❌ Seuls les MJ peuvent clôturer une scène.",
                ephemeral=True
            )
            return

        # Retirer le salon de la surveillance
        if self.channel_id in self.cog.monitored_channels:
            del self.cog.monitored_channels[self.channel_id]
            self.cog.save_monitored_channels()

            # Récupérer les informations du salon
            channel = self.cog.bot.get_channel(self.channel_id)
            channel_info = self.cog.get_channel_info(channel) if channel else f"Salon ID {self.channel_id}"

            # Envoyer un message public de clôture
            try:
                closure_message = await interaction.response.send_message(
                    f"🔒 **Scène clôturée** - {channel_info} n'est plus surveillé (par {interaction.user.display_name})",
                    ephemeral=False
                )

                # Ajouter le message de clôture à Google Sheets pour suppression automatique
                if self.cog.ping_sheet:
                    try:
                        # Récupérer le message envoyé
                        sent_message = await interaction.original_response()
                        self.cog.ping_sheet.append_row([
                            str(sent_message.id),
                            str(interaction.channel_id),
                            datetime.now().isoformat()
                        ])
                    except Exception as e:
                        self.cog.logger.error(f"Erreur lors de l'ajout du message de clôture à Google Sheets: {e}")

                # Supprimer l'embed original
                try:
                    await interaction.message.delete()
                except discord.NotFound:
                    pass

            except discord.NotFound:
                await interaction.followup.send(
                    "✅ Scène clôturée.",
                    ephemeral=True
                )

            self.cog.logger.info(f"Scène {self.channel_id} clôturée et supprimée par {interaction.user.display_name}")
        else:
            await interaction.response.send_message(
                "❌ Cette scène n'est plus surveillée.",
                ephemeral=True
            )

class SceneView(discord.ui.View):
    """Vue avec le bouton de clôture de scène."""

    def __init__(self, cog, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(SceneCloseButton(cog, channel_id))

class ChannelMonitor(commands.Cog):
    """Cog pour surveiller les salons et notifier les MJ."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.monitored_channels: Dict[int, dict] = {}  # {channel_id: {mj_user_id, message_id, participants, last_activity}}
        self.logger = logging.getLogger('channel_monitor')
        self.gspread_client = None
        self.sheet = None
        self.ping_sheet = None
        # Initialisation asynchrone pour éviter les délais au démarrage
        self.bot.loop.create_task(self.async_init())
        self.cleanup_ping_messages.start()
        self.check_inactive_scenes.start()

    async def async_init(self):
        """Initialisation asynchrone du cog."""
        await self.bot.wait_until_ready()
        self.setup_google_sheets()
        self.load_monitored_channels()
        await self.setup_persistent_views()

    def setup_google_sheets(self):
        """Configure l'accès à Google Sheets."""
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = Credentials.from_service_account_info(
                json.loads(os.getenv('SERVICE_ACCOUNT_JSON')),
                scopes=scopes
            )
            self.gspread_client = gspread.authorize(creds)

            # Ouvrir le spreadsheet de validation
            spreadsheet = self.gspread_client.open_by_key(os.getenv('GOOGLE_SHEET_ID_VALIDATION'))

            # Essayer d'accéder à la feuille "Channel Monitor", la créer si elle n'existe pas
            try:
                self.sheet = spreadsheet.worksheet("Channel Monitor")
            except gspread.exceptions.WorksheetNotFound:
                self.sheet = spreadsheet.add_worksheet(
                    title="Channel Monitor",
                    rows="1000",
                    cols="10"
                )
                # Initialiser l'en-tête
                self.sheet.append_row(["channel_id", "mj_user_id", "message_id", "participant_1", "participant_2", "participant_3", "participant_4", "participant_5", "participant_6", "added_at", "last_activity"])

            # Feuille pour les messages de ping à supprimer
            try:
                self.ping_sheet = spreadsheet.worksheet("Ping Messages")
            except gspread.exceptions.WorksheetNotFound:
                self.ping_sheet = spreadsheet.add_worksheet(
                    title="Ping Messages",
                    rows="1000",
                    cols="3"
                )
                # Initialiser l'en-tête
                self.ping_sheet.append_row(["message_id", "channel_id", "timestamp"])

            self.logger.info("[CHANNEL_MONITOR] Connexion Google Sheets établie")
        except Exception as e:
            self.logger.error(f"[CHANNEL_MONITOR] Erreur lors de la configuration Google Sheets: {e}")
            self.gspread_client = None
            self.sheet = None
            self.ping_sheet = None

    def load_monitored_channels(self):
        """Charge la liste des salons surveillés depuis Google Sheets."""
        try:
            if not self.sheet:
                self.logger.warning("Google Sheets non configuré, impossible de charger les salons surveillés")
                self.monitored_channels = {}
                return

            # Récupérer toutes les données (en ignorant l'en-tête)
            all_values = self.sheet.get_all_values()
            if len(all_values) <= 1:  # Seulement l'en-tête ou vide
                self.monitored_channels = {}
                self.logger.info("Aucun salon surveillé trouvé dans Google Sheets")
                return

            # Charger les données (ignorer la première ligne qui est l'en-tête)
            self.monitored_channels = {}
            for row in all_values[1:]:
                if len(row) >= 2 and row[0] and row[1]:
                    try:
                        channel_id = int(row[0])
                        mj_user_id = int(row[1])
                        message_id = int(row[2]) if len(row) > 2 and row[2] else None

                        # Charger les participants depuis les colonnes 3-8 (participant_1 à participant_6)
                        participants = []
                        for i in range(3, 9):  # Colonnes 3 à 8
                            if len(row) > i and row[i]:
                                try:
                                    participants.append(int(row[i]))
                                except ValueError:
                                    pass

                        # Récupérer last_activity (colonne 10, index 10)
                        last_activity = None
                        if len(row) > 10 and row[10]:
                            try:
                                last_activity = datetime.fromisoformat(row[10])
                            except ValueError:
                                last_activity = datetime.now()  # Fallback pour les anciennes données
                        else:
                            last_activity = datetime.now()  # Fallback pour les anciennes données

                        self.monitored_channels[channel_id] = {
                            'mj_user_id': mj_user_id,
                            'message_id': message_id,
                            'participants': participants,
                            'last_activity': last_activity
                        }
                    except ValueError as e:
                        self.logger.warning(f"Ligne invalide ignorée: {row} - Erreur: {e}")

            self.logger.info(f"Chargé {len(self.monitored_channels)} salons surveillés depuis Google Sheets")
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement des salons surveillés: {e}")
            self.monitored_channels = {}

    def save_monitored_channels(self):
        """Sauvegarde la liste des salons surveillés dans Google Sheets."""
        try:
            if not self.sheet:
                self.logger.error("Google Sheets non configuré, impossible de sauvegarder")
                return

            # Effacer le contenu existant (garder l'en-tête)
            self.sheet.clear()

            # Réécrire l'en-tête
            self.sheet.append_row(["channel_id", "mj_user_id", "message_id", "participant_1", "participant_2", "participant_3", "participant_4", "participant_5", "participant_6", "added_at", "last_activity"])

            # Ajouter toutes les données
            current_time = datetime.now().isoformat()
            for channel_id, data in self.monitored_channels.items():
                # Préparer la ligne avec les participants dans des colonnes séparées
                row = [
                    str(channel_id),
                    str(data['mj_user_id']),
                    str(data['message_id']) if data['message_id'] else ""
                ]

                # Ajouter les participants (maximum 6)
                participants = data['participants'][:6]  # Limiter à 6 participants
                for i in range(6):
                    if i < len(participants):
                        row.append(str(participants[i]))
                    else:
                        row.append("")  # Colonne vide si pas de participant

                row.append(current_time)

                # Ajouter last_activity
                last_activity = data.get('last_activity', datetime.now())
                row.append(last_activity.isoformat())

                self.sheet.append_row(row)

            self.logger.info(f"Sauvegardé {len(self.monitored_channels)} salons surveillés dans Google Sheets")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des salons surveillés: {e}")

    @tasks.loop(hours=1)
    async def cleanup_ping_messages(self):
        """Nettoie les messages de ping anciens (plus de 24h)."""
        try:
            if not self.ping_sheet:
                return

            current_time = datetime.now()
            all_values = self.ping_sheet.get_all_values()

            if len(all_values) <= 1:  # Seulement l'en-tête ou vide
                return

            rows_to_delete = []

            # Parcourir toutes les lignes (ignorer l'en-tête)
            for idx, row in enumerate(all_values[1:], start=2):
                if len(row) >= 3 and row[0] and row[1] and row[2]:
                    try:
                        message_id = int(row[0])
                        channel_id = int(row[1])
                        timestamp = row[2]

                        # Vérifier si le message a plus de 24h
                        message_time = datetime.fromisoformat(timestamp)
                        if (current_time - message_time).total_seconds() > 86400:  # 24h en secondes
                            try:
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    message = await channel.fetch_message(message_id)
                                    await message.delete()
                                    self.logger.info(f"Message de ping supprimé: {message_id}")
                            except discord.NotFound:
                                # Message déjà supprimé
                                pass
                            except Exception as e:
                                self.logger.error(f"Erreur lors de la suppression du message de ping {message_id}: {e}")

                            rows_to_delete.append(idx)
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Ligne de ping invalide ignorée: {row} - Erreur: {e}")
                        rows_to_delete.append(idx)

            # Supprimer les lignes en commençant par la fin pour éviter les décalages d'index
            for row_idx in reversed(rows_to_delete):
                self.ping_sheet.delete_rows(row_idx)

            if rows_to_delete:
                self.logger.info(f"Supprimé {len(rows_to_delete)} messages de ping expirés")

        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage des messages de ping: {e}")

    @cleanup_ping_messages.before_loop
    async def before_cleanup_ping_messages(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def check_inactive_scenes(self):
        """Vérifie les scènes inactives depuis une semaine et ping le MJ."""
        try:
            if not self.monitored_channels:
                return

            current_time = datetime.now()
            week_ago = current_time.timestamp() - (7 * 24 * 60 * 60)  # 7 jours en secondes

            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                self.logger.error(f"Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé")
                return

            for channel_id, data in self.monitored_channels.items():
                try:
                    last_activity = data.get('last_activity')
                    if not last_activity:
                        continue

                    # Vérifier si la scène est inactive depuis une semaine
                    if last_activity.timestamp() < week_ago:
                        mj_id = data['mj_user_id']
                        mj = self.bot.get_user(mj_id)

                        if not mj:
                            self.logger.warning(f"MJ avec ID {mj_id} non trouvé pour le salon {channel_id}")
                            continue

                        # Récupérer les informations du salon
                        channel = self.bot.get_channel(channel_id)
                        if not channel:
                            self.logger.warning(f"Salon {channel_id} non trouvé")
                            continue

                        channel_info = self.get_channel_info(channel)

                        # Créer le message de rappel
                        days_inactive = int((current_time - last_activity).days)
                        ping_content = (
                            f"⏰ {mj.mention} **Rappel de scène inactive**\n"
                            f"La scène {channel_info} n'a pas eu d'activité depuis **{days_inactive} jours**.\n"
                            f"Pensez à vérifier si elle nécessite votre attention !"
                        )

                        # Envoyer le message de rappel
                        if data['message_id']:
                            try:
                                embed_message = await notification_channel.fetch_message(data['message_id'])
                                ping_message = await embed_message.reply(ping_content)

                                # Ajouter le message de ping à Google Sheets pour suppression automatique
                                if self.ping_sheet:
                                    try:
                                        self.ping_sheet.append_row([
                                            str(ping_message.id),
                                            str(notification_channel.id),
                                            datetime.now().isoformat()
                                        ])
                                    except Exception as e:
                                        self.logger.error(f"Erreur lors de l'ajout du ping de rappel à Google Sheets: {e}")

                                self.logger.info(f"Ping de rappel envoyé pour scène inactive: {channel_info} ({days_inactive} jours)")

                            except discord.NotFound:
                                self.logger.warning(f"Message d'embed {data['message_id']} non trouvé pour le rappel")
                        else:
                            # Envoyer un message direct si pas d'embed
                            ping_message = await notification_channel.send(ping_content)

                            # Ajouter le message de ping à Google Sheets pour suppression automatique
                            if self.ping_sheet:
                                try:
                                    self.ping_sheet.append_row([
                                        str(ping_message.id),
                                        str(notification_channel.id),
                                        datetime.now().isoformat()
                                    ])
                                except Exception as e:
                                    self.logger.error(f"Erreur lors de l'ajout du ping de rappel à Google Sheets: {e}")

                            self.logger.info(f"Ping de rappel direct envoyé pour scène inactive: {channel_info} ({days_inactive} jours)")

                except Exception as e:
                    self.logger.error(f"Erreur lors de la vérification d'inactivité pour le salon {channel_id}: {e}")

        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des scènes inactives: {e}")

    @check_inactive_scenes.before_loop
    async def before_check_inactive_scenes(self):
        await self.bot.wait_until_ready()

    def is_mj(self, user: discord.Member) -> bool:
        """Vérifie si l'utilisateur a le rôle MJ."""
        return any(role.id == MJ_ROLE_ID for role in user.roles)
    
    def get_channel_info(self, channel) -> str:
        """Retourne une description du salon (nom + type)."""
        if isinstance(channel, discord.Thread):
            if channel.parent and hasattr(channel.parent, 'type') and channel.parent.type == discord.ChannelType.forum:
                return f"fil de forum **{channel.name}** (dans {channel.parent.name})"
            else:
                return f"fil **{channel.name}** (dans {channel.parent.name if channel.parent else 'salon inconnu'})"
        elif isinstance(channel, discord.TextChannel):
            return f"**{channel.name}**"
        else:
            return f"**{getattr(channel, 'name', 'inconnu')}**"

    def create_scene_embed(self, channel, mj_user, participants: List[int] = None, last_action_user=None) -> discord.Embed:
        """Crée l'embed de surveillance d'une scène."""
        if participants is None:
            participants = []

        embed = discord.Embed(
            title="🎭 Scène surveillée",
            color=0x3498db,
            timestamp=datetime.now()
        )

        # Nom du salon
        channel_info = self.get_channel_info(channel)
        embed.add_field(
            name="Salon",
            value=channel_info,
            inline=False
        )

        # MJ responsable
        embed.add_field(
            name="MJ qui s'occupe de la scène",
            value=mj_user.display_name,
            inline=True
        )

        # Participants
        if participants:
            participant_names = []
            for user_id in participants:
                user = self.bot.get_user(user_id)
                if user:
                    participant_names.append(user.display_name)
                else:
                    participant_names.append(f"Utilisateur {user_id}")

            embed.add_field(
                name="Rôlistes participants",
                value=", ".join(participant_names) if participant_names else "Aucun",
                inline=True
            )
        else:
            embed.add_field(
                name="Rôlistes participants",
                value="Aucun",
                inline=True
            )

        # Dernière action
        if last_action_user:
            embed.add_field(
                name="Dernière action",
                value=f"Nouvelle action de **{last_action_user.display_name}**",
                inline=False
            )

        embed.set_footer(text=f"Surveillance initiée par {mj_user.display_name}")

        return embed

    async def update_scene_embed(self, channel_id: int, new_participant_id: int, action_user):
        """Met à jour l'embed de surveillance d'une scène."""
        try:
            if channel_id not in self.monitored_channels:
                return

            data = self.monitored_channels[channel_id]
            message_id = data['message_id']

            if not message_id:
                return

            # Ajouter le participant s'il n'est pas déjà dans la liste
            if new_participant_id not in data['participants']:
                data['participants'].append(new_participant_id)
                self.save_monitored_channels()

            # Récupérer le message d'embed
            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                return

            try:
                message = await notification_channel.fetch_message(message_id)

                # Récupérer les informations
                channel = self.bot.get_channel(channel_id)
                mj_user = self.bot.get_user(data['mj_user_id'])

                if not channel or not mj_user:
                    return

                # Créer le nouvel embed
                embed = self.create_scene_embed(channel, mj_user, data['participants'], action_user)

                # Créer la vue avec le bouton
                view = SceneView(self, channel_id)

                # Mettre à jour le message
                await message.edit(embed=embed, view=view)

                # Ajouter la vue persistante
                self.bot.add_view(view, message_id=message_id)

            except discord.NotFound:
                self.logger.warning(f"Message d'embed {message_id} non trouvé")
                # Retirer le message_id invalide
                data['message_id'] = None
                self.save_monitored_channels()

        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour de l'embed de scène: {e}")
    
    def setup_check(interaction: discord.Interaction) -> bool:
        """Vérifie si l'utilisateur a le rôle MJ pour utiliser la commande setup."""
        return any(role.id == MJ_ROLE_ID for role in interaction.user.roles)

    @app_commands.command(name="setup", description="Commande Staff - Ajouter un salon à la surveillance")
    @app_commands.describe(salon="Le salon à surveiller")
    @app_commands.check(setup_check)
    async def setup_monitoring(self, interaction: discord.Interaction, salon: discord.abc.GuildChannel):
        """Commande pour ajouter un salon à la surveillance."""

        # Déférer la réponse pour éviter l'expiration
        await interaction.response.defer(ephemeral=True)

        # Vérifier les permissions MJ
        if not self.is_mj(interaction.user):
            await interaction.followup.send(
                "❌ Cette commande est réservée aux MJ.",
                ephemeral=True
            )
            return
        
        # Vérifier que c'est un type de salon supporté
        if not isinstance(salon, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            await interaction.followup.send(
                "❌ Ce type de salon n'est pas supporté. Seuls les salons texte, fils et forums sont supportés.",
                ephemeral=True
            )
            return
        
        # Créer l'embed de surveillance dans le salon de notification
        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            await interaction.followup.send(
                f"❌ Erreur: Le salon de notification {NOTIFICATION_CHANNEL_ID} n'a pas été trouvé.",
                ephemeral=True
            )
            return

        # Créer l'embed initial
        embed = self.create_scene_embed(salon, interaction.user)

        # Créer la vue avec le bouton de clôture
        view = SceneView(self, salon.id)

        # Envoyer l'embed dans le salon de notification
        try:
            embed_message = await notification_channel.send(embed=embed, view=view)

            # Ajouter le salon à la surveillance avec l'ID du message
            self.monitored_channels[salon.id] = {
                'mj_user_id': interaction.user.id,
                'message_id': embed_message.id,
                'participants': [],
                'last_activity': datetime.now()
            }
            self.save_monitored_channels()

            # Ajouter la vue persistante
            self.bot.add_view(view, message_id=embed_message.id)

            channel_info = self.get_channel_info(salon)

            await interaction.followup.send(
                f"✅ Le {channel_info} est maintenant surveillé.\n"
                f"Un embed de surveillance a été créé dans <#{NOTIFICATION_CHANNEL_ID}>.",
                ephemeral=True
            )

            self.logger.info(f"MJ {interaction.user.display_name} ({interaction.user.id}) a ajouté le salon {salon.name} ({salon.id}) à la surveillance")

        except Exception as e:
            await interaction.followup.send(
                f"❌ Erreur lors de la création de l'embed de surveillance: {str(e)}",
                ephemeral=True
            )
            self.logger.error(f"Erreur lors de la création de l'embed: {e}")

    @setup_monitoring.error
    async def setup_monitoring_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Gestionnaire d'erreur pour la commande setup."""
        try:
            if isinstance(error, app_commands.CheckFailure):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Cette commande est réservée au Staff (rôle MJ requis).",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Cette commande est réservée au Staff (rôle MJ requis).",
                        ephemeral=True
                    )
            else:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Une erreur est survenue lors de l'exécution de la commande.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Une erreur est survenue lors de l'exécution de la commande.",
                        ephemeral=True
                    )
                self.logger.error(f"Erreur dans la commande setup: {error}")
        except discord.NotFound:
            # L'interaction a expiré, on ne peut plus répondre
            self.logger.error(f"Interaction expirée pour la commande setup: {error}")
        except Exception as e:
            self.logger.error(f"Erreur dans le gestionnaire d'erreur setup: {e}")
    


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Surveille les messages dans les salons surveillés."""

        # Ignorer les messages du bot
        if message.author.bot:
            return

        # Vérifier si le salon est surveillé
        channel_id = message.channel.id
        if channel_id not in self.monitored_channels:
            return

        try:
            data = self.monitored_channels[channel_id]
            mj_id = data['mj_user_id']
            mj = self.bot.get_user(mj_id)

            if not mj:
                self.logger.warning(f"MJ avec ID {mj_id} non trouvé pour le salon {channel_id}")
                return

            # Mettre à jour last_activity
            data['last_activity'] = datetime.now()
            self.save_monitored_channels()

            # Mettre à jour l'embed de surveillance
            await self.update_scene_embed(channel_id, message.author.id, message.author)

            # Récupérer le salon de notification
            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                self.logger.error(f"Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé")
                return

            # Créer un message de ping en réponse à l'embed
            if data['message_id']:
                try:
                    embed_message = await notification_channel.fetch_message(data['message_id'])

                    # Créer le message de ping
                    ping_content = f"{mj.mention} Nouvelle action dans la scène surveillée de **{message.author.display_name}** !"

                    # Envoyer le message de ping en réponse à l'embed
                    ping_message = await embed_message.reply(ping_content)

                    # Ajouter le message de ping à Google Sheets pour suppression automatique
                    if self.ping_sheet:
                        try:
                            self.ping_sheet.append_row([
                                str(ping_message.id),
                                str(notification_channel.id),
                                datetime.now().isoformat()
                            ])
                        except Exception as e:
                            self.logger.error(f"Erreur lors de l'ajout du ping à Google Sheets: {e}")

                    self.logger.info(f"Ping envoyé pour message de {message.author.display_name} dans {message.channel.name}")

                except discord.NotFound:
                    self.logger.warning(f"Message d'embed {data['message_id']} non trouvé")
                    # Retirer le message_id invalide
                    data['message_id'] = None
                    self.save_monitored_channels()

        except Exception as e:
            self.logger.error(f"Erreur lors de la notification pour le message {message.id}: {e}")

    async def setup_persistent_views(self):
        """Configure les vues persistantes pour les embeds existants."""
        try:
            for channel_id, data in self.monitored_channels.items():
                if data['message_id']:
                    view = SceneView(self, channel_id)
                    self.bot.add_view(view, message_id=data['message_id'])

            self.logger.info(f"Configuré {len(self.monitored_channels)} vues persistantes")
        except Exception as e:
            self.logger.error(f"Erreur lors de la configuration des vues persistantes: {e}")

async def setup(bot: commands.Bot):
    """Fonction de setup du cog."""
    await bot.add_cog(ChannelMonitor(bot))
    print("Cog ChannelMonitor chargé avec succès")
