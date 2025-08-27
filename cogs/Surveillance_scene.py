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
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
import re
from typing import Optional, Dict, List, Union

# Configuration
SURVEILLANCE_CHANNEL_ID = 1380704586016362626
PARIS_TZ = pytz.timezone('Europe/Paris')

# Regroupement des mises à jour
UPDATE_BATCH_SIZE = 10  # Nombre de messages avant un rafraîchissement
UPDATE_INTERVAL_MINUTES = 5  # Intervalle de rafraîchissement en minutes

# Durée de rétention des entrées du cache anti-spam (24 heures)
NOTIFICATION_RETENTION_SECONDS = 24 * 60 * 60

# Intervalle minimal entre deux notifications dans un même salon (minutes)
CHANNEL_NOTIFICATION_INTERVAL_MINUTES = 5

# Délai entre les mises à jour des scènes (secondes)
UPDATE_SLEEP_SECONDS = 1

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

            # Répondre à l'interaction puis supprimer le message
            await interaction.response.send_message(
                f"🔒 **Surveillance clôturée**\nLa surveillance de **{self.scene_data['scene_name']}** a été fermée.",
                ephemeral=True
            )

            # Supprimer le message de surveillance
            try:
                await interaction.followup.delete_message(interaction.message.id)
            except:
                # Si la suppression échoue, essayer de modifier le message
                embed = discord.Embed(
                    title="🔒 Surveillance clôturée",
                    description=f"La surveillance de **{self.scene_data['scene_name']}** a été fermée.",
                    color=0x95a5a6,
                    timestamp=datetime.now(PARIS_TZ)
                )
                embed.set_footer(text=f"Clôturée par {interaction.user.display_name}")

                for child in self.children:
                    child.disabled = True

                await interaction.edit_original_response(embed=embed, view=self)
            
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

        # Cache pour éviter le spam de notifications (channel_id -> {user_id: timestamp})
        self.last_notifications: Dict[str, Dict[str, float]] = {}

        # Dernière notification envoyée par salon (channel_id -> timestamp)
        self.last_channel_notifications: Dict[str, float] = {}


        # Caches pour les mises à jour différées
        self.pending_updates: Dict[str, dict] = {}
        self.pending_update_counts: Dict[str, int] = {}

        # Démarrer les tâches
        self.update_surveillance.start()
        self.check_inactive_scenes.start()
        self.process_pending_updates.start()
        self.cleanup_notifications.start()
        
    def setup_google_sheets(self):
        """Configure la connexion Google Sheets."""
        try:
            credentials = Credentials.from_service_account_info(
                json.loads(os.getenv('SERVICE_ACCOUNT_JSON')),
                scopes=['https://www.googleapis.com/auth/spreadsheets'],
            )
        except Exception as e:
            logging.error(f"Erreur lors du chargement des credentials Google Sheets: {e}")
            self.sheet = None
            return

        self.gc = None
        self.spreadsheet = None
        for attempt in range(1, 4):
            try:
                logging.info(f"Tentative {attempt} de connexion à Google Sheets")
                self.gc = gspread.authorize(credentials)
                self.spreadsheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_VALIDATION'))
                break
            except Exception as e:
                logging.warning(
                    f"Échec de la tentative {attempt} de connexion à Google Sheets: {e}"
                )
                if attempt < 3:
                    delay = 2 ** attempt
                    logging.info(f"Nouvelle tentative dans {delay} secondes")
                    time.sleep(delay)

        if not self.spreadsheet:
            logging.error("Impossible de se connecter à Google Sheets après 3 tentatives")
            self.sheet = None
            return

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
        self.process_pending_updates.cancel()
        self.cleanup_notifications.cancel()

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
        if self.sheet is None:
            logging.warning("Feuille Google Sheets indisponible, tentative de reconnexion")
            self.setup_google_sheets()
            if self.sheet is None:
                logging.error(
                    "Impossible de se reconnecter à Google Sheets dans update_surveillance"
                )
                return
            logging.info("Reconnexion réussie à Google Sheets")
            
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
            # IMPORTANT: Recharger les données depuis Google Sheets pour avoir les infos à jour
            await self.refresh_monitored_scenes()
            logging.info(f"Vérification d'inactivité pour {len(self.monitored_scenes)} scènes")

            now = datetime.now(self.paris_tz)
            seven_days_ago = now - timedelta(days=7)

            for scene_data in self.monitored_scenes.values():
                try:
                    last_activity_str = scene_data.get('last_activity_date', '')
                    if not last_activity_str:
                        logging.warning(f"Pas de date d'activité pour la scène {scene_data.get('scene_name', 'Inconnue')}")
                        continue

                    last_activity = datetime.fromisoformat(last_activity_str)
                    # S'assurer que la date a une timezone
                    if last_activity.tzinfo is None:
                        last_activity = self.paris_tz.localize(last_activity)

                    time_since_activity = now - last_activity
                    logging.info(f"Scène {scene_data.get('scene_name', 'Inconnue')}: dernière activité il y a {time_since_activity.days} jours")

                    if time_since_activity >= timedelta(days=7):
                        logging.info(f"Scène inactive détectée: {scene_data.get('scene_name', 'Inconnue')}")
                        await self.notify_inactive_scene(scene_data)

                except Exception as scene_error:
                    logging.error(f"Erreur lors de la vérification de la scène {scene_data.get('scene_name', 'Inconnue')}: {scene_error}")

        except Exception as e:
            logging.error(f"Erreur dans check_inactive_scenes: {e}")
    
    @check_inactive_scenes.before_loop
    async def before_check_inactive_scenes(self):
        """Attend que le bot soit prêt."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)

    def convert_scientific_to_int(self, value) -> str:
        """Convertit une notation scientifique en entier string (pour les IDs Discord)."""
        try:
            # Nettoyer la valeur (supprimer apostrophes de Google Sheets)
            clean_value = str(value).lstrip("'").strip()

            # Si la valeur est vide ou 'nan', retourner une chaîne vide
            if not clean_value or clean_value.lower() == 'nan':
                return ""

            # Vérifier si c'est de la notation scientifique
            if isinstance(clean_value, str) and ('E+' in clean_value.upper() or 'e+' in clean_value):
                # Convertir la notation scientifique en entier
                float_val = float(clean_value.replace(',', '.'))  # Gérer les virgules européennes
                int_val = int(float_val)
                return str(int_val)

            # Si c'est déjà un nombre valide, le retourner tel quel
            if clean_value.isdigit():
                return clean_value

            return clean_value
        except (ValueError, TypeError) as e:
            logging.warning(f"Impossible de convertir '{value}' en entier: {e}")
            return str(value).lstrip("'").strip()

    def format_id_for_sheets(self, id_value) -> str:
        """Formate un ID pour Google Sheets en ajoutant l'apostrophe si nécessaire."""
        if not id_value:
            return ""

        str_value = str(id_value)

        # Ne pas ajouter d'apostrophe si l'ID est vide ou nan
        if not str_value or str_value.lower() == 'nan':
            return ""

        # Si l'ID commence déjà par une apostrophe, le retourner tel quel
        if str_value.startswith("'"):
            return str_value

        # Sinon, nettoyer et ajouter l'apostrophe
        clean_id = str_value.lstrip("'")
        return f"'{clean_id}"

    async def refresh_monitored_scenes(self):
        """Recharge les scènes surveillées depuis Google Sheets."""
        if not self.sheet:
            logging.error("Aucune feuille Google Sheets configurée")
            return

        try:
            records = self.sheet.get_all_records()
            logging.info(f"Récupération de {len(records)} enregistrements depuis Google Sheets")

            # Sauvegarder l'ancien cache pour comparaison
            old_scenes = set(self.monitored_scenes.keys())
            self.monitored_scenes.clear()

            for i, record in enumerate(records):
                channel_id_raw = record.get('channel_id')
                # Convertir la notation scientifique si nécessaire
                channel_id = self.convert_scientific_to_int(channel_id_raw)

                if channel_id and str(channel_id).strip() and channel_id != 'nan':  # Vérifier que channel_id n'est pas vide
                    # Convertir tous les autres IDs aussi
                    record['channel_id'] = channel_id
                    record['gm_id'] = self.convert_scientific_to_int(record.get('gm_id', ''))
                    record['message_id'] = self.convert_scientific_to_int(record.get('message_id', ''))
                    record['guild_id'] = self.convert_scientific_to_int(record.get('guild_id', ''))

                    self.monitored_scenes[str(channel_id)] = record
                    logging.info(f"Scène ajoutée: {channel_id} - {record.get('scene_name', 'N/A')}")
                else:
                    logging.warning(f"Enregistrement {i+1} ignoré: channel_id vide ou invalide")

            # Identifier les scènes qui ont été supprimées de Google Sheets
            new_scenes = set(self.monitored_scenes.keys())
            removed_scenes = old_scenes - new_scenes
            added_scenes = new_scenes - old_scenes

            if removed_scenes:
                logging.info(f"Scènes supprimées de Google Sheets: {removed_scenes}")
            if added_scenes:
                logging.info(f"Nouvelles scènes dans Google Sheets: {added_scenes}")

            logging.info(f"Total des scènes chargées: {len(self.monitored_scenes)}")

        except Exception as e:
            logging.error(f"Erreur lors du rechargement des scènes: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

    async def get_channel_from_link(self, channel_link: str) -> Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]]:
        """Récupère un canal à partir d'un lien Discord."""
        try:
            # Vérifier si le lien est une mention de canal <#id>
            mention_match = re.match(r'<#(\d+)>', channel_link)
            if mention_match:
                channel_id = int(mention_match.group(1))
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    for guild in self.bot.guilds:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            break
                if channel:
                    logging.info(f"Canal mention trouvé: {channel.name} (ID: {channel.id})")
                    return channel
                else:
                    logging.error(f"Canal {channel_id} non trouvé pour la mention {channel_link}")
                    return None

            # Extraire l'ID du canal depuis le lien (support discord.com et discordapp.com)
            match = re.search(r'(?:discord(?:app)?\.com)/channels/(\d+)/(\d+)(?:/(\d+))?', channel_link)
            if not match:
                logging.error(f"Format de lien ou mention non reconnu: {channel_link}")
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
        """Parse une date au format JJ/MM/AA ou JJ/MM/AAAA."""
        try:
            # Essayer d'abord le format avec année sur 4 chiffres (JJ/MM/AAAA)
            parsed_date = datetime.strptime(date_str, "%d/%m/%Y").replace(hour=0, minute=0, second=0, microsecond=0)
            # Ajouter la timezone Paris
            return self.paris_tz.localize(parsed_date)
        except ValueError:
            try:
                # Essayer le format avec année sur 2 chiffres (JJ/MM/AA)
                parsed_date = datetime.strptime(date_str, "%d/%m/%y").replace(hour=0, minute=0, second=0, microsecond=0)
                # Ajouter la timezone Paris
                return self.paris_tz.localize(parsed_date)
            except ValueError:
                # Si aucun format ne fonctionne, utiliser la date d'aujourd'hui au début de la journée
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

    async def get_user_display_name_async(self, message: discord.Message) -> str:
        """Version asynchrone pour récupérer le nom d'affichage d'un utilisateur."""
        if message.author.bot and message.webhook_id:
            # C'est un webhook (Tupperbox), utiliser le nom du personnage
            return message.author.name if message.author.name else message.author.display_name
        else:
            # Utilisateur normal - récupérer le Member pour avoir le nickname du serveur
            if message.guild:
                # Essayer d'abord le cache
                member = message.guild.get_member(message.author.id)

                # Si pas dans le cache, essayer de le récupérer via l'API
                if not member:
                    try:
                        member = await message.guild.fetch_member(message.author.id)
                        logging.debug(f"Membre {message.author.id} récupéré via fetch_member")
                    except discord.NotFound:
                        logging.warning(f"Membre {message.author.id} non trouvé dans le serveur {message.guild.id}")
                    except discord.Forbidden:
                        logging.warning(f"Pas de permission pour récupérer le membre {message.author.id}")
                    except Exception as e:
                        logging.error(f"Erreur lors de la récupération du membre {message.author.id}: {e}")

                if member:
                    display_name = member.display_name
                    logging.debug(f"Nom d'affichage pour {message.author.id}: '{display_name}' (nickname: '{member.nick}', global_name: '{member.global_name}', username: '{member.name}')")
                    return display_name

            # Fallback si pas de serveur ou membre non trouvé
            fallback_name = message.author.display_name
            logging.debug(f"Fallback pour {message.author.id}: '{fallback_name}'")
            return fallback_name

    def get_user_display_name(self, message: discord.Message) -> str:
        """Récupère le nom d'affichage d'un utilisateur (version synchrone pour compatibilité)."""
        if message.author.bot and message.webhook_id:
            # C'est un webhook (Tupperbox), utiliser le nom du personnage
            return message.author.name if message.author.name else message.author.display_name
        else:
            # Utilisateur normal - récupérer le Member pour avoir le nickname du serveur
            if message.guild:
                member = message.guild.get_member(message.author.id)
                if member:
                    display_name = member.display_name
                    logging.debug(f"Nom d'affichage pour {message.author.id}: '{display_name}' (nickname: '{member.nick}', global_name: '{member.global_name}', username: '{member.name}')")
                    return display_name
                else:
                    logging.warning(f"Membre {message.author.id} non trouvé dans le cache du serveur {message.guild.id}")

            # Fallback si pas de serveur ou membre non trouvé
            fallback_name = message.author.display_name
            logging.debug(f"Fallback pour {message.author.id}: '{fallback_name}'")
            return fallback_name

    def should_ignore_message_for_participants(self, message: discord.Message) -> bool:
        """Détermine si un message doit être ignoré pour la liste des participants (ex: Maître du Jeu, message initiateur de forum)."""
        # Ignorer des utilisateurs spécifiques par leur ID
        ignored_user_ids = [249497144698863617, 496737005720436756]
        if message.author.id in ignored_user_ids:
            return True

        # Ignorer tous les webhooks qui ont le nom "Maître du Jeu" (avec ou sans caractères invisibles)
        if message.author.bot and message.webhook_id:
            user_name = self.get_user_display_name(message)
            # Nettoyer le nom en supprimant les caractères invisibles et espaces
            clean_name = ''.join(char for char in user_name if char.isprintable()).strip()
            if clean_name == "Maître du Jeu" or user_name.startswith("Maître du Jeu"):
                return True

        # Ignorer le message initiateur des posts de forum
        if isinstance(message.channel, discord.Thread) and hasattr(message.channel, 'parent'):
            # Vérifier si c'est un thread de forum
            if isinstance(message.channel.parent, discord.ForumChannel):
                # Vérifier si c'est le message initiateur en utilisant l'ID du thread
                # Le message initiateur d'un post de forum a le même ID que le thread
                if message.id == message.channel.id:
                    return True

        return False

    def is_game_master_message(self, message: discord.Message) -> bool:
        """Détermine si un message provient du 'Maître du Jeu' ou doit être ignoré pour l'activité."""
        # Ignorer des utilisateurs spécifiques par leur ID
        ignored_user_ids = [249497144698863617, 496737005720436756]
        if message.author.id in ignored_user_ids:
            return True

        # Ignorer les messages du Maître du Jeu
        if message.author.bot and message.webhook_id:
            user_name = self.get_user_display_name(message)
            # Nettoyer le nom en supprimant les caractères invisibles et espaces
            clean_name = ''.join(char for char in user_name if char.isprintable()).strip()
            if clean_name == "Maître du Jeu" or user_name.startswith("Maître du Jeu"):
                return True

        # Ignorer le message initiateur des posts de forum pour les notifications
        if isinstance(message.channel, discord.Thread) and hasattr(message.channel, 'parent'):
            # Vérifier si c'est un thread de forum
            if isinstance(message.channel.parent, discord.ForumChannel):
                # Vérifier si c'est le message initiateur en utilisant l'ID du thread
                # Le message initiateur d'un post de forum a le même ID que le thread
                if message.id == message.channel.id:
                    return True

        return False

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

                # Ignorer les messages qui doivent être filtrés pour les participants (ex: Maître du Jeu)
                if self.should_ignore_message_for_participants(message):
                    continue

                # Utiliser la version asynchrone pour obtenir le nom d'affichage
                user_name = await self.get_user_display_name_async(message)
                participants.add(user_name)



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

            async for message in channel.history(limit=50):
                # Pour la dernière activité, on prend TOUS les messages (y compris Maître du Jeu)
                # car on veut savoir quand la scène a vraiment été active pour la dernière fois

                # Utiliser la version asynchrone pour obtenir le nom d'affichage
                user_name = await self.get_user_display_name_async(message)

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
            now = datetime.now(self.paris_tz)
            embed = discord.Embed(
                title="🎭 Surveillance de Scène",
                color=0x3498db,
                timestamp=now
            )

            # Lien vers la scène (remplace le nom par un lien cliquable)
            channel_id = scene_data.get('channel_id')
            if channel_id:
                embed.add_field(
                    name="📍 Scène",
                    value=f"<#{channel_id}>",
                    inline=True
                )
            else:
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
                    # S'assurer que activity_date a une timezone
                    if activity_date.tzinfo is None:
                        activity_date = self.paris_tz.localize(activity_date)

                    now = datetime.now(self.paris_tz)
                    time_diff = now - activity_date

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

            embed.set_footer(
                text=f"Mise à jour automatique le {now.strftime('%d/%m/%Y à %H:%M')}"
            )

            return embed

        except Exception as e:
            logging.error(f"Erreur lors de la création de l'embed: {e}")
            return discord.Embed(title="❌ Erreur", description="Impossible de créer l'embed de surveillance.")

    @commands.command(name='scene')
    async def scene_command(self, ctx, channel_link: str = None, date: str = None, gm_id: str = None):
        """
        Commande pour initier la surveillance d'une scène.
        Usage: !scene [Lien du salon] [Date JJ/MM/AA ou JJ/MM/AAAA] [ID du MJ]
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

            # Ajouter à Google Sheets (avec apostrophe pour forcer le format texte sur les IDs)
            self.sheet.append_row([
                self.format_id_for_sheets(scene_data['channel_id']),
                scene_data['scene_name'],
                self.format_id_for_sheets(scene_data['gm_id']),
                scene_data['start_date'],
                scene_data['participants'],
                scene_data['last_activity_user'],
                scene_data['last_activity_date'],
                self.format_id_for_sheets(scene_data['message_id']),
                scene_data['channel_type'],
                self.format_id_for_sheets(scene_data['guild_id'])
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

                # Réordonner les messages de surveillance après création
                await self.reorder_surveillance_messages()

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

    @commands.command(name='diagnose_sheet')
    @commands.has_permissions(administrator=True)
    async def diagnose_sheet_command(self, ctx):
        """Diagnostique l'état du Google Sheet pour identifier les problèmes."""
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            records = self.sheet.get_all_records()

            issues = {
                'double_apostrophes': 0,
                'scientific_notation': 0,
                'missing_message_id': 0,
                'empty_ids': 0,
                'duplicates': 0
            }

            seen_channels = set()

            for i, record in enumerate(records, start=2):
                channel_id = str(record.get('channel_id', ''))
                gm_id = str(record.get('gm_id', ''))
                message_id = str(record.get('message_id', ''))
                guild_id = str(record.get('guild_id', ''))

                # Vérifier les doubles apostrophes
                for id_name, id_value in [('channel_id', channel_id), ('gm_id', gm_id), ('message_id', message_id), ('guild_id', guild_id)]:
                    if id_value.startswith("''"):
                        issues['double_apostrophes'] += 1
                        logging.info(f"Double apostrophe détectée ligne {i} {id_name}: {id_value}")

                # Vérifier la notation scientifique
                for id_value in [channel_id, gm_id, message_id, guild_id]:
                    if 'E+' in id_value.upper():
                        issues['scientific_notation'] += 1
                        logging.info(f"Notation scientifique détectée ligne {i}: {id_value}")

                # Vérifier les message_id manquants
                if not message_id or message_id.strip() == '' or message_id.lower() == 'nan':
                    issues['missing_message_id'] += 1
                    logging.info(f"Message_id manquant ligne {i}")

                # Vérifier les IDs vides
                if not channel_id.lstrip("'").strip():
                    issues['empty_ids'] += 1
                    logging.info(f"Channel_id vide ligne {i}")

                # Vérifier les doublons
                clean_channel_id = channel_id.lstrip("'")
                if clean_channel_id in seen_channels:
                    issues['duplicates'] += 1
                    logging.info(f"Doublon détecté ligne {i}: {clean_channel_id}")
                else:
                    seen_channels.add(clean_channel_id)

            embed = discord.Embed(
                title="🔍 Diagnostic du Google Sheet",
                color=0x3498db
            )

            embed.add_field(
                name="📊 Résumé des problèmes",
                value=f"• Doubles apostrophes: {issues['double_apostrophes']}\n"
                      f"• Notation scientifique: {issues['scientific_notation']}\n"
                      f"• Message_id manquants: {issues['missing_message_id']}\n"
                      f"• IDs vides: {issues['empty_ids']}\n"
                      f"• Doublons: {issues['duplicates']}",
                inline=False
            )

            embed.add_field(
                name="🛠️ Actions recommandées",
                value="• `!fix_sheet_ids` - Corriger les formats d'IDs\n"
                      "• `!restore_message_ids` - Restaurer les message_id\n"
                      "• `!remove_duplicates` - Supprimer les doublons",
                inline=False
            )

            await ctx.send(embed=embed)

        except Exception as e:
            logging.error(f"Erreur lors du diagnostic: {e}")
            await ctx.send(f"❌ Erreur lors du diagnostic: {str(e)}")

    @commands.command(name='remove_duplicates')
    @commands.has_permissions(administrator=True)
    async def remove_duplicates_command(self, ctx):
        """Supprime les doublons dans Google Sheets basés sur channel_id."""
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            await ctx.send("🔧 Suppression des doublons en cours...")

            records = self.sheet.get_all_records()
            seen_channels = set()
            rows_to_delete = []

            # Identifier les doublons (en partant de la fin pour éviter les problèmes d'index)
            for i, record in enumerate(records, start=2):
                channel_id = str(record.get('channel_id', '')).lstrip("'")

                if channel_id and channel_id != 'nan':
                    if channel_id in seen_channels:
                        rows_to_delete.append(i)
                        logging.info(f"Doublon détecté ligne {i}: {channel_id}")
                    else:
                        seen_channels.add(channel_id)

            # Supprimer les doublons (en commençant par la fin)
            for row_num in reversed(rows_to_delete):
                self.sheet.delete_rows(row_num)
                logging.info(f"Ligne {row_num} supprimée")

            await ctx.send(f"✅ Suppression terminée ! {len(rows_to_delete)} doublons supprimés.")

            # Recharger le cache
            await self.refresh_monitored_scenes()
            await ctx.send("🔄 Cache des scènes rechargé.")

        except Exception as e:
            logging.error(f"Erreur lors de la suppression des doublons: {e}")
            await ctx.send(f"❌ Erreur lors de la suppression: {str(e)}")

    @commands.command(name='recover_message_ids')
    @commands.has_permissions(administrator=True)
    async def recover_message_ids_command(self, ctx):
        """Récupère les message_id depuis les messages existants dans le canal de surveillance."""
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            await ctx.send("🔧 Récupération des message_id depuis le canal de surveillance...")

            surveillance_channel = self.bot.get_channel(SURVEILLANCE_CHANNEL_ID)
            if not surveillance_channel:
                await ctx.send("❌ Canal de surveillance non trouvé.")
                return

            # Récupérer les messages récents du canal de surveillance
            messages = []
            async for message in surveillance_channel.history(limit=200):
                if message.author == self.bot.user and message.embeds:
                    embed = message.embeds[0]
                    # Chercher le channel_id dans l'embed
                    for field in embed.fields:
                        if "Canal:" in field.value or "Informations de debug" in field.name:
                            # Extraire l'ID du canal depuis le mention <#123456>
                            import re
                            channel_match = re.search(r'<#(\d+)>', field.value)
                            if channel_match:
                                channel_id = channel_match.group(1)
                                messages.append((channel_id, str(message.id)))
                                break

            await ctx.send(f"📋 {len(messages)} messages de surveillance trouvés.")

            # Mettre à jour Google Sheets
            records = self.sheet.get_all_records()
            updated_count = 0

            for i, record in enumerate(records, start=2):
                record_channel_id = str(record.get('channel_id', '')).lstrip("'")
                current_message_id = record.get('message_id', '')

                # Chercher le message_id correspondant
                for msg_channel_id, msg_id in messages:
                    if record_channel_id == msg_channel_id:
                        if not current_message_id or current_message_id.strip() == '' or current_message_id.lower() == 'nan':
                            # Mettre à jour le message_id
                            self.sheet.update(f'H{i}', self.format_id_for_sheets(msg_id))
                            updated_count += 1
                            logging.info(f"Message_id récupéré pour canal {record_channel_id}: {msg_id}")
                        break

            await ctx.send(f"✅ Récupération terminée ! {updated_count} message_id récupérés.")

            # Recharger le cache
            await self.refresh_monitored_scenes()
            await ctx.send("🔄 Cache des scènes rechargé.")

        except Exception as e:
            logging.error(f"Erreur lors de la récupération des message_id: {e}")
            await ctx.send(f"❌ Erreur lors de la récupération: {str(e)}")

    @commands.command(name='restore_message_ids')
    @commands.has_permissions(administrator=True)
    async def restore_message_ids_command(self, ctx):
        """Restaure les message_id manquants en recréant les messages de surveillance."""
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            await ctx.send("🔧 Restauration des message_id en cours...")

            records = self.sheet.get_all_records()
            restored_count = 0

            surveillance_channel = self.bot.get_channel(SURVEILLANCE_CHANNEL_ID)
            if not surveillance_channel:
                await ctx.send("❌ Canal de surveillance non trouvé.")
                return

            for i, record in enumerate(records, start=2):
                message_id = record.get('message_id', '')
                channel_id = record.get('channel_id', '')

                # Si message_id est vide ou invalide
                if not message_id or message_id.strip() == '' or message_id.lower() == 'nan':
                    try:
                        # Créer un nouveau message de surveillance
                        scene_data = {
                            'channel_id': self.convert_scientific_to_int(channel_id),
                            'scene_name': record.get('scene_name', ''),
                            'gm_id': self.convert_scientific_to_int(record.get('gm_id', '')),
                            'start_date': record.get('start_date', ''),
                            'participants': record.get('participants', '[]'),
                            'last_activity_user': record.get('last_activity_user', ''),
                            'last_activity_date': record.get('last_activity_date', ''),
                            'channel_type': record.get('channel_type', ''),
                            'guild_id': self.convert_scientific_to_int(record.get('guild_id', ''))
                        }

                        embed = await self.create_surveillance_embed(scene_data)
                        view = SceneSurveillanceView(self, scene_data)

                        new_message = await surveillance_channel.send(embed=embed, view=view)

                        # Mettre à jour le message_id dans Google Sheets
                        self.sheet.update(f'H{i}', self.format_id_for_sheets(str(new_message.id)))
                        restored_count += 1

                        logging.info(f"Message_id restauré pour la scène {scene_data['scene_name']}: {new_message.id}")

                    except Exception as e:
                        logging.error(f"Erreur lors de la restauration du message_id ligne {i}: {e}")

            await ctx.send(f"✅ Restauration terminée ! {restored_count} message_id restaurés.")

            # Recharger le cache
            await self.refresh_monitored_scenes()
            await ctx.send("🔄 Cache des scènes rechargé.")

        except Exception as e:
            logging.error(f"Erreur lors de la restauration des message_id: {e}")
            await ctx.send(f"❌ Erreur lors de la restauration: {str(e)}")

    @commands.command(name='fix_sheet_ids')
    @commands.has_permissions(administrator=True)
    async def fix_sheet_ids_command(self, ctx):
        """Corrige les IDs Discord mal formatés dans Google Sheets."""
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            await ctx.send("🔧 Correction des IDs Discord en cours...")

            records = self.sheet.get_all_records()
            fixed_count = 0

            for i, record in enumerate(records, start=2):  # Start=2 car ligne 1 = en-tête
                needs_update = False
                updated_row = []

                # Colonnes à corriger : A=channel_id, C=gm_id, H=message_id, J=guild_id
                columns_to_fix = {
                    'A': record.get('channel_id', ''),
                    'B': record.get('scene_name', ''),
                    'C': record.get('gm_id', ''),
                    'D': record.get('start_date', ''),
                    'E': record.get('participants', ''),
                    'F': record.get('last_activity_user', ''),
                    'G': record.get('last_activity_date', ''),
                    'H': record.get('message_id', ''),
                    'I': record.get('channel_type', ''),
                    'J': record.get('guild_id', '')
                }

                # Vérifier et corriger les IDs
                for col, value in columns_to_fix.items():
                    if col in ['A', 'C', 'H', 'J']:  # Colonnes contenant des IDs Discord
                        original_value = str(value)

                        # Vérifier si l'ID a besoin d'être corrigé
                        needs_id_fix = False

                        if 'E+' in original_value.upper():  # Notation scientifique
                            needs_id_fix = True
                        elif original_value.startswith("''"):  # Double apostrophe
                            needs_id_fix = True
                        elif original_value and not original_value.startswith("'") and original_value.strip() and original_value.lower() != 'nan':  # Pas d'apostrophe mais pas vide
                            needs_id_fix = True

                        if needs_id_fix:
                            # Convertir et formater l'ID
                            if 'E+' in original_value.upper():
                                # Notation scientifique - convertir
                                clean_id = self.convert_scientific_to_int(value)
                                if clean_id and clean_id.strip():
                                    formatted_id = self.format_id_for_sheets(clean_id)
                                    updated_row.append(formatted_id)
                                    needs_update = True
                                    logging.info(f"ID converti (notation scientifique): '{original_value}' → '{formatted_id}'")
                                else:
                                    updated_row.append(original_value)
                            elif original_value.startswith("''"):
                                # Double apostrophe - corriger
                                clean_id = original_value.lstrip("'")
                                if clean_id and clean_id.strip():
                                    formatted_id = self.format_id_for_sheets(clean_id)
                                    updated_row.append(formatted_id)
                                    needs_update = True
                                    logging.info(f"ID corrigé (double apostrophe): '{original_value}' → '{formatted_id}'")
                                else:
                                    updated_row.append(original_value)
                            else:
                                # Pas d'apostrophe - ajouter une apostrophe
                                if original_value and original_value.strip() and original_value.lower() != 'nan':
                                    formatted_id = self.format_id_for_sheets(original_value)
                                    updated_row.append(formatted_id)
                                    needs_update = True
                                    logging.info(f"ID formaté (ajout apostrophe): '{original_value}' → '{formatted_id}'")
                                else:
                                    updated_row.append(original_value)
                        else:
                            updated_row.append(value)
                    else:
                        updated_row.append(value)

                if needs_update:
                    self.sheet.update(f'A{i}:J{i}', [updated_row])
                    fixed_count += 1
                    logging.info(f"Ligne {i} corrigée")

            await ctx.send(f"✅ Correction terminée ! {fixed_count} lignes ont été corrigées.")

            # Recharger le cache
            await self.refresh_monitored_scenes()
            await ctx.send("🔄 Cache des scènes rechargé.")

        except Exception as e:
            logging.error(f"Erreur lors de la correction des IDs: {e}")
            await ctx.send(f"❌ Erreur lors de la correction: {str(e)}")

    @commands.command(name='check_channels')
    @commands.has_permissions(administrator=True)
    async def check_channels_command(self, ctx):
        """Vérifie l'accès aux canaux surveillés."""
        if not self.sheet:
            await ctx.send("❌ Erreur de configuration Google Sheets.")
            return

        try:
            await self.refresh_monitored_scenes()

            embed = discord.Embed(
                title="🔍 Vérification des canaux surveillés",
                color=0x3498db
            )

            accessible = 0
            inaccessible = 0
            details = []

            for channel_id, scene_data in self.monitored_scenes.items():
                clean_channel_id = self.convert_scientific_to_int(channel_id)
                scene_name = scene_data.get('scene_name', 'Inconnu')

                try:
                    channel = self.bot.get_channel(int(clean_channel_id))
                    if not channel:
                        channel = await self.bot.fetch_channel(int(clean_channel_id))

                    accessible += 1
                    details.append(f"✅ {scene_name} ({clean_channel_id})")

                except discord.NotFound:
                    inaccessible += 1
                    details.append(f"❌ {scene_name} ({clean_channel_id}) - Canal non trouvé")
                except discord.Forbidden:
                    inaccessible += 1
                    details.append(f"🔒 {scene_name} ({clean_channel_id}) - Permissions insuffisantes")
                except Exception as e:
                    inaccessible += 1
                    details.append(f"⚠️ {scene_name} ({clean_channel_id}) - Erreur: {str(e)[:50]}")

            embed.add_field(
                name="📊 Résumé",
                value=f"Accessibles: {accessible}\nInaccessibles: {inaccessible}",
                inline=False
            )

            # Limiter les détails pour éviter les messages trop longs
            if details:
                details_text = "\n".join(details[:10])
                if len(details) > 10:
                    details_text += f"\n... et {len(details) - 10} autres"

                embed.add_field(
                    name="📋 Détails",
                    value=f"```{details_text}```",
                    inline=False
                )

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la vérification: {e}")

    @commands.command(name="refresh_embeds")
    @commands.has_permissions(administrator=True)
    async def refresh_embeds(self, ctx):
        """Force la mise à jour de tous les embeds de surveillance avec les noms d'utilisateur actuels."""
        if not self.sheet:
            await ctx.send("❌ Google Sheets non configuré.")
            return

        try:
            await ctx.send("🔄 Mise à jour forcée de tous les embeds en cours...")

            # Recharger les données depuis Google Sheets
            await self.refresh_monitored_scenes()

            updated_count = 0
            failed_count = 0

            for channel_id, scene_data in self.monitored_scenes.items():
                try:
                    # Récupérer le canal
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel:
                        channel = await self.bot.fetch_channel(int(channel_id))

                    # Recalculer les participants et la dernière activité avec les nouveaux noms
                    start_date = datetime.fromisoformat(scene_data['start_date'])
                    participants = await self.get_channel_participants(channel, start_date)
                    last_activity = await self.get_last_activity(channel)

                    # Mettre à jour les données
                    scene_data['participants'] = json.dumps(participants)
                    if last_activity:
                        scene_data['last_activity_user'] = last_activity['user']
                        scene_data['last_activity_date'] = last_activity['date'].isoformat()

                    # Forcer la mise à jour de l'embed
                    await self.update_surveillance_message(scene_data)

                    # Mettre à jour Google Sheets
                    await self.update_scene_data(channel_id, scene_data)

                    updated_count += 1
                    logging.info(f"Embed mis à jour pour la scène: {scene_data.get('scene_name', 'Inconnu')}")

                except Exception as e:
                    failed_count += 1
                    logging.error(f"Erreur lors de la mise à jour de l'embed pour {channel_id}: {e}")

            await ctx.send(f"✅ Mise à jour terminée ! {updated_count} embeds mis à jour, {failed_count} échecs.")

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la mise à jour des embeds: {e}")
            logging.error(f"Erreur dans refresh_embeds: {e}")

    @commands.command(name="test_names")
    @commands.has_permissions(administrator=True)
    async def test_names(self, ctx, channel_id: str = None):
        """Teste la récupération des noms d'utilisateur dans un canal spécifique."""
        try:
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))
            else:
                channel = ctx.channel

            await ctx.send(f"🔍 Test des noms d'utilisateur dans {channel.mention}...")

            # Récupérer les 10 derniers messages
            test_results = []
            async for message in channel.history(limit=10):
                if not message.author.bot or message.webhook_id:  # Inclure les webhooks mais pas les autres bots
                    user_name = await self.get_user_display_name_async(message)

                    # Informations détaillées
                    if message.guild:
                        # Essayer d'abord le cache
                        member = message.guild.get_member(message.author.id)

                        # Si pas dans le cache, essayer fetch_member
                        if not member:
                            try:
                                member = await message.guild.fetch_member(message.author.id)
                            except:
                                pass

                        if member:
                            info = f"**{user_name}** (ID: {message.author.id})\n"
                            info += f"  • Nickname: `{member.nick}`\n"
                            info += f"  • Global name: `{member.global_name}`\n"
                            info += f"  • Username: `{member.name}`\n"
                            info += f"  • Display name: `{member.display_name}`\n"
                            if message.webhook_id:
                                info += f"  • Webhook: `{message.author.name}`"
                        else:
                            info = f"**{user_name}** (ID: {message.author.id}) - Membre non trouvé (cache + fetch)"
                    else:
                        info = f"**{user_name}** (ID: {message.author.id}) - Pas de serveur"

                    test_results.append(info)

            if test_results:
                # Diviser en chunks pour éviter les messages trop longs
                chunk_size = 5
                for i in range(0, len(test_results), chunk_size):
                    chunk = test_results[i:i+chunk_size]
                    embed = discord.Embed(
                        title=f"🔍 Test des noms - Partie {i//chunk_size + 1}",
                        description="\n\n".join(chunk),
                        color=0x3498db
                    )
                    await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Aucun message d'utilisateur trouvé dans ce canal.")

        except Exception as e:
            await ctx.send(f"❌ Erreur lors du test: {e}")
            logging.error(f"Erreur dans test_names: {e}")

    async def update_scene_message_id(self, channel_id: str, message_id: str):
        """Met à jour l'ID du message de surveillance dans Google Sheets."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):  # Start=2 car ligne 1 = en-tête
                record_channel_id = str(record.get('channel_id')).lstrip("'")
                clean_channel_id = str(channel_id).lstrip("'")
                if record_channel_id == clean_channel_id:
                    cell = f'H{i}'
                    formatted_id = self.format_id_for_sheets(message_id)
                    self.sheet.update(cell, formatted_id)  # Colonne H = message_id
                    written = str(self.sheet.cell(i, 8).value).lstrip("'")
                    if written != str(message_id):
                        logging.error(
                            f"Incohérence de message_id pour {channel_id}: écrit {written}, attendu {message_id}"
                        )
                    break
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de l'ID du message: {e}")

    async def update_scene_gm(self, channel_id: str, new_gm_id: str):
        """Met à jour le MJ d'une scène dans Google Sheets."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                record_channel_id = str(record.get('channel_id')).lstrip("'")
                clean_channel_id = str(channel_id).lstrip("'")
                if record_channel_id == clean_channel_id:
                    self.sheet.update(f'C{i}', self.format_id_for_sheets(new_gm_id))  # Colonne C = gm_id
                    break
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour du MJ: {e}")

    async def remove_scene_from_sheets(self, channel_id: str):
        """Supprime une scène de Google Sheets seulement (pour nettoyage)."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                if str(record.get('channel_id')) == str(channel_id):
                    self.sheet.delete_rows(i)
                    logging.info(f"Scène {channel_id} supprimée de Google Sheets")
                    break
        except Exception as e:
            logging.error(f"Erreur lors de la suppression de Google Sheets: {e}")

    async def remove_scene_surveillance(self, channel_id: str):
        """Supprime une scène de la surveillance."""
        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                record_channel_id = str(record.get('channel_id')).lstrip("'")
                clean_channel_id = str(channel_id).lstrip("'")
                if record_channel_id == clean_channel_id:
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



            records = self.sheet.get_all_records()

            found = False
            for i, record in enumerate(records, start=2):
                record_channel_id = record.get('channel_id')

                # Comparaison robuste en nettoyant les apostrophes des deux côtés
                clean_record_id = str(record_channel_id).lstrip("'")
                clean_channel_id = str(channel_id).lstrip("'")

                if clean_record_id == clean_channel_id:
                    # Mettre à jour toute la ligne (avec apostrophe pour forcer le format texte sur les IDs)
                    self.sheet.update(f'A{i}:J{i}', [[
                        self.format_id_for_sheets(scene_data['channel_id']),
                        scene_data['scene_name'],
                        self.format_id_for_sheets(scene_data['gm_id']),
                        scene_data['start_date'],
                        scene_data['participants'],
                        scene_data['last_activity_user'],
                        scene_data['last_activity_date'],
                        self.format_id_for_sheets(scene_data['message_id']),
                        scene_data['channel_type'],
                        self.format_id_for_sheets(scene_data['guild_id'])
                    ]])
                    logging.info(f"Données mises à jour dans Google Sheets ligne {i}")
                    found = True
                    break

            if not found:
                # Canal non trouvé dans Google Sheets - l'ajouter automatiquement
                logging.warning(f"Canal {channel_id} non trouvé dans Google Sheets - ajout automatique")
                try:
                    self.sheet.append_row([
                        self.format_id_for_sheets(scene_data['channel_id']),
                        scene_data['scene_name'],
                        self.format_id_for_sheets(scene_data['gm_id']),
                        scene_data['start_date'],
                        scene_data['participants'],
                        scene_data['last_activity_user'],
                        scene_data['last_activity_date'],
                        self.format_id_for_sheets(scene_data['message_id']),
                        scene_data['channel_type'],
                        self.format_id_for_sheets(scene_data['guild_id'])
                    ])
                    logging.info(f"Canal {channel_id} ajouté automatiquement à Google Sheets")
                except Exception as add_error:
                    logging.error(f"Erreur lors de l'ajout automatique du canal {channel_id}: {add_error}")

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour des données: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

    async def update_all_scenes(self):
        """Met à jour toutes les scènes surveillées."""
        logging.info(f"Mise à jour de {len(self.monitored_scenes)} scènes surveillées")

        for channel_id, scene_data in self.monitored_scenes.items():
            try:
                # Convertir l'ID en cas de notation scientifique
                clean_channel_id = self.convert_scientific_to_int(channel_id)
                logging.info(f"Mise à jour de la scène {clean_channel_id} ({scene_data.get('scene_name', 'Nom inconnu')})")

                try:
                    channel = self.bot.get_channel(int(clean_channel_id))
                    if not channel:
                        # Essayer de récupérer via l'API
                        channel = await self.bot.fetch_channel(int(clean_channel_id))
                except ValueError as ve:
                    logging.error(f"ID de canal invalide '{clean_channel_id}': {ve}")
                    continue
                except discord.NotFound:
                    # Canal non trouvé - peut être supprimé ou inaccessible
                    logging.warning(f"Canal {clean_channel_id} ({scene_data.get('scene_name', 'Inconnu')}) non trouvé (404) - vérifiez les permissions ou si le canal existe")
                    continue
                except discord.Forbidden:
                    # Pas de permissions pour accéder au canal
                    logging.warning(f"Canal {clean_channel_id} ({scene_data.get('scene_name', 'Inconnu')}) inaccessible - permissions insuffisantes")
                    continue
                except Exception as e:
                    logging.error(f"Impossible de récupérer le canal {clean_channel_id} ({scene_data.get('scene_name', 'Inconnu')}): {e}")
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
                await asyncio.sleep(UPDATE_SLEEP_SECONDS)

            except Exception as e:
                logging.error(f"Erreur lors de la mise à jour de la scène {channel_id}: {e}")
                import traceback
                logging.error(f"Traceback: {traceback.format_exc()}")

        await self.reorder_surveillance_messages()
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

    async def reorder_surveillance_messages(self):
        """Réordonne les messages de surveillance par date d'activité."""
        try:
            surveillance_channel = self.bot.get_channel(SURVEILLANCE_CHANNEL_ID)
            if not surveillance_channel:
                return

            scenes = list(self.monitored_scenes.values())
            if not scenes:
                return

            # Filtrer les doublons de channel_id ou d'IDs de message
            seen_channels = set()
            seen_ids = set()
            unique_scenes = []
            for scene in scenes:
                channel_id = scene.get('channel_id')
                msg_id = scene.get('message_id')
                if channel_id in seen_channels or (msg_id and msg_id in seen_ids):
                    logging.warning(f"Scène dupliquée ignorée: {channel_id} ({msg_id})")
                    continue
                if channel_id:
                    seen_channels.add(channel_id)
                if msg_id:
                    seen_ids.add(msg_id)
                unique_scenes.append(scene)
            scenes = unique_scenes

            def activity_date(scene: dict) -> datetime:
                date_str = scene.get('last_activity_date') or scene.get('start_date')
                if not date_str:
                    return datetime.fromtimestamp(0, tz=self.paris_tz)
                try:
                    dt = datetime.fromisoformat(date_str)
                    if dt.tzinfo is None:
                        dt = self.paris_tz.localize(dt)
                    return dt
                except Exception:
                    return datetime.fromtimestamp(0, tz=self.paris_tz)

            scenes.sort(key=activity_date, reverse=True)

            existing_messages = [
                m async for m in surveillance_channel.history(limit=None, oldest_first=True)
                if not m.pinned
            ]

            used_message_ids = set()

            for scene, message in zip(scenes, existing_messages):
                try:
                    embed = await self.create_surveillance_embed(scene)
                    view = SceneSurveillanceView(self, scene)
                    await message.edit(embed=embed, view=view)
                    used_message_ids.add(message.id)
                    if scene.get('message_id') != str(message.id):
                        scene['message_id'] = str(message.id)
                except Exception as e:
                    logging.error(f"Erreur lors de la modification du message: {e}")

            if len(scenes) > len(existing_messages):
                for scene in scenes[len(existing_messages):]:
                    try:
                        embed = await self.create_surveillance_embed(scene)
                        view = SceneSurveillanceView(self, scene)
                        new_message = await surveillance_channel.send(embed=embed, view=view)
                        scene['message_id'] = str(new_message.id)
                        used_message_ids.add(new_message.id)
                        await self.update_scene_message_id(scene['channel_id'], scene['message_id'])
                        await asyncio.sleep(1)
                    except Exception as e:
                        logging.error(f"Erreur lors de la création du message: {e}")

            elif len(existing_messages) > len(scenes):
                for message in existing_messages[len(scenes):]:
                    try:
                        await message.delete()
                    except Exception:
                        pass

            # Nettoyage des messages orphelins
            async for message in surveillance_channel.history(limit=None):
                if message.id not in used_message_ids and not message.pinned:
                    try:
                        await message.delete()
                    except Exception:
                        pass

        except Exception as e:
            logging.error(f"Erreur dans reorder_surveillance_messages: {e}")

    async def notify_inactive_scene(self, scene_data: dict):
        """Notifie le MJ d'une scène inactive depuis 7 jours."""
        try:
            gm = self.bot.get_user(int(scene_data['gm_id']))
            if gm:
                # Calculer le temps exact d'inactivité
                last_activity_date = scene_data.get('last_activity_date', '')
                now = datetime.now(self.paris_tz)

                embed = discord.Embed(
                    title="⚠️ Scène Inactive",
                    description=f"La scène **{scene_data['scene_name']}** n'a pas eu d'activité depuis 7 jours.",
                    color=0xf39c12,
                    timestamp=now
                )

                if last_activity_date:
                    try:
                        activity_date = datetime.fromisoformat(last_activity_date)
                        if activity_date.tzinfo is None:
                            activity_date = self.paris_tz.localize(activity_date)

                        time_diff = now - activity_date
                        days_inactive = time_diff.days

                        embed.add_field(
                            name="Dernière activité",
                            value=f"{activity_date.strftime('%d/%m/%Y à %H:%M')}\n({days_inactive} jours d'inactivité)",
                            inline=False
                        )

                        # Ajouter des infos de debug
                        embed.add_field(
                            name="🔍 Informations de debug",
                            value=f"Canal: <#{scene_data['channel_id']}>\nDernière vérification: {now.strftime('%d/%m/%Y à %H:%M')}",
                            inline=False
                        )

                    except Exception as date_error:
                        logging.error(f"Erreur lors du parsing de la date d'activité: {date_error}")
                        embed.add_field(
                            name="Dernière activité",
                            value=f"Erreur de format: {last_activity_date}",
                            inline=False
                        )

                await gm.send(embed=embed)
                logging.info(f"Notification d'inactivité envoyée pour la scène {scene_data['scene_name']}")

        except Exception as e:
            logging.error(f"Erreur lors de la notification d'inactivité: {e}")

    async def flush_channel_update(self, channel_id: str):
        """Applique les mises à jour différées pour un canal."""
        scene_data = self.pending_updates.get(channel_id)
        if not scene_data:
            return
        try:
            start_date = datetime.fromisoformat(scene_data['start_date'])
            channel = self.bot.get_channel(int(channel_id))
            participants = await self.get_channel_participants(channel, start_date)
            scene_data['participants'] = json.dumps(participants)
            await self.update_scene_data(channel_id, scene_data)
            await self.update_surveillance_message(scene_data)
            self.monitored_scenes[channel_id] = scene_data
        except Exception as e:
            logging.error(f"Erreur lors du rafraîchissement différé: {e}")
        finally:
            self.pending_update_counts[channel_id] = 0
            self.pending_updates.pop(channel_id, None)

    @tasks.loop(minutes=UPDATE_INTERVAL_MINUTES)
    async def process_pending_updates(self):
        """Traite périodiquement les mises à jour en attente."""
        if not self.pending_updates:
            return
        for channel_id in list(self.pending_updates.keys()):
            await self.flush_channel_update(channel_id)
        await self.reorder_surveillance_messages()

    @process_pending_updates.before_loop
    async def before_process_pending_updates(self):
        await self.bot.wait_until_ready()

    def cleanup_old_notifications(self, current_time: Optional[float] = None) -> None:
        """Supprime les entrées périmées du cache anti-spam."""
        if current_time is None:
            current_time = time.time()
        for channel_id in list(self.last_notifications.keys()):
            cache = self.last_notifications[channel_id]
            self.last_notifications[channel_id] = {
                uid: ts for uid, ts in cache.items()
                if current_time - ts <= NOTIFICATION_RETENTION_SECONDS
            }
            if not self.last_notifications[channel_id]:
                del self.last_notifications[channel_id]

        for channel_id in list(self.last_channel_notifications.keys()):
            if current_time - self.last_channel_notifications[channel_id] > NOTIFICATION_RETENTION_SECONDS:
                del self.last_channel_notifications[channel_id]

    @tasks.loop(hours=1)
    async def cleanup_notifications(self):
        """Nettoie périodiquement le cache anti-spam."""
        self.cleanup_old_notifications()

    @cleanup_notifications.before_loop
    async def before_cleanup_notifications(self):
        await self.bot.wait_until_ready()

    def should_notify_gm(self, channel_id: str, user_id: int) -> bool:
        """Détermine si le MJ doit être notifié en fonction de l'anti-spam."""
        current_time = time.time()

        # Nettoyer les notifications expirées
        self.cleanup_old_notifications(current_time)

        # Initialiser le cache pour ce canal si nécessaire
        channel_cache = self.last_notifications.setdefault(channel_id, {})
        # Vérifier la dernière notification pour cet utilisateur
        last_notification = channel_cache.get(user_id, 0)

        # Déterminer le dernier utilisateur notifié
        last_user_notified = max(channel_cache, key=channel_cache.get, default=None)

        # Vérifier l'intervalle global par salon
        last_channel_notif = self.last_channel_notifications.get(channel_id, 0)
        if (
            current_time - last_channel_notif
            < CHANNEL_NOTIFICATION_INTERVAL_MINUTES * 60
        ):
            return False

        if last_user_notified != user_id:
            # Utilisateur différent, notifier immédiatement
            channel_cache[user_id] = current_time
            self.last_channel_notifications[channel_id] = current_time
            return True

        # Même utilisateur, vérifier l'intervalle de 10 minutes (600 secondes)
        if current_time - last_notification >= 600:
            channel_cache[user_id] = current_time
            self.last_channel_notifications[channel_id] = current_time
            return True

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Écoute les nouveaux messages dans les canaux surveillés."""
        if message.author == self.bot.user:
            return

        channel_id = str(message.channel.id)
        if channel_id not in self.monitored_scenes:
            return

        # Vérifier que le message n'a pas été remplacé par un webhook (ex: Tupperbox)
        if message.webhook_id is None:
            await asyncio.sleep(1)
            try:
                await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return

        try:
            scene_data = self.monitored_scenes[channel_id]

            # Mettre à jour la dernière activité (TOUJOURS, même pour Maître du Jeu)
            user_name = await self.get_user_display_name_async(message)

            scene_data['last_activity_user'] = user_name
            scene_data['last_activity_date'] = message.created_at.astimezone(self.paris_tz).isoformat()

            # Ajouter aux mises à jour en attente
            self.pending_updates[channel_id] = scene_data
            self.pending_update_counts[channel_id] = self.pending_update_counts.get(channel_id, 0) + 1

            # Rafraîchir immédiatement si le seuil est atteint
            if self.pending_update_counts[channel_id] >= UPDATE_BATCH_SIZE:
                await self.flush_channel_update(channel_id)
                await self.reorder_surveillance_messages()

            # Notifier le MJ avec système anti-spam (SAUF si c'est un message de Maître du Jeu)
            if not self.is_game_master_message(message):
                gm = self.bot.get_user(int(scene_data['gm_id']))
                if gm and gm.id != message.author.id:
                    # Vérifier si on doit notifier (anti-spam)
                    if self.should_notify_gm(channel_id, message.author.id):
                        try:
                            embed = discord.Embed(
                                title="📝 Nouvelle activité",
                                description=f"Nouveau message dans **{scene_data['scene_name']}**",
                                color=0x2ecc71,
                                timestamp=message.created_at
                            )
                            embed.add_field(name="Auteur", value=user_name, inline=True)
                            embed.add_field(name="Canal", value=message.channel.mention, inline=True)
                            embed.add_field(name="Aperçu", value=message.content[:100] + "..." if len(message.content) > 100 else message.content, inline=False)

                            await gm.send(embed=embed)
                        except Exception as e:
                            logging.error(f"Erreur lors de l'envoi de notification au MJ: {e}")

        except Exception as e:
            logging.error(f"Erreur lors du traitement du message: {e}")

async def setup(bot):
    await bot.add_cog(SurveillanceScene(bot))
