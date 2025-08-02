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
from datetime import datetime, timedelta, timezone
from typing import Dict, Set, List
import gspread
from google.oauth2.service_account import Credentials
import asyncio
from discord.ext import tasks
import re

# Configuration
NOTIFICATION_CHANNEL_ID = 1380704586016362626  # Salon de notification
MJ_ROLE_ID = 1018179623886000278  # ID du rôle MJ


def normalize_datetime(dt) -> datetime:
    """
    Normalise un datetime pour éviter les problèmes offset-naive vs offset-aware.
    Convertit tout en datetime naive (sans timezone) pour la cohérence.
    """
    if dt is None:
        return None

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return datetime.now()

    # Si le datetime a une timezone, le convertir en naive (heure locale)
    if dt.tzinfo is not None:
        # Convertir en heure locale et supprimer la timezone
        dt = dt.replace(tzinfo=None)

    return dt


def get_current_datetime() -> datetime:
    """Retourne le datetime actuel normalisé (naive)."""
    return datetime.now()


def safe_datetime_comparison(dt1, dt2) -> bool:
    """
    Compare deux datetime de manière sécurisée en les normalisant d'abord.
    Retourne True si dt1 < dt2.
    """
    try:
        dt1_norm = normalize_datetime(dt1)
        dt2_norm = normalize_datetime(dt2)

        if dt1_norm is None or dt2_norm is None:
            return False

        return dt1_norm < dt2_norm
    except Exception:
        return False


def safe_datetime_subtraction(dt1, dt2) -> timedelta:
    """
    Soustrait deux datetime de manière sécurisée en les normalisant d'abord.
    Retourne dt1 - dt2.
    """
    try:
        dt1_norm = normalize_datetime(dt1)
        dt2_norm = normalize_datetime(dt2)

        if dt1_norm is None or dt2_norm is None:
            return timedelta(0)

        return dt1_norm - dt2_norm
    except Exception:
        return timedelta(0)


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
        self.add_item(SceneTakeOverButton(cog, channel_id))
        self.add_item(SceneCloseButton(cog, channel_id))

class ChannelMonitor(commands.Cog):
    """Cog pour surveiller les salons et notifier les MJ."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.monitored_channels: Dict[int, dict] = {}  # {channel_id: {mj_user_id, message_id, participants, last_activity}}
        self.last_ping_times: Dict[int, dict] = {}  # {channel_id: {user_id: datetime, last_user_id: int}} - Suivi des derniers pings par salon et utilisateur
        self.ping_cooldown_minutes_same_user = 30  # Intervalle de 30 minutes si même utilisateur
        self.ping_cooldown_minutes_different_user = 5  # Intervalle de 5 minutes si utilisateur différent
        self.logger = logging.getLogger('channel_monitor')
        self.gspread_client = None
        self.sheet = None
        self.ping_sheet = None
        self.alert_sheet = None
        # Initialisation asynchrone pour éviter les délais au démarrage
        self.bot.loop.create_task(self.async_init())
        self._start_tasks()

    async def get_user_safely(self, user_id: int):
        """
        Récupère un utilisateur de manière robuste.
        Essaie d'abord le cache, puis fetch si nécessaire.
        """
        try:
            # Essayer d'abord le cache
            user = self.bot.get_user(user_id)
            if user:
                return user

            # Si pas dans le cache, essayer de le récupérer
            try:
                user = await self.bot.fetch_user(user_id)
                return user
            except (discord.NotFound, discord.HTTPException) as e:
                self.logger.warning(f"Impossible de récupérer l'utilisateur {user_id}: {e}")
                return None

        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'utilisateur {user_id}: {e}")
            return None

    async def async_init(self):
        """Initialisation asynchrone du cog."""
        await self.bot.wait_until_ready()
        self.setup_google_sheets()
        self.load_monitored_channels()

        # IMPORTANT: D'abord vérifier l'activité manquée pour mettre à jour les données
        await self.check_missed_activity()

        # Ensuite mettre à jour tous les embeds avec les données fraîches ET forcer les nouvelles vues
        await self.update_all_existing_embeds()

        # Enfin configurer les vues persistantes avec la nouvelle version
        await self.setup_persistent_views()

        # Nettoyer immédiatement les messages de ping expirés au démarrage
        await self.cleanup_ping_messages_immediate()
        # Nettoyer les anciennes alertes d'inactivité
        self.cleanup_old_alerts()

        self.logger.info("🎭 Initialisation du système de surveillance terminée")

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
                self.sheet.append_row(["channel_id", "mj_user_id", "message_id", "participant_1", "participant_2", "participant_3", "participant_4", "participant_5", "participant_6", "added_at", "last_activity", "last_alert_sent", "last_reminder_message_id"])

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
                                last_activity = normalize_datetime(datetime.fromisoformat(row[10]))
                            except ValueError:
                                last_activity = get_current_datetime()  # Fallback pour les anciennes données
                        else:
                            last_activity = get_current_datetime()  # Fallback pour les anciennes données

                        # Récupérer last_alert_sent (colonne 11, index 11)
                        last_alert_sent = None
                        if len(row) > 11 and row[11]:
                            try:
                                last_alert_sent = normalize_datetime(datetime.fromisoformat(row[11]))
                            except ValueError:
                                last_alert_sent = None

                        # Récupérer last_reminder_message_id (colonne 12, index 12)
                        last_reminder_message_id = None
                        if len(row) > 12 and row[12]:
                            try:
                                last_reminder_message_id = int(row[12])
                            except ValueError:
                                last_reminder_message_id = None

                        self.monitored_channels[channel_id] = {
                            'mj_user_id': mj_user_id,
                            'message_id': message_id,
                            'participants': participants,
                            'last_activity': last_activity,
                            'last_alert_sent': last_alert_sent,
                            'last_reminder_message_id': last_reminder_message_id
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
            self.sheet.append_row(["channel_id", "mj_user_id", "message_id", "participant_1", "participant_2", "participant_3", "participant_4", "participant_5", "participant_6", "added_at", "last_activity", "last_alert_sent", "last_reminder_message_id"])

            # Ajouter toutes les données
            current_time = get_current_datetime().isoformat()
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

                # Ajouter last_activity (normalisé)
                last_activity = normalize_datetime(data.get('last_activity', get_current_datetime()))
                row.append(last_activity.isoformat())

                # Ajouter last_alert_sent (normalisé)
                last_alert_sent = normalize_datetime(data.get('last_alert_sent'))
                row.append(last_alert_sent.isoformat() if last_alert_sent else "")

                # Ajouter last_reminder_message_id
                last_reminder_message_id = data.get('last_reminder_message_id')
                row.append(str(last_reminder_message_id) if last_reminder_message_id else "")

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

            last_alert_sent = normalize_datetime(data.get('last_alert_sent'))
            if not last_alert_sent:
                return False

            # Vérifier si l'alerte a été envoyée aujourd'hui
            today = get_current_datetime().date()
            alert_date = last_alert_sent.date()

            return alert_date == today
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification d'alerte pour le salon {channel_id}: {e}")
            return False

    def should_send_new_alert(self, channel_id: int) -> bool:
        """Vérifie si un nouveau message d'alerte doit être envoyé (renouvellement quotidien)."""
        try:
            data = self.monitored_channels.get(channel_id)
            if not data:
                return True

            last_alert_sent = data.get('last_alert_sent')
            if not last_alert_sent:
                return True

            # Vérifier si plus de 24h se sont écoulées depuis la dernière alerte
            current_time = get_current_datetime()
            time_since_last_alert = safe_datetime_subtraction(current_time, last_alert_sent)

            return time_since_last_alert.total_seconds() >= 86400  # 24h en secondes
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification de renouvellement d'alerte pour le salon {channel_id}: {e}")
            return True

    def record_alert_sent(self, channel_id: int, mj_user_id: int, message_id: int = None):
        """Enregistre qu'une alerte d'inactivité a été envoyée pour ce salon."""
        try:
            current_time = get_current_datetime()

            # Mettre à jour les données en mémoire
            if channel_id in self.monitored_channels:
                self.monitored_channels[channel_id]['last_alert_sent'] = current_time
                # Enregistrer l'ID du dernier message de rappel pour pouvoir le supprimer plus tard
                if message_id:
                    self.monitored_channels[channel_id]['last_reminder_message_id'] = message_id
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

    async def cleanup_old_reminder_message(self, channel_id: int, notification_channel):
        """Supprime l'ancien message de rappel s'il existe."""
        try:
            data = self.monitored_channels.get(channel_id)
            if not data:
                return

            old_message_id = data.get('last_reminder_message_id')
            if old_message_id:
                try:
                    old_message = await notification_channel.fetch_message(old_message_id)
                    await old_message.delete()
                    self.logger.info(f"Ancien message de rappel supprimé: {old_message_id}")

                    # Supprimer aussi de la feuille ping_sheet si présent
                    if self.ping_sheet:
                        try:
                            all_values = self.ping_sheet.get_all_values()
                            for idx, row in enumerate(all_values[1:], start=2):
                                if len(row) >= 1 and row[0] == str(old_message_id):
                                    self.ping_sheet.delete_rows(idx)
                                    break
                        except Exception as e:
                            self.logger.error(f"Erreur lors de la suppression de l'ancien ping de la base: {e}")

                except discord.NotFound:
                    self.logger.debug(f"Ancien message de rappel {old_message_id} déjà supprimé")
                except Exception as e:
                    self.logger.error(f"Erreur lors de la suppression de l'ancien message de rappel {old_message_id}: {e}")

                # Nettoyer l'ID du message dans les données
                data['last_reminder_message_id'] = None
                self.save_monitored_channels()

        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage de l'ancien message de rappel pour le salon {channel_id}: {e}")

    def cleanup_old_alerts(self):
        """Nettoie les anciennes entrées d'alertes (plus de 30 jours)."""
        try:
            if not self.alert_sheet:
                return

            current_time = get_current_datetime()
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
                        alert_timestamp = normalize_datetime(datetime.fromisoformat(row[3]))
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

            current_time = get_current_datetime()
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
                        message_time = normalize_datetime(datetime.fromisoformat(timestamp))
                        time_diff = safe_datetime_subtraction(current_time, message_time)
                        if time_diff.total_seconds() > 86400:  # 24h en secondes
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
            current_hour = get_current_datetime().hour
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

            current_time = get_current_datetime()
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
                        message_time = normalize_datetime(datetime.fromisoformat(timestamp))
                        time_diff = safe_datetime_subtraction(current_time, message_time)
                        if time_diff.total_seconds() > 86400:  # 24h en secondes
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
        """Met à jour tous les embeds de surveillance existants avec récupération de l'activité récente."""
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

                    # Si le MJ n'est pas dans le cache, essayer de le récupérer
                    if not mj_user:
                        try:
                            mj_user = await self.bot.fetch_user(data['mj_user_id'])
                        except (discord.NotFound, discord.HTTPException):
                            pass

                    if not channel or not mj_user:
                        self.logger.warning(f"Salon {channel_id} ou MJ {data['mj_user_id']} non trouvé")
                        failed_count += 1
                        continue

                    # NOUVEAU: Forcer la récupération de l'activité récente avant de mettre à jour l'embed
                    await self.force_refresh_scene_data(channel_id)

                    # Récupérer l'utilisateur de la dernière action pour l'affichage correct
                    last_action_user = None
                    last_action_user_id = data.get('last_action_user_id')
                    if last_action_user_id:
                        last_action_user = await self.get_user_safely(last_action_user_id)

                    # Créer le nouvel embed avec le format amélioré (version asynchrone)
                    embed = await self.create_scene_embed_async(channel, mj_user, data.get('participants', []), last_action_user)

                    # Créer la NOUVELLE vue avec seulement 2 boutons (sans le bouton Actualiser)
                    view = SceneView(self, channel_id)

                    # FORCER la mise à jour du message avec la nouvelle vue
                    await message.edit(embed=embed, view=view)

                    # Log pour confirmer la mise à jour
                    self.logger.info(f"🔄 Embed et vue mis à jour pour le salon {channel_id} - {len(view.children)} boutons")

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

                    # Normaliser le datetime
                    last_recorded_activity = normalize_datetime(last_recorded_activity)
                    if not last_recorded_activity:
                        self.logger.warning(f"Impossible de normaliser la date pour le salon {channel_id}")
                        continue

                    # Récupérer les messages récents depuis la dernière activité
                    try:
                        # Limiter la vérification aux 7 derniers jours maximum pour éviter les surcharges
                        max_check_period = get_current_datetime() - timedelta(days=7)
                        # Utiliser max avec des datetime normalisés
                        check_after = max(last_recorded_activity, max_check_period)

                        # Limiter à 200 messages pour éviter les surcharges
                        messages = []
                        valid_messages = []
                        message_count = 0

                        async for message in channel.history(limit=200, after=check_after):
                            messages.append(message)
                            message_count += 1

                            # Identifier l'utilisateur réel pour chaque message
                            real_user = None

                            if message.author.bot:
                                # Vérifier si c'est un message Tupperbot/webhook
                                if message.webhook_id:
                                    # Utiliser la méthode améliorée pour extraire l'utilisateur réel
                                    real_user = await self.extract_real_user_from_tupperbot(message)
                                    if real_user:
                                        self.logger.info(f"Message Tupperbot manqué détecté de {real_user.display_name} dans le salon {channel_id}")
                            else:
                                # Message d'utilisateur normal
                                real_user = message.author

                            # Ajouter seulement les messages avec un utilisateur réel identifié
                            if real_user:
                                valid_messages.append((message, real_user))

                        if message_count >= 200:
                            self.logger.warning(f"Limite de 200 messages atteinte pour le salon {channel_id}, certains messages peuvent être manqués")

                        if not valid_messages:
                            self.logger.debug(f"Aucune nouvelle activité trouvée pour le salon {channel_id}")
                            continue

                        # Trier les messages par timestamp (plus récent en dernier)
                        valid_messages.sort(key=lambda m: m[0].created_at)

                        # Traiter chaque message manqué
                        new_participants = set(data.get('participants', []))
                        last_action_user = None

                        for message, real_user in valid_messages:
                            # Ajouter l'utilisateur réel aux participants s'il n'y est pas déjà
                            if real_user.id not in new_participants:
                                new_participants.add(real_user.id)
                                self.logger.info(f"Nouveau participant détecté pendant la déconnexion: {real_user.display_name} dans le salon {channel_id}")

                            last_action_user = real_user

                            # Mettre à jour la dernière activité avec le timestamp du message (normalisé)
                            data['last_activity'] = normalize_datetime(message.created_at)

                        # Mettre à jour la liste des participants
                        data['participants'] = list(new_participants)

                        # Sauvegarder l'ID de l'utilisateur réel de la dernière action
                        if last_action_user:
                            data['last_action_user_id'] = last_action_user.id

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



    async def force_refresh_scene_data(self, channel_id: int):
        """
        Force la récupération des données d'activité récente pour une scène spécifique.
        Utilisé lors de la mise à jour des embeds existants.
        """
        if channel_id not in self.monitored_channels:
            return

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return

            data = self.monitored_channels[channel_id]
            last_recorded_activity = data.get('last_activity')

            # Si pas de dernière activité enregistrée, utiliser la date de création du salon
            if not last_recorded_activity:
                if hasattr(channel, 'created_at'):
                    last_recorded_activity = normalize_datetime(channel.created_at)
                else:
                    last_recorded_activity = get_current_datetime() - timedelta(days=7)
            else:
                last_recorded_activity = normalize_datetime(last_recorded_activity)

            # Limiter la vérification aux 7 derniers jours maximum
            max_check_period = get_current_datetime() - timedelta(days=7)
            check_after = max(last_recorded_activity, max_check_period)

            try:
                # Récupérer les messages récents avec la même logique que check_missed_activity
                valid_messages = []
                message_count = 0

                async for message in channel.history(limit=200, after=check_after):
                    message_count += 1

                    # Identifier l'utilisateur réel pour chaque message
                    real_user = None

                    if message.author.bot:
                        # Vérifier si c'est un message Tupperbot/webhook
                        if message.webhook_id:
                            real_user = await self.extract_real_user_from_tupperbot(message)
                            if real_user:
                                self.logger.info(f"Message Tupperbot détecté lors de la mise à jour de {real_user.display_name} dans le salon {channel_id}")
                    else:
                        # Message d'utilisateur normal
                        real_user = message.author

                    # Ajouter seulement les messages avec un utilisateur réel identifié
                    if real_user:
                        valid_messages.append((message, real_user))

                if valid_messages:
                    # Trier les messages par timestamp (plus récent en dernier)
                    valid_messages.sort(key=lambda m: m[0].created_at)

                    # Mettre à jour avec le message le plus récent
                    latest_message, latest_real_user = valid_messages[-1]
                    data['last_activity'] = normalize_datetime(latest_message.created_at)
                    data['last_action_user_id'] = latest_real_user.id

                    # Mettre à jour les participants
                    new_participants = set(data.get('participants', []))
                    for message, real_user in valid_messages:
                        if real_user.id not in new_participants:
                            new_participants.add(real_user.id)

                    data['participants'] = list(new_participants)
                    self.save_monitored_channels()

                    self.logger.info(f"Données de scène {channel_id} mises à jour avec l'activité récente de {latest_real_user.display_name}")

            except discord.Forbidden:
                self.logger.warning(f"Permissions insuffisantes pour lire l'historique du salon {channel_id}")
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération des messages pour la mise à jour de {channel_id}: {e}")

        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour forcée des données de scène {channel_id}: {e}")

    @tasks.loop(hours=6)
    async def check_inactive_scenes(self):
        """Vérifie les scènes inactives depuis une semaine et ping le MJ. Exécution toutes les 6h pour plus de fiabilité."""
        try:
            if not self.monitored_channels:
                return

            current_time = get_current_datetime()
            week_ago_timestamp = current_time.timestamp() - (7 * 24 * 60 * 60)  # 7 jours en secondes

            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                self.logger.error(f"Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé")
                return

            for channel_id, data in self.monitored_channels.items():
                try:
                    last_activity = normalize_datetime(data.get('last_activity'))
                    if not last_activity:
                        continue

                    # Vérifier si la scène est inactive depuis une semaine
                    if last_activity.timestamp() < week_ago_timestamp:
                        # Vérifier si un nouveau message d'alerte doit être envoyé (renouvellement quotidien)
                        if not self.should_send_new_alert(channel_id):
                            self.logger.debug(f"Alerte récente déjà envoyée pour le salon {channel_id}, attente du renouvellement")
                            continue

                        mj_id = data['mj_user_id']
                        # Utiliser la fonction robuste pour récupérer l'utilisateur
                        mj = await self.get_user_safely(mj_id)

                        if not mj:
                            self.logger.warning(f"MJ avec ID {mj_id} non trouvé pour le salon {channel_id}")
                            continue

                        # Récupérer les informations du salon
                        channel = self.bot.get_channel(channel_id)
                        if not channel:
                            self.logger.warning(f"Salon {channel_id} non trouvé")
                            continue

                        channel_info = self.get_channel_info(channel)

                        # Supprimer l'ancien message de rappel s'il existe
                        await self.cleanup_old_reminder_message(channel_id, notification_channel)

                        # Envoyer le rappel d'inactivité (MP avec fallback salon)
                        time_diff = safe_datetime_subtraction(current_time, last_activity)
                        days_inactive = int(time_diff.days)
                        reminder_sent = False
                        reminder_message = None

                        if data['message_id']:
                            try:
                                embed_message = await notification_channel.fetch_message(data['message_id'])
                                reminder_sent, reminder_message = await self.send_reminder_notification(
                                    mj, channel, channel_id, days_inactive,
                                    notification_channel, embed_message
                                )

                            except discord.NotFound:
                                self.logger.warning(f"Message d'embed {data['message_id']} non trouvé pour le rappel, envoi direct")
                                # Fallback : envoyer directement sur le salon
                                try:
                                    fallback_embed = self.create_reminder_embed(mj, channel, channel_id, days_inactive, is_dm=False)
                                    reminder_message = await notification_channel.send(content=mj.mention, embed=fallback_embed)
                                    reminder_sent = True
                                    self.logger.info(f"Ping de rappel direct envoyé pour scène inactive: {channel_info} ({days_inactive} jours)")

                                    # Ajouter à Google Sheets pour suppression
                                    if self.ping_sheet:
                                        try:
                                            self.ping_sheet.append_row([
                                                str(reminder_message.id),
                                                str(notification_channel.id),
                                                datetime.now().isoformat()
                                            ])
                                        except Exception as e:
                                            self.logger.error(f"Erreur lors de l'ajout du rappel direct à Google Sheets: {e}")
                                except Exception as e:
                                    self.logger.error(f"Erreur lors de l'envoi du rappel direct: {e}")
                        else:
                            # Envoyer l'embed directement si pas d'embed de surveillance
                            try:
                                fallback_embed = self.create_reminder_embed(mj, channel, channel_id, days_inactive, is_dm=False)
                                reminder_message = await notification_channel.send(content=mj.mention, embed=fallback_embed)
                                reminder_sent = True
                                self.logger.info(f"Ping de rappel direct envoyé pour scène inactive: {channel_info} ({days_inactive} jours)")

                                # Ajouter à Google Sheets pour suppression
                                if self.ping_sheet:
                                    try:
                                        self.ping_sheet.append_row([
                                            str(reminder_message.id),
                                            str(notification_channel.id),
                                            datetime.now().isoformat()
                                        ])
                                    except Exception as e:
                                        self.logger.error(f"Erreur lors de l'ajout du rappel direct à Google Sheets: {e}")
                            except Exception as e:
                                self.logger.error(f"Erreur lors de l'envoi du rappel direct: {e}")

                        # Enregistrer que l'alerte a été envoyée avec l'ID du message (seulement si c'était un message public)
                        if reminder_sent and reminder_message and hasattr(reminder_message, 'guild'):
                            self.record_alert_sent(channel_id, mj_id, reminder_message.id)

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

    def can_send_ping(self, channel_id: int, user_id: int) -> bool:
        """
        Vérifie si un ping peut être envoyé pour un salon donné en respectant l'intervalle de cooldown.
        - 30 minutes si c'est le même utilisateur qui écrit
        - 5 minutes si c'est un utilisateur différent

        Args:
            channel_id: ID du salon à vérifier
            user_id: ID de l'utilisateur qui écrit

        Returns:
            bool: True si un ping peut être envoyé, False sinon
        """
        current_time = datetime.now()

        # Si aucun ping n'a été envoyé pour ce salon, on peut envoyer
        if channel_id not in self.last_ping_times:
            return True

        ping_data = self.last_ping_times[channel_id]
        last_user_id = ping_data.get('last_user_id')
        last_ping_time = ping_data.get('last_ping_time')

        # Si pas de données de ping précédent, on peut envoyer
        if not last_ping_time:
            return True

        # Déterminer l'intervalle de cooldown selon l'utilisateur
        if last_user_id == user_id:
            # Même utilisateur : 30 minutes
            cooldown_seconds = self.ping_cooldown_minutes_same_user * 60
        else:
            # Utilisateur différent : 5 minutes
            cooldown_seconds = self.ping_cooldown_minutes_different_user * 60

        # Vérifier si assez de temps s'est écoulé depuis le dernier ping
        time_since_last_ping = current_time - last_ping_time
        return time_since_last_ping.total_seconds() >= cooldown_seconds

    def update_last_ping_time(self, channel_id: int, user_id: int):
        """
        Met à jour le timestamp du dernier ping pour un salon donné avec l'utilisateur.

        Args:
            channel_id: ID du salon pour lequel mettre à jour le timestamp
            user_id: ID de l'utilisateur qui a déclenché le ping
        """
        self.last_ping_times[channel_id] = {
            'last_ping_time': datetime.now(),
            'last_user_id': user_id
        }
        self.logger.debug(f"Timestamp de dernier ping mis à jour pour le salon {channel_id} (utilisateur {user_id})")

    def get_remaining_cooldown(self, channel_id: int, user_id: int) -> int:
        """
        Retourne le temps restant avant de pouvoir envoyer un nouveau ping (en secondes).

        Args:
            channel_id: ID du salon à vérifier
            user_id: ID de l'utilisateur qui écrit

        Returns:
            int: Nombre de secondes restantes, 0 si un ping peut être envoyé
        """
        if self.can_send_ping(channel_id, user_id):
            return 0

        current_time = datetime.now()
        ping_data = self.last_ping_times[channel_id]
        last_ping_time = ping_data.get('last_ping_time')
        last_user_id = ping_data.get('last_user_id')

        if not last_ping_time:
            return 0

        # Déterminer l'intervalle de cooldown selon l'utilisateur
        if last_user_id == user_id:
            cooldown_seconds = self.ping_cooldown_minutes_same_user * 60
        else:
            cooldown_seconds = self.ping_cooldown_minutes_different_user * 60

        time_since_last_ping = current_time - last_ping_time
        return max(0, cooldown_seconds - int(time_since_last_ping.total_seconds()))

    def format_time_since_activity(self, last_activity: datetime) -> str:
        """Formate le temps écoulé depuis la dernière activité."""
        if not last_activity:
            return "Jamais"

        # Utiliser les fonctions utilitaires pour une comparaison sécurisée
        now = get_current_datetime()
        last_activity_norm = normalize_datetime(last_activity)

        time_diff = safe_datetime_subtraction(now, last_activity_norm)

        if time_diff.days > 0:
            return f"il y a {time_diff.days} jour{'s' if time_diff.days > 1 else ''}"
        elif time_diff.seconds >= 3600:
            hours = time_diff.seconds // 3600
            return f"il y a {hours} heure{'s' if hours > 1 else ''}"
        elif time_diff.seconds >= 60:
            minutes = time_diff.seconds // 60
            return f"il y a {minutes} minute{'s' if minutes > 1 else ''}"
        else:
            return "à l'instant"

    def create_scene_embed(self, channel, mj_user, participants: List[int] = None, last_action_user=None) -> discord.Embed:
        """Crée l'embed de surveillance d'une scène."""
        if participants is None:
            participants = []

        # Récupérer la dernière activité depuis les données surveillées
        channel_data = self.monitored_channels.get(channel.id, {})
        last_activity = normalize_datetime(channel_data.get('last_activity'))

        # Si pas de dernière activité enregistrée, utiliser la date de création du salon
        if not last_activity:
            if hasattr(channel, 'created_at'):
                last_activity = normalize_datetime(channel.created_at)
            else:
                last_activity = get_current_datetime()

        embed = discord.Embed(
            title="🎭 Scène surveillée",
            color=0x3498db,
            timestamp=last_activity
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

        # Participants - utilisation synchrone pour éviter de bloquer l'embed
        if participants:
            participant_names = []
            guild = channel.guild if hasattr(channel, 'guild') else None

            for user_id in participants:
                # Essayer d'abord le cache du bot
                user = self.bot.get_user(user_id)
                if user:
                    participant_names.append(user.display_name)
                elif guild:
                    # Essayer le cache du serveur
                    member = guild.get_member(user_id)
                    if member:
                        participant_names.append(member.display_name)
                    else:
                        participant_names.append(f"Utilisateur {user_id}")
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

        # Ajouter les informations de dernière activité avec date et temps écoulé
        if last_action_user:
            time_since = self.format_time_since_activity(last_activity)
            activity_date = last_activity.strftime("%d/%m/%Y à %H:%M")
            embed.add_field(
                name="⚡ Dernière activité",
                value=f"{last_action_user.display_name}\n📅 {activity_date}\n⏰ {time_since}",
                inline=True
            )
        elif channel_data.get('last_action_user_id'):
            # Récupérer l'utilisateur de la dernière action depuis l'ID stocké
            last_user_id = channel_data['last_action_user_id']
            last_user = self.bot.get_user(last_user_id)
            time_since = self.format_time_since_activity(last_activity)
            activity_date = last_activity.strftime("%d/%m/%Y à %H:%M")

            if last_user:
                embed.add_field(
                    name="⚡ Dernière activité",
                    value=f"{last_user.display_name}\n📅 {activity_date}\n⏰ {time_since}",
                    inline=True
                )
            else:
                # Essayer de récupérer le nom d'utilisateur depuis l'ID
                embed.add_field(
                    name="⚡ Dernière activité",
                    value=f"Utilisateur {last_user_id}\n📅 {activity_date}\n⏰ {time_since}",
                    inline=True
                )
        else:
            # Même s'il n'y a pas d'activité récente, afficher la date de création du salon
            time_since = self.format_time_since_activity(last_activity)
            activity_date = last_activity.strftime("%d/%m/%Y à %H:%M")
            embed.add_field(
                name="⚡ Dernière activité",
                value=f"Création du salon\n📅 {activity_date}\n⏰ {time_since}",
                inline=True
            )

        # Supprimer le footer "système de surveillance de scène" car l'info est maintenant dans le champ activité
        # Le timestamp de l'embed indique déjà la dernière activité
        return embed

    def create_ping_embed(self, mj_user, action_user, channel, channel_id: int, is_dm: bool = False) -> discord.Embed:
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

        # Adapter le contenu selon si c'est un MP ou un message public
        if is_dm:
            embed.add_field(
                name="🎯 Notification",
                value="Vous surveillez cette scène",
                inline=True
            )
        else:
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

        # Ajouter un lien direct vers le salon pour les MP
        if is_dm:
            embed.add_field(
                name="🔗 Accès rapide",
                value=f"[Aller au salon]({channel.jump_url})",
                inline=False
            )

        footer_text = "Système de surveillance des scènes"
        if not is_dm:
            footer_text += " • Ce message sera supprimé dans 24h"

        embed.set_footer(text=footer_text)

        return embed

    async def send_ping_notification(self, mj_user, action_user, channel, channel_id: int, notification_channel, embed_message) -> bool:
        """
        Envoie une notification de ping, d'abord en MP puis en fallback sur le salon.

        Args:
            mj_user: L'utilisateur MJ à notifier
            action_user: L'utilisateur qui a déclenché l'activité
            channel: Le salon surveillé
            channel_id: ID du salon surveillé
            notification_channel: Le salon de notification (fallback)
            embed_message: Le message d'embed de surveillance

        Returns:
            bool: True si la notification a été envoyée avec succès
        """
        ping_sent = False
        ping_message = None

        # Tentative d'envoi en message privé
        try:
            dm_embed = self.create_ping_embed(mj_user, action_user, channel, channel_id, is_dm=True)
            ping_message = await mj_user.send(embed=dm_embed)
            ping_sent = True
            self.logger.info(f"Ping envoyé en MP à {mj_user.display_name} pour activité de {action_user.display_name} dans {channel.name}")

        except discord.Forbidden:
            # MP fermés ou bloqués, fallback vers le salon
            self.logger.debug(f"MP fermés pour {mj_user.display_name}, fallback vers le salon")
            try:
                public_embed = self.create_ping_embed(mj_user, action_user, channel, channel_id, is_dm=False)
                ping_message = await embed_message.reply(content=mj_user.mention, embed=public_embed)
                ping_sent = True
                self.logger.info(f"Ping envoyé sur le salon (fallback) pour {mj_user.display_name} - activité de {action_user.display_name} dans {channel.name}")

                # Ajouter le message de ping public à Google Sheets pour suppression automatique
                if self.ping_sheet:
                    try:
                        self.ping_sheet.append_row([
                            str(ping_message.id),
                            str(notification_channel.id),
                            datetime.now().isoformat()
                        ])
                    except Exception as e:
                        self.logger.error(f"Erreur lors de l'ajout du ping fallback à Google Sheets: {e}")

            except Exception as e:
                self.logger.error(f"Erreur lors de l'envoi du ping fallback: {e}")

        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi du ping en MP: {e}")

        return ping_sent

    async def send_reminder_notification(self, mj_user, channel, channel_id: int, days_inactive: int, notification_channel, embed_message) -> bool:
        """
        Envoie une notification de rappel d'inactivité, d'abord en MP puis en fallback sur le salon.

        Args:
            mj_user: L'utilisateur MJ à notifier
            channel: Le salon surveillé
            channel_id: ID du salon surveillé
            days_inactive: Nombre de jours d'inactivité
            notification_channel: Le salon de notification (fallback)
            embed_message: Le message d'embed de surveillance

        Returns:
            bool: True si la notification a été envoyée avec succès
        """
        reminder_sent = False
        reminder_message = None

        # Tentative d'envoi en message privé
        try:
            dm_embed = self.create_reminder_embed(mj_user, channel, channel_id, days_inactive, is_dm=True)
            reminder_message = await mj_user.send(embed=dm_embed)
            reminder_sent = True
            self.logger.info(f"Rappel d'inactivité envoyé en MP à {mj_user.display_name} pour {channel.name} ({days_inactive} jours)")

        except discord.Forbidden:
            # MP fermés ou bloqués, fallback vers le salon
            self.logger.debug(f"MP fermés pour {mj_user.display_name}, fallback vers le salon pour rappel")
            try:
                public_embed = self.create_reminder_embed(mj_user, channel, channel_id, days_inactive, is_dm=False)
                reminder_message = await embed_message.reply(content=mj_user.mention, embed=public_embed)
                reminder_sent = True
                self.logger.info(f"Rappel d'inactivité envoyé sur le salon (fallback) pour {mj_user.display_name} - {channel.name} ({days_inactive} jours)")

                # Ajouter le message de rappel public à Google Sheets pour suppression automatique
                if self.ping_sheet:
                    try:
                        self.ping_sheet.append_row([
                            str(reminder_message.id),
                            str(notification_channel.id),
                            datetime.now().isoformat()
                        ])
                    except Exception as e:
                        self.logger.error(f"Erreur lors de l'ajout du rappel fallback à Google Sheets: {e}")

            except Exception as e:
                self.logger.error(f"Erreur lors de l'envoi du rappel fallback: {e}")

        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi du rappel en MP: {e}")

        return reminder_sent, reminder_message

    def create_reminder_embed(self, mj_user, channel, channel_id: int, days_inactive: int, is_dm: bool = False) -> discord.Embed:
        """Crée un embed pour les rappels de scènes inactives."""
        channel_details = self.get_detailed_channel_info(channel)

        embed = discord.Embed(
            title="⏰ Rappel de scène inactive",
            color=0xe74c3c,  # Rouge pour attirer l'attention
            timestamp=get_current_datetime()
        )

        # Adapter le contenu selon si c'est un MP ou un message public
        if is_dm:
            embed.add_field(
                name="🎯 Notification",
                value="Vous surveillez cette scène",
                inline=True
            )
        else:
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

        # Ajouter un lien direct vers le salon pour les MP
        if is_dm:
            embed.add_field(
                name="🔗 Accès rapide",
                value=f"[Aller au salon]({channel.jump_url})",
                inline=False
            )

        embed.add_field(
            name="💡 Action recommandée",
            value="Pensez à vérifier si cette scène nécessite votre attention !",
            inline=False
        )

        footer_text = "Système de surveillance des scènes"
        if not is_dm:
            footer_text += " • Ce message sera supprimé dans 24h"

        embed.set_footer(text=footer_text)

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

                # Si le MJ n'est pas dans le cache, essayer de le récupérer
                if not mj_user:
                    try:
                        mj_user = await self.bot.fetch_user(data['mj_user_id'])
                    except (discord.NotFound, discord.HTTPException):
                        pass

                if not channel or not mj_user:
                    return

                # Créer le nouvel embed avec les informations à jour (version asynchrone)
                embed = await self.create_scene_embed_async(channel, mj_user, data['participants'], action_user)

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

                        # Si le nouveau MJ n'est pas dans le cache, essayer de le récupérer
                        if not new_mj_user:
                            try:
                                new_mj_user = await self.bot.fetch_user(new_mj_id)
                            except (discord.NotFound, discord.HTTPException):
                                pass

                        if channel and new_mj_user:
                            # Créer le nouvel embed avec le nouveau MJ (version asynchrone)
                            embed = await self.create_scene_embed_async(channel, new_mj_user, data['participants'])

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

    async def find_user_by_identifier(self, ctx: commands.Context, identifier: str):
        """
        Trouve un utilisateur par son ID, nom d'utilisateur ou mention.

        Args:
            ctx: Le contexte de la commande
            identifier: L'identifiant de l'utilisateur (ID, nom, mention)

        Returns:
            discord.Member ou None si non trouvé
        """
        # Nettoyer l'identifiant (supprimer les espaces)
        identifier = identifier.strip()

        # Cas 1: Mention d'utilisateur (<@123456789> ou <@!123456789>)
        mention_match = re.match(r'<@!?(\d+)>', identifier)
        if mention_match:
            user_id = int(mention_match.group(1))
            # Essayer d'abord le cache
            member = ctx.guild.get_member(user_id)
            if member:
                return member
            # Puis fetch depuis Discord
            try:
                return await ctx.guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                return None

        # Cas 2: ID numérique
        if identifier.isdigit():
            user_id = int(identifier)
            # Essayer d'abord le cache
            member = ctx.guild.get_member(user_id)
            if member:
                return member
            # Puis fetch depuis Discord
            try:
                return await ctx.guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                return None

        # Cas 3: Nom d'utilisateur (recherche dans les membres du serveur)
        # Si le cache n'est pas complet, on peut essayer de chercher par chunks
        # Mais d'abord, essayons avec le cache existant

        # Recherche exacte par display_name
        for member in ctx.guild.members:
            if member.display_name.lower() == identifier.lower():
                return member

        # Recherche exacte par nom d'utilisateur global
        for member in ctx.guild.members:
            if member.name.lower() == identifier.lower():
                return member

        # Si pas trouvé dans le cache, essayer de chercher avec une approche différente
        # Utiliser la recherche par nom avec l'API Discord si possible
        try:
            # Essayer de chercher parmi tous les membres (limité pour éviter la lenteur)
            async for member in ctx.guild.fetch_members(limit=1000):
                if (member.display_name.lower() == identifier.lower() or
                    member.name.lower() == identifier.lower()):
                    return member
        except discord.HTTPException:
            # Si la recherche échoue, continuer avec la recherche partielle dans le cache
            pass

        # Recherche partielle par display_name (si pas de correspondance exacte)
        for member in ctx.guild.members:
            if identifier.lower() in member.display_name.lower():
                return member

        # Recherche partielle par nom d'utilisateur global
        for member in ctx.guild.members:
            if identifier.lower() in member.name.lower():
                return member

        return None

    async def get_user_info_robust(self, user_id: int, guild: discord.Guild = None):
        """
        Récupère les informations d'un utilisateur de manière robuste.

        Args:
            user_id: L'ID de l'utilisateur
            guild: Le serveur Discord (optionnel)

        Returns:
            tuple: (user_object, display_name) ou (None, f"Utilisateur {user_id}")
        """
        # Essayer d'abord le cache du bot
        user = self.bot.get_user(user_id)
        if user:
            return user, user.display_name

        # Si on a un serveur, essayer de récupérer le membre
        if guild:
            member = guild.get_member(user_id)
            if member:
                return member, member.display_name

            # Essayer de fetch le membre depuis Discord
            try:
                member = await guild.fetch_member(user_id)
                return member, member.display_name
            except (discord.NotFound, discord.HTTPException):
                pass

        # Essayer de fetch l'utilisateur global
        try:
            user = await self.bot.fetch_user(user_id)
            return user, user.display_name
        except (discord.NotFound, discord.HTTPException):
            pass

        # Si tout échoue, retourner un nom par défaut
        return None, f"Utilisateur {user_id}"

    async def create_scene_embed_async(self, channel, mj_user, participants: List[int] = None, last_action_user=None) -> discord.Embed:
        """Version asynchrone de create_scene_embed avec récupération robuste des participants."""
        if participants is None:
            participants = []

        # Récupérer la dernière activité depuis les données surveillées
        channel_data = self.monitored_channels.get(channel.id, {})
        last_activity = normalize_datetime(channel_data.get('last_activity'))

        # Si pas de dernière activité enregistrée, utiliser la date de création du salon
        if not last_activity:
            if hasattr(channel, 'created_at'):
                last_activity = normalize_datetime(channel.created_at)
            else:
                last_activity = get_current_datetime()
        
        embed = discord.Embed(
            title="🎭 Scène surveillée",
            color=0x3498db,
            timestamp=last_activity
        )

        # Informations du salon
        channel_details = self.get_detailed_channel_info(channel)
        salon_info = f"**{channel_details['name']}**"
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
            value=f"**{mj_user.display_name}**",
            inline=True
        )

        # Participants - version asynchrone avec récupération robuste
        if participants:
            participant_names = []
            guild = channel.guild if hasattr(channel, 'guild') else None

            for user_id in participants:
                user_obj, display_name = await self.get_user_info_robust(user_id, guild)
                participant_names.append(display_name)

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

        # Ajouter les informations de dernière activité avec date et temps écoulé
        if last_action_user:
            time_since = self.format_time_since_activity(last_activity)
            activity_date = last_activity.strftime("%d/%m/%Y à %H:%M")
            embed.add_field(
                name="⚡ Dernière activité",
                value=f"{last_action_user.display_name}\n📅 {activity_date}\n⏰ {time_since}",
                inline=True
            )
        elif channel_data.get('last_action_user_id'):
            # Récupérer l'utilisateur de la dernière action depuis l'ID stocké
            last_user_id = channel_data['last_action_user_id']
            time_since = self.format_time_since_activity(last_activity)
            activity_date = last_activity.strftime("%d/%m/%Y à %H:%M")

            try:
                last_user = await self.bot.fetch_user(last_user_id)
                embed.add_field(
                    name="⚡ Dernière activité",
                    value=f"{last_user.display_name}\n📅 {activity_date}\n⏰ {time_since}",
                    inline=True
                )
            except (discord.NotFound, discord.HTTPException):
                embed.add_field(
                    name="⚡ Dernière activité",
                    value=f"Utilisateur {last_user_id}\n📅 {activity_date}\n⏰ {time_since}",
                    inline=True
                )
        else:
            # Même s'il n'y a pas d'activité récente, afficher la date de création du salon
            time_since = self.format_time_since_activity(last_activity)
            activity_date = last_activity.strftime("%d/%m/%Y à %H:%M")
            embed.add_field(
                name="⚡ Dernière activité",
                value=f"Création du salon\n📅 {activity_date}\n⏰ {time_since}",
                inline=True
            )

        # Supprimer le footer "système de surveillance de scène" car l'info est maintenant dans le champ activité
        # Le timestamp de l'embed indique déjà la dernière activité
        return embed

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

        # Créer l'embed initial (version asynchrone)
        embed = await self.create_scene_embed_async(salon, interaction.user)

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
    async def create_scene_admin(self, ctx: commands.Context, lien_salon: str, *, mj_identifier: str):
        """
        Commande admin pour créer une scène avec un MJ désigné.

        Usage: !create_scene <lien_salon> <nom_ou_id_mj>

        Args:
            lien_salon: Le lien du salon, fil ou post de forum à surveiller
            mj_identifier: Le nom d'utilisateur, l'ID ou la mention du MJ qui sera responsable de la scène
        """
        # Vérifier les permissions MJ de l'utilisateur qui lance la commande
        if not self.is_mj(ctx.author):
            error_embed = self.create_error_embed(
                title="Accès refusé",
                description="Cette commande est réservée aux MJ."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        # Rechercher l'utilisateur désigné
        designated_mj = await self.find_user_by_identifier(ctx, mj_identifier)
        if not designated_mj:
            error_embed = self.create_error_embed(
                title="Utilisateur introuvable",
                description=f"Impossible de trouver l'utilisateur `{mj_identifier}`.\n\n"
                           f"**Formats acceptés :**\n"
                           f"• ID utilisateur : `123456789012345678`\n"
                           f"• Nom d'utilisateur : `Nom Utilisateur`\n"
                           f"• Mention : `@utilisateur`"
            )
            await ctx.send(embed=error_embed, delete_after=15)
            return

        # Debug logging
        self.logger.info(f"Utilisateur trouvé: {designated_mj.display_name} (ID: {designated_mj.id}, Type: {type(designated_mj).__name__})")

        # Vérifier que le MJ désigné est membre du serveur
        guild_member = None

        # Si designated_mj est déjà un Member, l'utiliser directement
        if isinstance(designated_mj, discord.Member):
            guild_member = designated_mj
            self.logger.info(f"Utilisateur déjà un Member: {guild_member.display_name}")
        else:
            # Sinon, essayer de récupérer le membre depuis le serveur
            self.logger.info(f"Tentative de récupération du membre {designated_mj.id} depuis le serveur")
            guild_member = ctx.guild.get_member(designated_mj.id)
            if guild_member:
                self.logger.info(f"Membre trouvé dans le cache: {guild_member.display_name}")
            else:
                # Essayer de fetch le membre depuis Discord
                self.logger.info(f"Membre non trouvé dans le cache, tentative de fetch...")
                try:
                    guild_member = await ctx.guild.fetch_member(designated_mj.id)
                    self.logger.info(f"Membre récupéré via fetch: {guild_member.display_name}")
                except discord.NotFound:
                    self.logger.warning(f"Membre {designated_mj.id} non trouvé sur le serveur (NotFound)")
                except discord.HTTPException as e:
                    self.logger.warning(f"Erreur HTTP lors de la récupération du membre {designated_mj.id}: {e}")

        if not guild_member:
            error_embed = self.create_error_embed(
                title="Membre introuvable",
                description=f"L'utilisateur **{designated_mj.display_name}** n'est pas membre de ce serveur."
            )
            await ctx.send(embed=error_embed, delete_after=10)
            return

        if not self.is_mj(guild_member):
            error_embed = self.create_error_embed(
                title="Permissions insuffisantes",
                description=f"L'utilisateur **{designated_mj.display_name}** n'a pas le rôle MJ."
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

        # Créer l'embed initial avec le MJ désigné (version asynchrone)
        embed = await self.create_scene_embed_async(salon, designated_mj)

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

    async def extract_real_user_from_tupperbot(self, message: discord.Message):
        """
        Extrait l'utilisateur réel derrière un message Tupperbot/webhook.
        Retourne l'utilisateur réel ou un objet utilisateur fictif basé sur le webhook.
        """
        # Vérifier si c'est un webhook (Tupperbot utilise des webhooks)
        if message.webhook_id:
            try:
                # Méthode 1: Chercher les messages récents d'utilisateurs non-bot
                recent_time = message.created_at - timedelta(seconds=60)
                async for recent_msg in message.channel.history(limit=15, before=message.created_at, after=recent_time):
                    if not recent_msg.author.bot:
                        return recent_msg.author

                # Méthode 2: Si pas de message récent, chercher dans un intervalle plus large
                extended_time = message.created_at - timedelta(minutes=5)
                async for recent_msg in message.channel.history(limit=30, before=message.created_at, after=extended_time):
                    if not recent_msg.author.bot:
                        return recent_msg.author

                # Méthode 3: Si aucun utilisateur réel trouvé, créer un objet utilisateur fictif
                # basé sur le nom du webhook pour au moins avoir un nom à afficher
                if hasattr(message.author, 'display_name') and message.author.display_name:
                    # Créer un objet utilisateur fictif avec les informations du webhook
                    class WebhookUser:
                        def __init__(self, webhook_author):
                            self.id = webhook_author.id
                            self.display_name = webhook_author.display_name
                            self.name = webhook_author.name
                            self.mention = f"<@{webhook_author.id}>"
                            self.avatar = webhook_author.avatar
                            self.bot = True  # Marquer comme bot pour éviter la confusion

                    webhook_user = WebhookUser(message.author)
                    self.logger.info(f"Utilisateur Tupperbox identifié par webhook: {webhook_user.display_name}")
                    return webhook_user

            except Exception as e:
                self.logger.error(f"Erreur lors de l'extraction utilisateur Tupperbot: {e}")
                return None

        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Surveille les messages dans les salons surveillés."""

        # Vérifier si le salon est surveillé d'abord
        channel_id = message.channel.id
        if channel_id not in self.monitored_channels:
            return

        # Identifier l'utilisateur réel (peut être différent pour Tupperbot)
        real_user = None
        
        if message.author.bot:
            # Vérifier si c'est un message Tupperbot/webhook
            if message.webhook_id:
                # Utiliser la méthode améliorée pour extraire l'utilisateur réel
                real_user = await self.extract_real_user_from_tupperbot(message)
                if real_user:
                    self.logger.info(f"Message Tupperbot détecté de {real_user.display_name} dans le salon {channel_id}")

            # Si on n'a pas identifié d'utilisateur réel, ignorer le message
            if not real_user:
                return
        else:
            # Message d'utilisateur normal
            real_user = message.author

        try:
            data = self.monitored_channels[channel_id]
            mj_id = data['mj_user_id']
            mj = self.bot.get_user(mj_id)

            # Si le MJ n'est pas dans le cache, essayer de le récupérer
            if not mj:
                try:
                    mj = await self.bot.fetch_user(mj_id)
                except (discord.NotFound, discord.HTTPException):
                    pass

            if not mj:
                self.logger.warning(f"MJ avec ID {mj_id} non trouvé pour le salon {channel_id}")
                return

            # Mettre à jour last_activity avec timestamp précis et utilisateur réel
            current_time = message.created_at  # Utiliser le timestamp du message au lieu de now()
            data['last_activity'] = current_time
            data['last_action_user_id'] = real_user.id  # Utiliser l'utilisateur réel (pas le bot)
            self.save_monitored_channels()

            # Mettre à jour l'embed de surveillance avec l'utilisateur réel
            await self.update_scene_embed(channel_id, real_user.id, real_user)

            # Récupérer le salon de notification
            notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                self.logger.error(f"Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé")
                return

            # Vérifier si un ping peut être envoyé (respecter l'intervalle selon l'utilisateur réel)
            if self.can_send_ping(channel_id, real_user.id):
                # Envoyer la notification de ping (MP avec fallback salon)
                if data['message_id']:
                    try:
                        embed_message = await notification_channel.fetch_message(data['message_id'])

                        # Envoyer la notification (MP ou fallback salon) avec l'utilisateur réel
                        ping_sent = await self.send_ping_notification(
                            mj, real_user, message.channel, channel_id,
                            notification_channel, embed_message
                        )

                        if ping_sent:
                            # Mettre à jour le timestamp du dernier ping pour ce salon avec l'utilisateur réel
                            self.update_last_ping_time(channel_id, real_user.id)

                    except discord.NotFound:
                        self.logger.warning(f"Message d'embed {data['message_id']} non trouvé")
                        # Retirer le message_id invalide
                        data['message_id'] = None
                        self.save_monitored_channels()
            else:
                # Log que le ping a été ignoré à cause du cooldown
                remaining_seconds = self.get_remaining_cooldown(channel_id, real_user.id)
                remaining_minutes = remaining_seconds // 60
                remaining_seconds_display = remaining_seconds % 60

                # Déterminer le type de cooldown pour le log
                ping_data = self.last_ping_times.get(channel_id, {})
                last_user_id = ping_data.get('last_user_id')
                cooldown_type = "même utilisateur (30m)" if last_user_id == real_user.id else "utilisateur différent (5m)"

                self.logger.debug(
                    f"Ping ignoré pour {message.channel.name} - Cooldown actif ({cooldown_type}) "
                    f"(reste {remaining_minutes}m {remaining_seconds_display}s) - Utilisateur réel: {real_user.display_name}"
                )

        except Exception as e:
            self.logger.error(f"Erreur lors de la notification pour le message {message.id}: {e}")

    async def setup_persistent_views(self):
        """Configure les vues persistantes pour les embeds existants avec la nouvelle version."""
        try:
            views_configured = 0
            for channel_id, data in self.monitored_channels.items():
                if data['message_id']:
                    # Créer une NOUVELLE vue avec seulement 2 boutons
                    view = SceneView(self, channel_id)
                    self.bot.add_view(view, message_id=data['message_id'])
                    views_configured += 1
                    self.logger.debug(f"Vue persistante configurée pour salon {channel_id} avec {len(view.children)} boutons")

            self.logger.info(f"✅ Configuré {views_configured} vues persistantes avec la nouvelle version (2 boutons)")
        except Exception as e:
            self.logger.error(f"Erreur lors de la configuration des vues persistantes: {e}")



async def setup(bot: commands.Bot):
    """Fonction de setup du cog."""
    await bot.add_cog(ChannelMonitor(bot))
    print("Cog ChannelMonitor chargé avec succès")
