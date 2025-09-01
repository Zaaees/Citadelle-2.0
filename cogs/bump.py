import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import logging

class Bump(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = 1031999400383348757
        self.disboard_bot_id = 302050872383242240
        
        # Configuration Google Sheets avec gestion d'erreurs
        self.setup_logging()
        self.sheet = None
        self.initialization_complete = False
        
        # Chargement différé avec valeurs par défaut sécurisées
        self.last_bump = datetime.min
        self.last_reminder = datetime.min
        
        # Initialisation sécurisée des credentials
        try:
            service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                raise ValueError("SERVICE_ACCOUNT_JSON non défini")
            self.SERVICE_ACCOUNT_JSON = json.loads(service_account_json)
            
            self.GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID_BUMP')
            if not self.GOOGLE_SHEET_ID:
                raise ValueError("GOOGLE_SHEET_ID_BUMP non défini")
                
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Erreur de configuration Google Sheets: {e}")
            self.SERVICE_ACCOUNT_JSON = None
            self.GOOGLE_SHEET_ID = None

    async def _async_setup(self):
        """Initialisation asynchrone sécurisée avec protection contre les race conditions."""
        if self.initialization_complete:
            self.logger.info("Initialisation déjà terminée")
            return
            
        try:
            # Vérifier les prérequis
            if not self.SERVICE_ACCOUNT_JSON or not self.GOOGLE_SHEET_ID:
                self.logger.error("Configuration Google Sheets manquante, fonctionnement en mode dégradé")
                self.initialization_complete = True
                return
                
            # Créer le service Google Sheets en thread
            def _build_service():
                credentials = service_account.Credentials.from_service_account_info(
                    self.SERVICE_ACCOUNT_JSON,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                service = build('sheets', 'v4', credentials=credentials)
                return service.spreadsheets()
                
            self.sheet = await asyncio.to_thread(_build_service)
            self.logger.info("✅ Service Google Sheets initialisé")

            # Charger les données initiales avec retry
            try:
                self.last_bump = await self.load_last_bump()
                self.last_reminder = await self.load_last_reminder()
                self.logger.info(f"✅ Données chargées: bump={self.last_bump}, reminder={self.last_reminder}")
            except Exception as e:
                self.logger.error(f"Erreur lors du chargement des données: {e}")
                # Continuer avec les valeurs par défaut
                
            self.initialization_complete = True
            
        except Exception as e:
            self.logger.error(f"Erreur d'initialisation bump: {e}")
            self.initialization_complete = True  # Marquer comme terminé même en cas d'erreur

        # Démarrer la tâche seulement si l'initialisation est complète
        try:
            if self.initialization_complete and not self.check_bump.is_running():
                self.check_bump.start()
                self.logger.info("✅ Tâche check_bump démarrée")
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage de check_bump: {e}")

    def setup_google_sheets(self):
        credentials = service_account.Credentials.from_service_account_info(
            self.SERVICE_ACCOUNT_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service.spreadsheets()

    async def load_last_bump(self):
        """Charger la dernière date de bump avec gestion d'erreurs robuste."""
        if not self.sheet:
            self.logger.warning("Sheet non initialisé, utilisation de la valeur par défaut")
            return datetime.min
            
        for attempt in range(3):  # Retry up to 3 times
            try:
                request = self.sheet.values().get(
                    spreadsheetId=self.GOOGLE_SHEET_ID,
                    range='A2'
                )
                result = await asyncio.to_thread(request.execute)
                values = result.get('values', [[datetime.min.isoformat()]])
                
                if values and values[0]:
                    return datetime.fromisoformat(values[0][0])
                else:
                    return datetime.min
                    
            except HttpError as e:
                if e.resp.status == 503:  # Service unavailable
                    self.logger.warning(f"Google Sheets API unavailable (attempt {attempt + 1}/3). Retrying...")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"Error loading last bump: {str(e)}")
                    break
            except Exception as e:
                self.logger.error(f"Erreur inattendue lors du chargement: {e}")
                break
                
        # Si toutes les tentatives échouent, retourner valeur par défaut
        self.logger.warning("Impossible de charger last_bump, utilisation de datetime.min")
        return datetime.min

    async def save_last_bump(self):
        if not self.sheet:
            self.logger.warning("Sheet non initialisé; report de save_last_bump")
            return
        request = self.sheet.values().update(
            spreadsheetId=self.GOOGLE_SHEET_ID,
            range='A2',
            valueInputOption='RAW',
            body={'values': [[self.last_bump.isoformat()]]}
        )
        await asyncio.to_thread(request.execute)

    async def load_last_reminder(self):
        """Charger la dernière date de reminder avec gestion d'erreurs robuste."""
        if not self.sheet:
            self.logger.warning("Sheet non initialisé, utilisation de la valeur par défaut")
            return datetime.min
            
        for attempt in range(3):  # Retry up to 3 times
            try:
                request = self.sheet.values().get(
                    spreadsheetId=self.GOOGLE_SHEET_ID,
                    range='B2'
                )
                result = await asyncio.to_thread(request.execute)
                values = result.get('values', [[datetime.min.isoformat()]])
                
                if values and values[0]:
                    return datetime.fromisoformat(values[0][0])
                else:
                    return datetime.min
                    
            except HttpError as e:
                if e.resp.status == 503:  # Service unavailable
                    self.logger.warning(f"Google Sheets API unavailable (attempt {attempt + 1}/3). Retrying...")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"Error loading last reminder: {str(e)}")
                    break
            except Exception as e:
                self.logger.error(f"Erreur inattendue lors du chargement du reminder: {e}")
                break
                
        # Si toutes les tentatives échouent, retourner valeur par défaut
        self.logger.warning("Impossible de charger last_reminder, utilisation de datetime.min")
        return datetime.min

    async def save_last_reminder(self):
        if not self.sheet:
            self.logger.warning("Sheet non initialisé; report de save_last_reminder")
            return
        request = self.sheet.values().update(
            spreadsheetId=self.GOOGLE_SHEET_ID,
            range='B2',
            valueInputOption='RAW',
            body={'values': [[self.last_reminder.isoformat()]]}
        )
        await asyncio.to_thread(request.execute)

    def setup_logging(self):
        self.logger = logging.getLogger('bump_cog')
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler('bump.log')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id == self.channel_id and message.author.id == self.disboard_bot_id:
            self.last_bump = datetime.now()
            await self.save_last_bump()
            self.check_bump.restart()

    @tasks.loop(minutes=1)
    async def check_bump(self):
        try:
            now = datetime.now()
            time_since_last_bump = now - self.last_bump
            time_since_last_reminder = now - self.last_reminder
            
            self.logger.info(f"Checking bump - Last bump: {time_since_last_bump}, Last reminder: {time_since_last_reminder}")
            
            # Vérification pour 24 heures
            if time_since_last_bump >= timedelta(hours=24):
                if self.last_reminder < self.last_bump:
                    channel = self.bot.get_channel(self.channel_id)
                    if channel:
                        await channel.send("⚠️ Ça fait 24h ! Bump le serveur enculé")
                        self.last_reminder = now
                        await self.save_last_reminder()
                        self.logger.info("24-hour reminder sent successfully")
                        return
            # Vérification normale pour 2 heures
            elif time_since_last_bump >= timedelta(hours=2) and time_since_last_reminder >= timedelta(hours=2):
                if self.last_reminder < self.last_bump:
                    channel = self.bot.get_channel(self.channel_id)
                    if channel:
                        await channel.send("Bump le serveur")
                        self.last_reminder = now
                        await self.save_last_reminder()
                        self.logger.info("Reminder sent successfully")
                    else:
                        self.logger.error(f"Channel not found: {self.channel_id}")

            time_to_next_check = min(
                timedelta(hours=2) - time_since_last_bump,
                timedelta(hours=2) - time_since_last_reminder
            )
            next_check = max(1, int(time_to_next_check.total_seconds() / 60))
            self.logger.info(f"Next check in {next_check} minutes")
            self.check_bump.change_interval(minutes=next_check)

        except Exception as e:
            self.logger.error(f"Error in check_bump: {str(e)}")
            # Attendre avant de redémarrer pour éviter les boucles infinies
            await asyncio.sleep(60)
            try:
                if not self.check_bump.is_running():
                    self.check_bump.restart()
                    self.logger.info("✅ Tâche check_bump redémarrée après erreur")
            except Exception as restart_error:
                self.logger.error(f"❌ Erreur lors du redémarrage de check_bump: {restart_error}")

    @check_bump.error
    async def check_bump_error(self, error):
        """Gère les erreurs de la tâche check_bump."""
        self.logger.error(f"❌ Erreur dans check_bump: {error}")
        # Redémarrer la tâche après une erreur
        await asyncio.sleep(120)  # Attendre 2 minutes avant de redémarrer
        try:
            if not self.check_bump.is_running():
                self.check_bump.restart()
                self.logger.info("✅ Tâche check_bump redémarrée après erreur critique")
        except Exception as restart_error:
            self.logger.error(f"❌ Erreur lors du redémarrage de check_bump: {restart_error}")

    async def cog_unload(self):
        """Nettoie les ressources lors du déchargement du cog."""
        try:
            if self.check_bump.is_running():
                self.check_bump.cancel()
            self.logger.info("🧹 Tâche du cog bump arrêtée")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'arrêt de la tâche bump: {e}")

    @commands.command(name="bumpstatus")
    @commands.has_permissions(administrator=True)
    async def bump_status(self, ctx):
        """Affiche le statut actuel du système de bump"""
        now = datetime.now()
        time_since_last_bump = now - self.last_bump
        time_since_last_reminder = now - self.last_reminder
        
        embed = discord.Embed(title="Statut du Bump", color=discord.Color.blue())
        embed.add_field(name="Dernier bump", value=f"Il y a {time_since_last_bump.seconds // 3600}h {(time_since_last_bump.seconds // 60) % 60}m")
        embed.add_field(name="Dernier rappel", value=f"Il y a {time_since_last_reminder.seconds // 3600}h {(time_since_last_reminder.seconds // 60) % 60}m")
        embed.add_field(name="Task active", value=str(self.check_bump.is_running()))
        
        await ctx.send(embed=embed)

    @check_bump.before_loop
    async def before_check_bump(self):
        """Attendre que le bot soit prêt et l'initialisation terminée."""
        await self.bot.wait_until_ready()
        # Attendre que l'initialisation soit terminée
        while not self.initialization_complete:
            await asyncio.sleep(0.5)
        self.logger.info("✅ Check bump prêt à démarrer")

    async def cog_unload(self):
        self.check_bump.cancel()

async def setup(bot):
    """Setup du cog avec initialisation sécurisée."""
    cog = Bump(bot)
    await bot.add_cog(cog)
    # Démarrer l'initialisation asynchrone de manière sécurisée
    bot.loop.create_task(cog._async_setup())
    print("Cog bump chargé avec succès")
