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
from datetime import datetime, timedelta
from typing import Dict, Set, List
import gspread
from google.oauth2.service_account import Credentials
import asyncio
from discord.ext import tasks
import re

# Configuration
NOTIFICATION_CHANNEL_ID = 1380704586016362626  # Salon de notification
MJ_ROLE_ID = 1018179623886000278  # ID du rôle MJ

class SceneRefreshButton(discord.ui.Button):
    """Bouton pour actualiser une scène."""

    def __init__(self, cog, channel_id: int):
        super().__init__(
            label="Actualiser",
            style=discord.ButtonStyle.secondary,
            custom_id=f"refresh_scene_{channel_id}",
            emoji="🔄"
        )
        self.cog = cog
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        # Vérifier les permissions MJ
        if not self.cog.is_mj(interaction.user):
            error_embed = self.cog.create_error_embed(
                title="Accès refusé",
                description="Seuls les MJ peuvent actualiser une scène."
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Actualiser la scène
        updated = await self.cog.refresh_scene_activity(self.channel_id)

        if updated:
            success_embed = self.cog.create_success_embed(
                title="Scène actualisée",
                description="La scène a été mise à jour avec l'activité récente."
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)
        else:
            info_embed = discord.Embed(
                title="ℹ️ Aucune mise à jour",
                description="Aucune nouvelle activité détectée depuis la dernière mise à jour.",
                color=0x3498db
            )
            await interaction.followup.send(embed=info_embed, ephemeral=True)


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
            # Nettoyer également le timestamp de ping pour ce salon
            if self.channel_id in self.cog.last_ping_times:
                del self.cog.last_ping_times[self.channel_id]
                self.cog.logger.debug(f"Timestamp de ping nettoyé pour le salon {self.channel_id}")
            self.cog.save_monitored_channels()

            # Récupérer les informations du salon
            channel = self.cog.bot.get_channel(self.channel_id)
            channel_info = self.cog.get_channel_info(channel) if channel else f"Salon ID {self.channel_id}"

            # Envoyer un embed public de clôture
            try:
                closure_embed = self.cog.create_closure_embed(channel, interaction.user)
                closure_message = await interaction.response.send_message(
                    embed=closure_embed,
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

class SceneTakeOverButton(discord.ui.Button):
    """Bouton pour reprendre une scène."""

    def __init__(self, cog, channel_id: int):
        super().__init__(
            label="Reprendre la scène",
            style=discord.ButtonStyle.success,
            custom_id=f"takeover_scene_{channel_id}"
        )
        self.cog = cog
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        # Vérifier les permissions MJ
        if not self.cog.is_mj(interaction.user):
            await interaction.response.send_message(
                "❌ Seuls les MJ peuvent reprendre une scène.",
                ephemeral=True
            )
            return

        # Vérifier que la scène est toujours surveillée
        if self.channel_id in self.cog.monitored_channels:
            data = self.cog.monitored_channels[self.channel_id]
            old_mj_id = data['mj_user_id']

            # Vérifier si c'est déjà le MJ responsable
            if old_mj_id == interaction.user.id:
                await interaction.response.send_message(
                    "ℹ️ Vous êtes déjà le MJ responsable de cette scène.",
                    ephemeral=True
                )
                return

            # Mettre à jour le MJ responsable
            await self.cog.take_over_scene(self.channel_id, interaction.user.id)

            # Récupérer les informations du salon
            channel = self.cog.bot.get_channel(self.channel_id)
            channel_info = self.cog.get_channel_info(channel) if channel else f"salon {self.channel_id}"

            await interaction.response.send_message(
                f"✅ Vous avez repris la responsabilité de {channel_info}.",
                ephemeral=True
            )

            self.cog.logger.info(f"MJ {interaction.user.display_name} ({interaction.user.id}) a repris la scène {self.channel_id}")
        else:
            await interaction.response.send_message(
                "❌ Cette scène n'est plus surveillée.",
                ephemeral=True
            )

class SceneView(discord.ui.View):
    """Vue avec les boutons de gestion de scène."""

    def __init__(self, cog, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(SceneRefreshButton(cog, channel_id))
        self.add_item(SceneTakeOverButton(cog, channel_id))
        self.add_item(SceneCloseButton(cog, channel_id))

class ChannelMonitor(commands.Cog):
    """Cog pour surveiller les salons et notifier les MJ."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.monitored_channels: Dict[int, dict] = {}  # {channel_id: {mj_user_id, message_id, participants, last_activity}}
        self.last_ping_times: Dict[int, datetime] = {}  # {channel_id: datetime} - Suivi des derniers pings par salon
        self.ping_cooldown_minutes = 5  # Intervalle de 5 minutes entre les pings par salon
        self.logger = logging.getLogger('channel_monitor')
        self.gspread_client = None
        self.sheet = None
        self.ping_sheet = None
        self.alert_sheet = None
        # Initialisation asynchrone pour éviter les délais au démarrage
        self.bot.loop.create_task(self.async_init())
        self._start_tasks()

    async def async_init(self):
        """Initialisation asynchrone du cog."""
        await self.bot.wait_until_ready()
        self.setup_google_sheets()
        self.load_monitored_channels()
        await self.setup_persistent_views()
        # Nettoyer immédiatement les messages de ping expirés au démarrage
        await self.cleanup_ping_messages_immediate()
        # Nettoyer les anciennes alertes d'inactivité
        self.cleanup_old_alerts()
        # Vérifier l'activité manquée pendant la déconnexion
        await self.check_missed_activity()
        # Mettre à jour tous les embeds existants avec le nouveau format
        await self.update_all_existing_embeds()

    def _start_tasks(self):
        """Démarre les tâches avec gestion d'erreurs."""
        try:
            if not self.cleanup_ping_messages.is_running():
                self.cleanup_ping_messages.start()
                self.logger.info("✅ Tâche cleanup_ping_messages démarrée")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du démarrage de cleanup_ping_messages: {e}")

        try:
            if not self.check_inactive_scenes.is_running():
                self.check_inactive_scenes.start()
                self.logger.info("✅ Tâche check_inactive_scenes démarrée")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du démarrage de check_inactive_scenes: {e}")

    def _restart_task_if_needed(self, task, task_name):
        """Redémarre une tâche si elle n'est pas en cours d'exécution."""
        try:
            if not task.is_running():
                self.logger.warning(f"⚠️ Tâche {task_name} arrêtée, redémarrage...")
                task.restart()
                self.logger.info(f"✅ Tâche {task_name} redémarrée")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du redémarrage de {task_name}: {e}")

    async def cog_unload(self):
        """Nettoie les ressources lors du déchargement du cog."""
        try:
            if self.cleanup_ping_messages.is_running():
                self.cleanup_ping_messages.cancel()
            if self.check_inactive_scenes.is_running():
                self.check_inactive_scenes.cancel()
            self.logger.info("🧹 Tâches du cog channel_monitor arrêtées")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'arrêt des tâches: {e}")

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

            # Feuille pour le suivi des alertes d'inactivité
            try:
                self.alert_sheet = spreadsheet.worksheet("Inactivity Alerts")
            except gspread.exceptions.WorksheetNotFound:
                self.alert_sheet = spreadsheet.add_worksheet(
                    title="Inactivity Alerts",
                    rows="1000",
                    cols="4"
                )
                # Initialiser l'en-tête
                self.alert_sheet.append_row(["channel_id", "mj_user_id", "alert_date", "timestamp"])

            self.logger.info("[CHANNEL_MONITOR] Connexion Google Sheets établie")
        except Exception as e:
            self.logger.error(f"[CHANNEL_MONITOR] Erreur lors de la configuration Google Sheets: {e}")
            self.gspread_client = None
            self.sheet = None
            self.ping_sheet = None
            self.alert_sheet = None

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

                        # Récupérer last_alert_sent (colonne 11, index 11)
                        last_alert_sent = None
                        if len(row) > 11 and row[11]:
                            try:
                                last_alert_sent = datetime.fromisoformat(row[11])
                            except ValueError:
                                last_alert_sent = None

                        self.monitored_channels[channel_id] = {
                            'mj_user_id': mj_user_id,
                            'message_id': message_id,
                            'participants': participants,
                            'last_activity': last_activity,
                            'last_alert_sent': last_alert_sent
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
            self.sheet.append_row(["channel_id", "mj_user_id", "message_id", "participant_1", "participant_2", "participant_3", "participant_4", "participant_5", "participant_6", "added_at", "last_activity", "last_alert_sent"])

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

                # Ajouter last_alert_sent
                last_alert_sent = data.get('last_alert_sent')
                row.append(last_alert_sent.isoformat() if last_alert_sent else "")

                self.sheet.append_row(row)

            self.logger.info(f"Sauvegardé {len(self.monitored_channels)} salons surveillés dans Google Sheets")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des salons surveillés: {e}")

    def has_alert_been_sent_today(self, channel_id: int) -> bool:
        """Vérifie si une alerte d'inactivité a déjà été envoyée aujourd'hui pour ce salon."""
        try:
            data = self.monitored_channels.get(channel_id)
            if not data:
                return False

            last_alert_sent = data.get('last_alert_sent')
            if not last_alert_sent:
                return False

            # Vérifier si l'alerte a été envoyée aujourd'hui
            today = datetime.now().date()
            alert_date = last_alert_sent.date()

            return alert_date == today
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification d'alerte pour le salon {channel_id}: {e}")
            return False

    def record_alert_sent(self, channel_id: int, mj_user_id: int):
        """Enregistre qu'une alerte d'inactivité a été envoyée pour ce salon."""
        try:
            current_time = datetime.now()

            # Mettre à jour les données en mémoire
            if channel_id in self.monitored_channels:
                self.monitored_channels[channel_id]['last_alert_sent'] = current_time
                self.save_monitored_channels()

            # Enregistrer dans la feuille des alertes
            if self.alert_sheet:
                try:
                    self.alert_sheet.append_row([
                        str(channel_id),
                        str(mj_user_id),
                        current_time.date().isoformat(),
                        current_time.isoformat()
                    ])
                except Exception as e:
                    self.logger.error(f"Erreur lors de l'enregistrement de l'alerte dans Google Sheets: {e}")

            self.logger.info(f"Alerte d'inactivité enregistrée pour le salon {channel_id}")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'enregistrement d'alerte pour le salon {channel_id}: {e}")

    def cleanup_old_alerts(self):
        """Nettoie les anciennes entrées d'alertes (plus de 30 jours)."""
        try:
            if not self.alert_sheet:
                return

            current_time = datetime.now()
            thirty_days_ago = current_time - timedelta(days=30)

            all_values = self.alert_sheet.get_all_values()
            if len(all_values) <= 1:  # Seulement l'en-tête ou vide
                return

            # Identifier les lignes à supprimer (plus de 30 jours)
            rows_to_keep = [all_values[0]]  # Garder l'en-tête
            cleaned_count = 0

            for row in all_values[1:]:
                if len(row) >= 4 and row[3]:  # Vérifier que timestamp existe
                    try:
                        alert_timestamp = datetime.fromisoformat(row[3])
                        if alert_timestamp >= thirty_days_ago:
                            rows_to_keep.append(row)
                        else:
                            cleaned_count += 1
                    except ValueError:
                        # Garder les lignes avec des timestamps invalides
                        rows_to_keep.append(row)
                else:
                    # Garder les lignes incomplètes
                    rows_to_keep.append(row)

            # Réécrire la feuille si des lignes ont été supprimées
            if cleaned_count > 0:
                self.alert_sheet.clear()
                for row in rows_to_keep:
                    self.alert_sheet.append_row(row)

                self.logger.info(f"Nettoyé {cleaned_count} anciennes alertes d'inactivité")

        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage des anciennes alertes: {e}")

    @tasks.loop(hours=1)
    async def cleanup_ping_messages(self):
        """Nettoie les messages de ping anciens (plus de 24h) - Exécution périodique."""
        try:
            if not self.ping_sheet:
                self.logger.warning("Google Sheets non configuré pour le nettoyage périodique")
                return

            current_time = datetime.now()
            all_values = self.ping_sheet.get_all_values()

            if len(all_values) <= 1:  # Seulement l'en-tête ou vide
                return

            rows_to_delete = []
            messages_deleted = 0

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
                                    messages_deleted += 1
                                    self.logger.debug(f"Message de ping supprimé (périodique): {message_id}")
                            except discord.NotFound:
                                # Message déjà supprimé
                                self.logger.debug(f"Message de ping {message_id} déjà supprimé")
                            except discord.Forbidden:
                                self.logger.warning(f"Permissions insuffisantes pour supprimer le message {message_id}")
                            except Exception as e:
                                self.logger.error(f"Erreur lors de la suppression du message de ping {message_id}: {e}")

                            rows_to_delete.append(idx)
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Ligne de ping invalide ignorée (périodique): {row} - Erreur: {e}")
                        rows_to_delete.append(idx)

            # Supprimer les lignes en commençant par la fin pour éviter les décalages d'index
            for row_idx in reversed(rows_to_delete):
                try:
                    self.ping_sheet.delete_rows(row_idx)
                except Exception as e:
                    self.logger.error(f"Erreur lors de la suppression de la ligne {row_idx}: {e}")

            if rows_to_delete:
                self.logger.info(f"Nettoyage périodique: supprimé {messages_deleted} messages de ping expirés et {len(rows_to_delete)} entrées de la base")

            # Nettoyer les anciennes alertes une fois par jour (à la première exécution de chaque jour)
            current_hour = datetime.now().hour
            if current_hour == 0:  # Minuit
                self.cleanup_old_alerts()

        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage périodique des messages de ping: {e}")
            # Redémarrer la tâche en cas d'erreur critique
            self._restart_task_if_needed(self.cleanup_ping_messages, "cleanup_ping_messages")

    @cleanup_ping_messages.before_loop
    async def before_cleanup_ping_messages(self):
        await self.bot.wait_until_ready()

    @cleanup_ping_messages.error
    async def cleanup_ping_messages_error(self, error):
        """Gère les erreurs de la tâche cleanup_ping_messages."""
        self.logger.error(f"❌ Erreur dans cleanup_ping_messages: {error}")
        # Redémarrer la tâche après une erreur
        await asyncio.sleep(60)  # Attendre 1 minute avant de redémarrer
        self._restart_task_if_needed(self.cleanup_ping_messages, "cleanup_ping_messages")

    async def cleanup_ping_messages_immediate(self):
        """Nettoie immédiatement les messages de ping expirés au démarrage."""
        try:
            if not self.ping_sheet:
                self.logger.warning("Google Sheets non configuré, impossible de nettoyer les messages de ping")
                return

            current_time = datetime.now()
            all_values = self.ping_sheet.get_all_values()

            if len(all_values) <= 1:  # Seulement l'en-tête ou vide
                self.logger.info("Aucun message de ping à nettoyer")
                return

            rows_to_delete = []
            messages_deleted = 0

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
                                    messages_deleted += 1
                                    self.logger.info(f"Message de ping expiré supprimé au démarrage: {message_id}")
                            except discord.NotFound:
                                # Message déjà supprimé
                                self.logger.debug(f"Message de ping {message_id} déjà supprimé")
                            except Exception as e:
                                self.logger.error(f"Erreur lors de la suppression du message de ping {message_id}: {e}")

                            rows_to_delete.append(idx)
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Ligne de ping invalide ignorée au démarrage: {row} - Erreur: {e}")
                        rows_to_delete.append(idx)

            # Supprimer les lignes en commençant par la fin pour éviter les décalages d'index
            for row_idx in reversed(rows_to_delete):
                self.ping_sheet.delete_rows(row_idx)

            if rows_to_delete:
                self.logger.info(f"Nettoyage au démarrage: supprimé {messages_deleted} messages de ping expirés et {len(rows_to_delete)} entrées de la base")
            else:
                self.logger.info("Aucun message de ping expiré trouvé au démarrage")

        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage immédiat des messages de ping: {e}")

    async def update_all_existing_embeds(self):
        """Met à jour tous les embeds de surveillance existants avec le nouveau format."""
        try:
            if not self.monitored_channels:
                self.logger.info("Aucun embed de surveillance à mettre à jour")
                return

            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                self.logger.error(f"Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé pour la mise à jour des embeds")
                return

            updated_count = 0
            failed_count = 0

            for channel_id, data in self.monitored_channels.items():
                try:
                    message_id = data.get('message_id')
                    if not message_id:
                        continue

                    # Récupérer le message d'embed existant
                    try:
                        message = await notification_channel.fetch_message(message_id)
                    except discord.NotFound:
                        self.logger.warning(f"Message d'embed {message_id} non trouvé pour le salon {channel_id}")
                        # Nettoyer l'entrée invalide
                        data['message_id'] = None
                        failed_count += 1
                        continue

                    # Récupérer les informations du salon et du MJ
                    channel = self.bot.get_channel(channel_id)
                    mj_user = self.bot.get_user(data['mj_user_id'])

                    if not channel or not mj_user:
                        self.logger.warning(f"Salon {channel_id} ou MJ {data['mj_user_id']} non trouvé")
                        failed_count += 1
                        continue

                    # Créer le nouvel embed avec le format amélioré
                    embed = self.create_scene_embed(channel, mj_user, data.get('participants', []))

                    # Créer la vue avec le bouton
                    view = SceneView(self, channel_id)

                    # Mettre à jour le message
                    await message.edit(embed=embed, view=view)

                    # Ajouter la vue persistante
                    self.bot.add_view(view, message_id=message_id)

                    updated_count += 1
                    self.logger.debug(f"Embed mis à jour pour le salon {channel_id}")

                except Exception as e:
                    self.logger.error(f"Erreur lors de la mise à jour de l'embed pour le salon {channel_id}: {e}")
                    failed_count += 1

            # Sauvegarder les changements si des message_id ont été nettoyés
            if failed_count > 0:
                self.save_monitored_channels()

            self.logger.info(f"Mise à jour des embeds terminée: {updated_count} réussis, {failed_count} échoués")

        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour globale des embeds: {e}")

    async def check_missed_activity(self):
        """Vérifie l'activité manquée dans les scènes surveillées pendant la déconnexion du bot."""
        try:
            if not self.monitored_channels:
                self.logger.info("Aucune scène surveillée à vérifier pour l'activité manquée")
                return

            self.logger.info("Vérification de l'activité manquée pendant la déconnexion...")
            updated_scenes = 0

            for channel_id, data in self.monitored_channels.items():
                try:
                    # Récupérer le salon
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        self.logger.warning(f"Salon {channel_id} non trouvé pour la vérification d'activité manquée")
                        continue

                    # Récupérer la dernière activité enregistrée
                    last_recorded_activity = data.get('last_activity')
                    if not last_recorded_activity:
                        self.logger.debug(f"Pas de dernière activité enregistrée pour le salon {channel_id}")
                        continue

                    # Convertir en datetime si c'est une string
                    if isinstance(last_recorded_activity, str):
                        try:
                            last_recorded_activity = datetime.fromisoformat(last_recorded_activity)
                        except ValueError:
                            self.logger.warning(f"Format de date invalide pour le salon {channel_id}: {last_recorded_activity}")
                            continue

                    # Récupérer les messages récents depuis la dernière activité
                    try:
                        # Limiter la vérification aux 7 derniers jours maximum pour éviter les surcharges
                        max_check_period = datetime.now() - timedelta(days=7)
                        check_after = max(last_recorded_activity, max_check_period)

                        # Limiter à 200 messages pour éviter les surcharges
                        messages = []
                        message_count = 0
                        async for message in channel.history(limit=200, after=check_after):
                            if not message.author.bot:  # Ignorer les messages de bots
                                messages.append(message)
                                message_count += 1

                        if message_count >= 200:
                            self.logger.warning(f"Limite de 200 messages atteinte pour le salon {channel_id}, certains messages peuvent être manqués")

                        if not messages:
                            self.logger.debug(f"Aucune nouvelle activité trouvée pour le salon {channel_id}")
                            continue

                        # Trier les messages par timestamp (plus récent en dernier)
                        messages.sort(key=lambda m: m.created_at)

                        # Traiter chaque message manqué
                        new_participants = set(data.get('participants', []))
                        last_action_user = None

                        for message in messages:
                            # Ajouter l'auteur aux participants s'il n'y est pas déjà
                            if message.author.id not in new_participants:
                                new_participants.add(message.author.id)
                                self.logger.info(f"Nouveau participant détecté pendant la déconnexion: {message.author.display_name} dans le salon {channel_id}")

                            last_action_user = message.author

                            # Mettre à jour la dernière activité avec le timestamp du message
                            data['last_activity'] = message.created_at

                        # Mettre à jour la liste des participants
                        data['participants'] = list(new_participants)

                        # Mettre à jour l'embed avec la dernière activité
                        if last_action_user:
                            await self.update_scene_embed(channel_id, last_action_user.id, last_action_user)
                            updated_scenes += 1
                            self.logger.info(f"Scène {channel_id} mise à jour avec l'activité manquée de {last_action_user.display_name}")

                    except discord.Forbidden:
                        self.logger.warning(f"Permissions insuffisantes pour lire l'historique du salon {channel_id}")
                    except discord.HTTPException as e:
                        self.logger.error(f"Erreur HTTP lors de la lecture de l'historique du salon {channel_id}: {e}")

                except Exception as e:
                    self.logger.error(f"Erreur lors de la vérification d'activité manquée pour le salon {channel_id}: {e}")

            # Sauvegarder toutes les modifications
            if updated_scenes > 0:
                self.save_monitored_channels()
                self.logger.info(f"Vérification d'activité manquée terminée: {updated_scenes} scènes mises à jour")
            else:
                self.logger.info("Aucune activité manquée détectée")

        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification globale d'activité manquée: {e}")

    async def refresh_scene_activity(self, channel_id: int) -> bool:
        """
        Force la vérification et la mise à jour d'une scène spécifique.
        Retourne True si la scène a été mise à jour, False sinon.
        """
        try:
            if channel_id not in self.monitored_channels:
                return False

            data = self.monitored_channels[channel_id]
            channel = self.bot.get_channel(channel_id)

            if not channel:
                return False

            # Récupérer la dernière activité enregistrée
            last_recorded_activity = data.get('last_activity')
            if not last_recorded_activity:
                return False

            # Convertir en datetime si c'est une string
            if isinstance(last_recorded_activity, str):
                try:
                    last_recorded_activity = datetime.fromisoformat(last_recorded_activity)
                except ValueError:
                    return False

            # Récupérer les messages récents
            try:
                messages = []
                async for message in channel.history(limit=50, after=last_recorded_activity):
                    if not message.author.bot:
                        messages.append(message)

                if not messages:
                    return False

                # Trier par timestamp
                messages.sort(key=lambda m: m.created_at)

                # Traiter les messages
                new_participants = set(data.get('participants', []))
                last_action_user = None

                for message in messages:
                    if message.author.id not in new_participants:
                        new_participants.add(message.author.id)
                    last_action_user = message.author
                    data['last_activity'] = message.created_at

                # Mettre à jour
                data['participants'] = list(new_participants)

                if last_action_user:
                    await self.update_scene_embed(channel_id, last_action_user.id, last_action_user)
                    self.save_monitored_channels()
                    return True

            except (discord.Forbidden, discord.HTTPException):
                return False

        except Exception as e:
            self.logger.error(f"Erreur lors du rafraîchissement de la scène {channel_id}: {e}")

        return False

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
                        # Vérifier si une alerte a déjà été envoyée aujourd'hui
                        if self.has_alert_been_sent_today(channel_id):
                            self.logger.debug(f"Alerte déjà envoyée aujourd'hui pour le salon {channel_id}, ignoré")
                            continue

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

                        # Créer l'embed de rappel
                        days_inactive = int((current_time - last_activity).days)
                        reminder_embed = self.create_reminder_embed(mj, channel, channel_id, days_inactive)

                        # Envoyer l'embed de rappel
                        if data['message_id']:
                            try:
                                embed_message = await notification_channel.fetch_message(data['message_id'])
                                ping_message = await embed_message.reply(content=mj.mention, embed=reminder_embed)

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

                                # Enregistrer que l'alerte a été envoyée
                                self.record_alert_sent(channel_id, mj_id)
                                self.logger.info(f"Ping de rappel envoyé pour scène inactive: {channel_info} ({days_inactive} jours)")

                            except discord.NotFound:
                                self.logger.warning(f"Message d'embed {data['message_id']} non trouvé pour le rappel")
                        else:
                            # Envoyer l'embed directement si pas d'embed de surveillance
                            ping_message = await notification_channel.send(content=mj.mention, embed=reminder_embed)

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

                            # Enregistrer que l'alerte a été envoyée
                            self.record_alert_sent(channel_id, mj_id)
                            self.logger.info(f"Ping de rappel direct envoyé pour scène inactive: {channel_info} ({days_inactive} jours)")

                except Exception as e:
                    self.logger.error(f"Erreur lors de la vérification d'inactivité pour le salon {channel_id}: {e}")

        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des scènes inactives: {e}")
            # Redémarrer la tâche en cas d'erreur critique
            self._restart_task_if_needed(self.check_inactive_scenes, "check_inactive_scenes")

    @check_inactive_scenes.before_loop
    async def before_check_inactive_scenes(self):
        await self.bot.wait_until_ready()

    @check_inactive_scenes.error
    async def check_inactive_scenes_error(self, error):
        """Gère les erreurs de la tâche check_inactive_scenes."""
        self.logger.error(f"❌ Erreur dans check_inactive_scenes: {error}")
        # Redémarrer la tâche après une erreur
        await asyncio.sleep(300)  # Attendre 5 minutes avant de redémarrer
        self._restart_task_if_needed(self.check_inactive_scenes, "check_inactive_scenes")

    def is_mj(self, user: discord.Member) -> bool:
        """Vérifie si l'utilisateur a le rôle MJ."""
        return any(role.id == MJ_ROLE_ID for role in user.roles)

    def parse_discord_url(self, url: str) -> int | None:
        """
        Parse une URL Discord pour extraire l'ID du salon/fil/post de forum.

        Formats supportés:
        - https://discord.com/channels/GUILD_ID/CHANNEL_ID
        - https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
        - https://ptb.discord.com/channels/GUILD_ID/CHANNEL_ID
        - https://canary.discord.com/channels/GUILD_ID/CHANNEL_ID

        Args:
            url: L'URL Discord à parser

        Returns:
            int: L'ID du salon/fil, ou None si l'URL est invalide
        """
        # Pattern pour matcher les URLs Discord
        pattern = r'https://(?:ptb\.|canary\.)?discord\.com/channels/\d+/(\d+)(?:/\d+)?'
        match = re.match(pattern, url.strip())

        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None
    
    def get_channel_info(self, channel) -> str:
        """Retourne une description du salon (nom seulement)."""
        if isinstance(channel, discord.Thread):
            return f"**{channel.name}**"
        elif isinstance(channel, discord.TextChannel):
            return f"**{channel.name}**"
        else:
            return f"**{getattr(channel, 'name', 'inconnu')}**"

    def get_detailed_channel_info(self, channel) -> dict:
        """Retourne des informations détaillées sur le salon."""
        info = {
            'name': getattr(channel, 'name', 'inconnu'),
            'type': 'inconnu',
            'parent_name': None,
            'forum_name': None
        }

        if isinstance(channel, discord.Thread):
            info['type'] = 'thread'
            if hasattr(channel, 'parent') and channel.parent:
                info['parent_name'] = channel.parent.name
                # Si le parent est un forum
                if isinstance(channel.parent, discord.ForumChannel):
                    info['type'] = 'forum_post'
                    info['forum_name'] = channel.parent.name
        elif isinstance(channel, discord.TextChannel):
            info['type'] = 'text_channel'

        return info

    async def ensure_thread_unarchived(self, thread):
        """
        S'assure qu'un thread est désarchivé et déverrouillé pour permettre l'interaction.

        Args:
            thread: Le thread Discord à vérifier/modifier

        Returns:
            tuple: (success: bool, (was_archived: bool, was_locked: bool))
        """
        if not thread or not isinstance(thread, discord.Thread):
            self.logger.warning(f"Thread fourni est None ou n'est pas un Thread")
            return False, (False, False)

        was_archived = thread.archived
        was_locked = thread.locked

        # Si le thread n'est ni archivé ni verrouillé, pas besoin de le modifier
        if not was_archived and not was_locked:
            self.logger.info(f"Thread {thread.id} ({thread.name}) est déjà ouvert.")
            return True, (was_archived, was_locked)

        # Tenter plusieurs fois de désarchiver ou déverrouiller si nécessaire
        for attempt in range(3):  # Essayer 3 fois
            try:
                self.logger.info(f"Tentative #{attempt+1} de réouverture du thread {thread.id} ({thread.name})")

                # Désarchiver et/ou déverrouiller
                await thread.edit(archived=False, locked=False)
                await asyncio.sleep(2)  # Attendre que les changements prennent effet

                # Rafraîchir le thread pour vérifier son état
                try:
                    # Utiliser fetch_channel au lieu de get_channel pour forcer une actualisation
                    reloaded_thread = await thread.guild.fetch_channel(thread.id)
                    if not reloaded_thread.archived and not reloaded_thread.locked:
                        self.logger.info(f"Thread {thread.id} réouvert avec succès")
                        return True, (was_archived, was_locked)
                    else:
                        self.logger.warning(f"Le thread {thread.id} est toujours fermé après édition")
                except Exception as e:
                    self.logger.error(f"Erreur lors du rechargement du thread: {e}")

            except discord.HTTPException as e:
                self.logger.error(f"Erreur HTTP lors de la réouverture du thread: {e}")
            except Exception as e:
                self.logger.error(f"Erreur générale lors de la réouverture du thread: {type(e).__name__}: {e}")

            if attempt < 2:  # Ne pas attendre après la dernière tentative
                self.logger.info(f"Tentative #{attempt+1} échouée, attente avant réessai...")
                await asyncio.sleep(3)

        self.logger.error(f"Impossible de rouvrir le thread {thread.id} après 3 tentatives")
        return False, (was_archived, was_locked)

    def can_send_ping(self, channel_id: int) -> bool:
        """
        Vérifie si un ping peut être envoyé pour un salon donné en respectant l'intervalle de cooldown.

        Args:
            channel_id: ID du salon à vérifier

        Returns:
            bool: True si un ping peut être envoyé, False sinon
        """
        current_time = datetime.now()

        # Si aucun ping n'a été envoyé pour ce salon, on peut envoyer
        if channel_id not in self.last_ping_times:
            return True

        # Vérifier si assez de temps s'est écoulé depuis le dernier ping
        last_ping_time = self.last_ping_times[channel_id]
        time_since_last_ping = current_time - last_ping_time
        cooldown_seconds = self.ping_cooldown_minutes * 60

        return time_since_last_ping.total_seconds() >= cooldown_seconds

    def update_last_ping_time(self, channel_id: int):
        """
        Met à jour le timestamp du dernier ping pour un salon donné.

        Args:
            channel_id: ID du salon pour lequel mettre à jour le timestamp
        """
        self.last_ping_times[channel_id] = datetime.now()
        self.logger.debug(f"Timestamp de dernier ping mis à jour pour le salon {channel_id}")

    def get_remaining_cooldown(self, channel_id: int) -> int:
        """
        Retourne le temps restant avant de pouvoir envoyer un nouveau ping (en secondes).

        Args:
            channel_id: ID du salon à vérifier

        Returns:
            int: Nombre de secondes restantes, 0 si un ping peut être envoyé
        """
        if self.can_send_ping(channel_id):
            return 0

        current_time = datetime.now()
        last_ping_time = self.last_ping_times[channel_id]
        time_since_last_ping = current_time - last_ping_time
        cooldown_seconds = self.ping_cooldown_minutes * 60

        return max(0, cooldown_seconds - int(time_since_last_ping.total_seconds()))

    def create_scene_embed(self, channel, mj_user, participants: List[int] = None, last_action_user=None) -> discord.Embed:
        """Crée l'embed de surveillance d'une scène."""
        if participants is None:
            participants = []

        embed = discord.Embed(
            title="🎭 Scène surveillée",
            color=0x3498db,
            timestamp=datetime.now()
        )

        # Informations détaillées du salon
        channel_details = self.get_detailed_channel_info(channel)
        channel_link = f"<#{channel.id}>"

        # Construire la description du salon (juste le lien, pas de répétition du nom)
        salon_info = channel_link

        # Ajouter les informations de forum/thread parent si applicable
        if channel_details['type'] == 'forum_post' and channel_details['forum_name']:
            salon_info += f"\n🗂️ **Forum :** {channel_details['forum_name']}"
        elif channel_details['type'] == 'thread' and channel_details['parent_name']:
            salon_info += f"\n💬 **Salon parent :** {channel_details['parent_name']}"

        embed.add_field(
            name="📍 Scène",
            value=salon_info,
            inline=False
        )

        # MJ responsable
        embed.add_field(
            name="🎯 MJ responsable",
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
                name="👥 Rôlistes participants",
                value=", ".join(participant_names) if participant_names else "Aucun",
                inline=True
            )
        else:
            embed.add_field(
                name="👥 Rôlistes participants",
                value="Aucun",
                inline=True
            )

        # Dernière action avec timestamp plus visible
        if last_action_user:
            embed.add_field(
                name="⏰ Dernière action",
                value=f"**{last_action_user.display_name}** - <t:{int(datetime.now().timestamp())}:R>",
                inline=False
            )
        else:
            embed.add_field(
                name="⏰ Dernière action",
                value=f"Surveillance initiée - <t:{int(datetime.now().timestamp())}:R>",
                inline=False
            )

        embed.set_footer(text=f"Surveillance initiée par {mj_user.display_name}")

        return embed

    def create_ping_embed(self, mj_user, action_user, channel, channel_id: int) -> discord.Embed:
        """Crée un embed pour les notifications de ping d'activité."""
        channel_details = self.get_detailed_channel_info(channel)

        embed = discord.Embed(
            title="🔔 Nouvelle activité détectée",
            color=0x3498db,
            timestamp=datetime.now()
        )

        # Information sur l'action
        embed.add_field(
            name="👤 Joueur actif",
            value=f"**{action_user.display_name}**",
            inline=True
        )

        embed.add_field(
            name="🎯 MJ notifié",
            value=f"{mj_user.mention}",
            inline=True
        )

        # Informations du salon
        salon_info = f"<#{channel_id}>"
        if channel_details['type'] == 'forum_post' and channel_details['forum_name']:
            salon_info += f"\n🗂️ **Forum :** {channel_details['forum_name']}"
        elif channel_details['type'] == 'thread' and channel_details['parent_name']:
            salon_info += f"\n💬 **Salon parent :** {channel_details['parent_name']}"

        embed.add_field(
            name="📍 Scène",
            value=salon_info,
            inline=False
        )

        embed.set_footer(text="Système de surveillance des scènes")

        return embed

    def create_reminder_embed(self, mj_user, channel, channel_id: int, days_inactive: int) -> discord.Embed:
        """Crée un embed pour les rappels de scènes inactives."""
        channel_details = self.get_detailed_channel_info(channel)

        embed = discord.Embed(
            title="⏰ Rappel de scène inactive",
            color=0xe74c3c,  # Rouge pour attirer l'attention
            timestamp=datetime.now()
        )

        embed.add_field(
            name="🎯 MJ responsable",
            value=f"{mj_user.mention}",
            inline=True
        )

        embed.add_field(
            name="⏳ Inactivité",
            value=f"**{days_inactive} jours**",
            inline=True
        )

        # Informations du salon
        salon_info = f"<#{channel_id}>"
        if channel_details['type'] == 'forum_post' and channel_details['forum_name']:
            salon_info += f"\n🗂️ **Forum :** {channel_details['forum_name']}"
        elif channel_details['type'] == 'thread' and channel_details['parent_name']:
            salon_info += f"\n💬 **Salon parent :** {channel_details['parent_name']}"

        embed.add_field(
            name="📍 Scène inactive",
            value=salon_info,
            inline=False
        )

        embed.add_field(
            name="💡 Action recommandée",
            value="Pensez à vérifier si cette scène nécessite votre attention !",
            inline=False
        )

        embed.set_footer(text="Système de surveillance des scènes")

        return embed

    def create_success_embed(self, title: str, description: str, channel=None, mj_user=None, thread_reopened: bool = False) -> discord.Embed:
        """Crée un embed pour les messages de succès."""
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=0x27ae60,  # Vert pour le succès
            timestamp=datetime.now()
        )

        if channel:
            channel_details = self.get_detailed_channel_info(channel)
            salon_info = f"<#{channel.id}>"
            if channel_details['type'] == 'forum_post' and channel_details['forum_name']:
                salon_info += f"\n🗂️ **Forum :** {channel_details['forum_name']}"
            elif channel_details['type'] == 'thread' and channel_details['parent_name']:
                salon_info += f"\n💬 **Salon parent :** {channel_details['parent_name']}"

            embed.add_field(
                name="📍 Scène surveillée",
                value=salon_info,
                inline=False
            )

        if mj_user:
            embed.add_field(
                name="🎯 MJ responsable",
                value=mj_user.display_name,
                inline=True
            )

        embed.add_field(
            name="📊 Surveillance",
            value=f"Un embed de surveillance a été créé dans <#{NOTIFICATION_CHANNEL_ID}>",
            inline=True
        )

        if thread_reopened:
            embed.add_field(
                name="🔄 Thread rouvert",
                value="Le fil a été automatiquement rouvert pour permettre la surveillance",
                inline=False
            )

        embed.set_footer(text="Système de surveillance des scènes")

        return embed

    def create_error_embed(self, title: str, description: str, error_details: str = None) -> discord.Embed:
        """Crée un embed pour les messages d'erreur."""
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=0xe74c3c,  # Rouge pour les erreurs
            timestamp=datetime.now()
        )

        if error_details:
            embed.add_field(
                name="🔍 Détails de l'erreur",
                value=f"```{error_details}```",
                inline=False
            )

        embed.set_footer(text="Système de surveillance des scènes")

        return embed

    def create_closure_embed(self, channel, closed_by_user) -> discord.Embed:
        """Crée un embed pour les messages de clôture de scène."""
        channel_details = self.get_detailed_channel_info(channel)

        embed = discord.Embed(
            title="🔒 Scène clôturée",
            color=0x95a5a6,  # Gris pour la clôture
            timestamp=datetime.now()
        )

        # Informations du salon
        salon_info = f"**{channel_details['name']}**"
        if channel_details['type'] == 'forum_post' and channel_details['forum_name']:
            salon_info += f"\n🗂️ **Forum :** {channel_details['forum_name']}"
        elif channel_details['type'] == 'thread' and channel_details['parent_name']:
            salon_info += f"\n💬 **Salon parent :** {channel_details['parent_name']}"

        embed.add_field(
            name="📍 Scène fermée",
            value=salon_info,
            inline=False
        )

        embed.add_field(
            name="👤 Clôturée par",
            value=closed_by_user.display_name,
            inline=True
        )

        embed.add_field(
            name="📊 Statut",
            value="Cette scène n'est plus surveillée",
            inline=True
        )

        embed.set_footer(text="Système de surveillance des scènes")

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
            participant_added = False
            if new_participant_id not in data['participants']:
                data['participants'].append(new_participant_id)
                participant_added = True

            # Toujours sauvegarder car last_activity a été mis à jour
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

                # Créer le nouvel embed avec les informations à jour
                embed = self.create_scene_embed(channel, mj_user, data['participants'], action_user)

                # Créer la vue avec le bouton
                view = SceneView(self, channel_id)

                # Mettre à jour le message (toujours, pour actualiser le timestamp)
                await message.edit(embed=embed, view=view)

                # Ajouter la vue persistante
                self.bot.add_view(view, message_id=message_id)

                if participant_added:
                    self.logger.debug(f"Nouveau participant {action_user.display_name} ajouté à la scène {channel_id}")
                else:
                    self.logger.debug(f"Embed mis à jour pour l'activité de {action_user.display_name} dans la scène {channel_id}")

            except discord.NotFound:
                self.logger.warning(f"Message d'embed {message_id} non trouvé")
                # Retirer le message_id invalide
                data['message_id'] = None
                self.save_monitored_channels()

        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour de l'embed de scène: {e}")

    async def take_over_scene(self, channel_id: int, new_mj_id: int):
        """
        Transfère la responsabilité d'une scène à un nouveau MJ.

        Args:
            channel_id: ID du salon surveillé
            new_mj_id: ID du nouveau MJ responsable
        """
        try:
            if channel_id not in self.monitored_channels:
                return

            # Mettre à jour les données en mémoire
            data = self.monitored_channels[channel_id]
            old_mj_id = data['mj_user_id']
            data['mj_user_id'] = new_mj_id

            # Sauvegarder dans Google Sheets
            self.save_monitored_channels()

            # Mettre à jour l'embed
            message_id = data['message_id']
            if message_id:
                notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
                if notification_channel:
                    try:
                        message = await notification_channel.fetch_message(message_id)

                        # Récupérer les informations
                        channel = self.bot.get_channel(channel_id)
                        new_mj_user = self.bot.get_user(new_mj_id)

                        if channel and new_mj_user:
                            # Créer le nouvel embed avec le nouveau MJ
                            embed = self.create_scene_embed(channel, new_mj_user, data['participants'])

                            # Créer la vue avec les boutons
                            view = SceneView(self, channel_id)

                            # Mettre à jour le message
                            await message.edit(embed=embed, view=view)

                            # Ajouter la vue persistante
                            self.bot.add_view(view, message_id=message_id)

                    except discord.NotFound:
                        self.logger.warning(f"Message d'embed {message_id} non trouvé lors du transfert de scène")
                        data['message_id'] = None
                        self.save_monitored_channels()

            self.logger.info(f"Scène {channel_id} transférée du MJ {old_mj_id} vers le MJ {new_mj_id}")

        except Exception as e:
            self.logger.error(f"Erreur lors du transfert de scène {channel_id}: {e}")

    @staticmethod
    def scene_check(interaction: discord.Interaction) -> bool:
        """Vérifie si l'utilisateur a le rôle MJ pour utiliser la commande scene."""
        return any(role.id == MJ_ROLE_ID for role in interaction.user.roles)

    @app_commands.command(name="scene", description="Commande Staff - Ajouter un salon à la surveillance")
    @app_commands.describe(lien_salon="Le lien du salon, fil ou post de forum à surveiller")
    @app_commands.check(scene_check)
    async def scene_monitoring(self, interaction: discord.Interaction, lien_salon: str):
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

        # Parser l'URL pour extraire l'ID du salon
        channel_id = self.parse_discord_url(lien_salon)
        if not channel_id:
            await interaction.followup.send(
                "❌ Lien Discord invalide. Veuillez fournir un lien valide vers un salon, fil ou post de forum.\n"
                "Format attendu: `https://discord.com/channels/GUILD_ID/CHANNEL_ID`",
                ephemeral=True
            )
            return

        # Récupérer l'objet salon/fil
        salon = self.bot.get_channel(channel_id)
        if not salon:
            await interaction.followup.send(
                "❌ Salon, fil ou post de forum non trouvé. Vérifiez que le lien est correct et que le bot a accès au salon.",
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

        # Si c'est un thread, vérifier s'il est fermé et le rouvrir si nécessaire
        thread_reopened = False
        if isinstance(salon, discord.Thread):
            if salon.archived or salon.locked:
                await interaction.followup.send(
                    f"🔄 Le fil **{salon.name}** est fermé/archivé. Tentative de réouverture...",
                    ephemeral=True
                )

                success, (was_archived, was_locked) = await self.ensure_thread_unarchived(salon)

                if success:
                    thread_reopened = True
                    status_msg = []
                    if was_archived:
                        status_msg.append("désarchivé")
                    if was_locked:
                        status_msg.append("déverrouillé")

                    success_embed = self.create_success_embed(
                        title="Thread rouvert",
                        description=f"Le fil **{salon.name}** a été {' et '.join(status_msg)} avec succès.",
                        channel=salon
                    )
                    await interaction.followup.send(embed=success_embed, ephemeral=True)
                else:
                    error_embed = self.create_error_embed(
                        title="Erreur de réouverture",
                        description=f"Impossible de rouvrir le fil **{salon.name}**. Vérifiez que le bot a les permissions nécessaires ou contactez un administrateur."
                    )
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

        # Créer l'embed de surveillance dans le salon de notification
        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            error_embed = self.create_error_embed(
                title="Salon de notification introuvable",
                description=f"Le salon de notification {NOTIFICATION_CHANNEL_ID} n'a pas été trouvé."
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
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
                'last_activity': datetime.now(),
                'last_alert_sent': None
            }
            self.save_monitored_channels()

            # Ajouter la vue persistante
            self.bot.add_view(view, message_id=embed_message.id)

            # Créer l'embed de succès
            success_embed = self.create_success_embed(
                title="Scène surveillée",
                description="La surveillance de cette scène a été activée avec succès.",
                channel=salon,
                mj_user=interaction.user,
                thread_reopened=thread_reopened
            )

            await interaction.followup.send(embed=success_embed, ephemeral=True)

            self.logger.info(f"MJ {interaction.user.display_name} ({interaction.user.id}) a ajouté le salon {salon.name} ({salon.id}) à la surveillance")

        except Exception as e:
            error_embed = self.create_error_embed(
                title="Erreur de surveillance",
                description="Une erreur est survenue lors de la création de l'embed de surveillance.",
                error_details=str(e)
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            self.logger.error(f"Erreur lors de la création de l'embed: {e}")

    @scene_monitoring.error
    async def scene_monitoring_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Gestionnaire d'erreur pour la commande scene."""
        try:
            if isinstance(error, app_commands.CheckFailure):
                error_embed = self.create_error_embed(
                    title="Accès refusé",
                    description="Cette commande est réservée au Staff (rôle MJ requis)."
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=error_embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                error_embed = self.create_error_embed(
                    title="Erreur de commande",
                    description="Une erreur est survenue lors de l'exécution de la commande.",
                    error_details=str(error)
                )
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=error_embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                self.logger.error(f"Erreur dans la commande scene: {error}")
        except discord.NotFound:
            # L'interaction a expiré, on ne peut plus répondre
            self.logger.error(f"Interaction expirée pour la commande scene: {error}")
        except Exception as e:
            self.logger.error(f"Erreur dans le gestionnaire d'erreur scene: {e}")

    @commands.command(name="create_scene")
    async def create_scene_admin(self, ctx: commands.Context, lien_salon: str, mj_id: int):
        """
        Commande admin pour créer une scène avec un MJ désigné.

        Usage: !create_scene <lien_salon> <mj_id>

        Args:
            lien_salon: Le lien du salon, fil ou post de forum à surveiller
            mj_id: L'ID du MJ qui sera responsable de la scène
        """
        # Vérifier les permissions MJ de l'utilisateur qui lance la commande
        if not self.is_mj(ctx.author):
            error_embed = self.create_error_embed(
                title="Accès refusé",
                description="Cette commande est réservée aux MJ."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Vérifier que le MJ désigné existe et a le rôle MJ
        designated_mj = self.bot.get_user(mj_id)
        if not designated_mj:
            error_embed = self.create_error_embed(
                title="Utilisateur introuvable",
                description=f"Utilisateur avec l'ID {mj_id} non trouvé."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Vérifier que le MJ désigné est membre du serveur et a le rôle MJ
        guild_member = ctx.guild.get_member(mj_id)
        if not guild_member:
            error_embed = self.create_error_embed(
                title="Membre introuvable",
                description=f"L'utilisateur {designated_mj.display_name} n'est pas membre de ce serveur."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        if not self.is_mj(guild_member):
            error_embed = self.create_error_embed(
                title="Permissions insuffisantes",
                description=f"L'utilisateur {designated_mj.display_name} n'a pas le rôle MJ."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Parser l'URL pour extraire l'ID du salon
        channel_id = self.parse_discord_url(lien_salon)
        if not channel_id:
            error_embed = self.create_error_embed(
                title="Lien invalide",
                description="Veuillez fournir un lien valide vers un salon, fil ou post de forum.\n\n**Format attendu :**\n`https://discord.com/channels/GUILD_ID/CHANNEL_ID`"
            )
            await ctx.send(embed=error_embed, delete_after=15)
            return

        # Récupérer l'objet salon/fil
        salon = self.bot.get_channel(channel_id)
        if not salon:
            error_embed = self.create_error_embed(
                title="Salon introuvable",
                description="Salon, fil ou post de forum non trouvé. Vérifiez que le lien est correct et que le bot a accès au salon."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Vérifier que c'est un type de salon supporté
        if not isinstance(salon, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            error_embed = self.create_error_embed(
                title="Type de salon non supporté",
                description="Ce type de salon n'est pas supporté. Seuls les salons texte, fils et forums sont supportés."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Vérifier si le salon est déjà surveillé
        if salon.id in self.monitored_channels:
            current_mj_id = self.monitored_channels[salon.id]['mj_user_id']
            current_mj = self.bot.get_user(current_mj_id)
            current_mj_name = current_mj.display_name if current_mj else f"ID {current_mj_id}"
            error_embed = self.create_error_embed(
                title="Salon déjà surveillé",
                description=f"Ce salon est déjà surveillé par **{current_mj_name}**."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Si c'est un thread, vérifier s'il est fermé et le rouvrir si nécessaire
        thread_reopened = False
        if isinstance(salon, discord.Thread):
            if salon.archived or salon.locked:
                status_msg = await ctx.send(f"🔄 Le fil **{salon.name}** est fermé/archivé. Tentative de réouverture...")

                success, (was_archived, was_locked) = await self.ensure_thread_unarchived(salon)

                if success:
                    thread_reopened = True
                    status_parts = []
                    if was_archived:
                        status_parts.append("désarchivé")
                    if was_locked:
                        status_parts.append("déverrouillé")

                    await status_msg.edit(content=f"✅ Le fil **{salon.name}** a été {' et '.join(status_parts)} avec succès.")
                else:
                    await status_msg.edit(
                        content=f"❌ Impossible de rouvrir le fil **{salon.name}**. "
                        f"Vérifiez que le bot a les permissions nécessaires ou contactez un administrateur."
                    )
                    return

        # Créer l'embed de surveillance dans le salon de notification
        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            await ctx.send(
                f"❌ Erreur: Le salon de notification {NOTIFICATION_CHANNEL_ID} n'a pas été trouvé.",
                delete_after=10
            )
            return

        # Créer l'embed initial avec le MJ désigné
        embed = self.create_scene_embed(salon, designated_mj)

        # Créer la vue avec le bouton de clôture
        view = SceneView(self, salon.id)

        # Envoyer l'embed dans le salon de notification
        try:
            embed_message = await notification_channel.send(embed=embed, view=view)

            # Ajouter le salon à la surveillance avec l'ID du message et le MJ désigné
            self.monitored_channels[salon.id] = {
                'mj_user_id': designated_mj.id,  # Utiliser l'ID du MJ désigné
                'message_id': embed_message.id,
                'participants': [],
                'last_activity': datetime.now()
            }
            self.save_monitored_channels()

            # Ajouter la vue persistante
            self.bot.add_view(view, message_id=embed_message.id)

            # Créer l'embed de succès pour l'admin
            success_embed = self.create_success_embed(
                title="Scène créée par l'administration",
                description=f"La surveillance de cette scène a été assignée à **{designated_mj.display_name}**.",
                channel=salon,
                mj_user=designated_mj,
                thread_reopened=thread_reopened
            )

            await ctx.send(embed=success_embed, delete_after=15)

            self.logger.info(f"Admin {ctx.author.display_name} ({ctx.author.id}) a créé une scène pour le MJ {designated_mj.display_name} ({designated_mj.id}) dans le salon {salon.name} ({salon.id})")

        except Exception as e:
            error_embed = self.create_error_embed(
                title="Erreur de création de scène",
                description="Une erreur est survenue lors de la création de l'embed de surveillance.",
                error_details=str(e)
            )
            await ctx.send(embed=error_embed, delete_after=10)
            self.logger.error(f"Erreur lors de la création de l'embed admin: {e}")

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

            # Mettre à jour last_activity avec timestamp précis
            current_time = datetime.now()
            data['last_activity'] = current_time
            self.save_monitored_channels()

            # Mettre à jour l'embed de surveillance
            await self.update_scene_embed(channel_id, message.author.id, message.author)

            # Récupérer le salon de notification
            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                self.logger.error(f"Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé")
                return

            # Vérifier si un ping peut être envoyé (respecter l'intervalle de 5 minutes)
            if self.can_send_ping(channel_id):
                # Créer un embed de ping en réponse à l'embed de surveillance
                if data['message_id']:
                    try:
                        embed_message = await notification_channel.fetch_message(data['message_id'])

                        # Créer l'embed de ping
                        ping_embed = self.create_ping_embed(mj, message.author, message.channel, channel_id)

                        # Envoyer l'embed de ping en réponse à l'embed de surveillance
                        ping_message = await embed_message.reply(content=mj.mention, embed=ping_embed)

                        # Mettre à jour le timestamp du dernier ping pour ce salon
                        self.update_last_ping_time(channel_id)

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
            else:
                # Log que le ping a été ignoré à cause du cooldown
                remaining_seconds = self.get_remaining_cooldown(channel_id)
                remaining_minutes = remaining_seconds // 60
                remaining_seconds_display = remaining_seconds % 60
                self.logger.debug(
                    f"Ping ignoré pour {message.channel.name} - Cooldown actif "
                    f"(reste {remaining_minutes}m {remaining_seconds_display}s)"
                )

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
