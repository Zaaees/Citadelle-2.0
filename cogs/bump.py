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
        
        # Flag pour gérer l'attente du bot ready dans la task
        self.bot_ready_waited = False
        
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
        """Initialisation asynchrone sécurisée avec timeout et gestion d'erreurs robuste."""
        if self.initialization_complete:
            self.logger.info("Initialisation déjà terminée")
            return
            
        self.logger.info("🔄 Début de l'initialisation du cog Bump...")
        
        try:
            # Vérifier les prérequis
            if not self.SERVICE_ACCOUNT_JSON or not self.GOOGLE_SHEET_ID:
                self.logger.warning("Configuration Google Sheets manquante, fonctionnement en mode dégradé")
                self.initialization_complete = True
                self._start_check_bump_task()
                return
                
            # Créer le service Google Sheets avec timeout
            def _build_service():
                self.logger.info("🔧 Création du service Google Sheets...")
                credentials = service_account.Credentials.from_service_account_info(
                    self.SERVICE_ACCOUNT_JSON,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
                service = build('sheets', 'v4', credentials=credentials)
                return service.spreadsheets()
            
            # Timeout de 10 secondes pour la création du service
            try:
                self.sheet = await asyncio.wait_for(
                    asyncio.to_thread(_build_service),
                    timeout=10.0
                )
                self.logger.info("✅ Service Google Sheets initialisé")
            except asyncio.TimeoutError:
                self.logger.error("❌ Timeout lors de l'initialisation Google Sheets (10s)")
                self.initialization_complete = True
                self._start_check_bump_task()
                return

            # Charger les données initiales avec timeout global
            try:
                self.logger.info("📊 Chargement des données initiales...")
                load_tasks = asyncio.gather(
                    self.load_last_bump(),
                    self.load_last_reminder(),
                    return_exceptions=True
                )
                results = await asyncio.wait_for(load_tasks, timeout=15.0)
                
                # Traiter les résultats
                if isinstance(results[0], Exception):
                    self.logger.error(f"Erreur lors du chargement last_bump: {results[0]}")
                    self.last_bump = datetime.min
                else:
                    self.last_bump = results[0]
                    
                if isinstance(results[1], Exception):
                    self.logger.error(f"Erreur lors du chargement last_reminder: {results[1]}")
                    self.last_reminder = datetime.min
                else:
                    self.last_reminder = results[1]
                    
                self.logger.info(f"✅ Données chargées: bump={self.last_bump}, reminder={self.last_reminder}")
            except asyncio.TimeoutError:
                self.logger.error("❌ Timeout lors du chargement des données (15s), utilisation des valeurs par défaut")
                self.last_bump = datetime.min
                self.last_reminder = datetime.min
            except Exception as e:
                self.logger.error(f"Erreur lors du chargement des données: {e}")
                self.last_bump = datetime.min
                self.last_reminder = datetime.min
                
            self.initialization_complete = True
            self.logger.info("✅ Initialisation du cog Bump terminée")
            
        except Exception as e:
            self.logger.error(f"❌ Erreur critique d'initialisation bump: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.initialization_complete = True  # Marquer comme terminé même en cas d'erreur

        # Démarrer la tâche dans tous les cas
        self._start_check_bump_task()
        
    def _start_check_bump_task(self):
        """Démarrer la tâche check_bump de manière sécurisée."""
        try:
            if not self.check_bump.is_running():
                self.check_bump.start()
                self.logger.info("✅ Tâche check_bump démarrée")
            else:
                self.logger.info("ℹ️ Tâche check_bump déjà active")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du démarrage de check_bump: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    def setup_google_sheets(self):
        credentials = service_account.Credentials.from_service_account_info(
            self.SERVICE_ACCOUNT_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service.spreadsheets()

    async def load_last_bump(self):
        """Charger la dernière date de bump avec gestion d'erreurs robuste et timeout."""
        if not self.sheet:
            self.logger.warning("Sheet non initialisé, utilisation de la valeur par défaut")
            return datetime.min
            
        for attempt in range(3):  # Retry up to 3 times
            try:
                self.logger.debug(f"📊 Tentative {attempt + 1}/3 de chargement last_bump...")
                
                def _load_bump():
                    request = self.sheet.values().get(
                        spreadsheetId=self.GOOGLE_SHEET_ID,
                        range='A2'
                    )
                    return request.execute()
                
                # Timeout de 5 secondes par tentative
                result = await asyncio.wait_for(
                    asyncio.to_thread(_load_bump),
                    timeout=5.0
                )
                
                values = result.get('values', [[datetime.min.isoformat()]])
                
                if values and values[0]:
                    bump_date = datetime.fromisoformat(values[0][0])
                    self.logger.debug(f"✅ Last_bump chargé: {bump_date}")
                    return bump_date
                else:
                    self.logger.debug("ℹ️ Aucune donnée last_bump, utilisation de datetime.min")
                    return datetime.min
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"⏰ Timeout lors du chargement last_bump (tentative {attempt + 1}/3)")
                if attempt < 2:
                    await asyncio.sleep(1)
            except HttpError as e:
                if e.resp.status == 503:  # Service unavailable
                    self.logger.warning(f"🔄 Google Sheets API indisponible (tentative {attempt + 1}/3). Retry...")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"❌ Erreur HTTP Google Sheets lors du chargement last_bump: {str(e)}")
                    break
            except (ConnectionError, OSError) as e:
                # Erreurs réseau/SSL temporaires
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['ssl', 'connection', 'network', 'timeout', 'decryption']):
                    self.logger.warning(f"🔄 Erreur réseau/SSL temporaire (tentative {attempt + 1}/3): {e}")
                    if attempt < 2:
                        delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        await asyncio.sleep(delay)
                        continue
                else:
                    self.logger.error(f"❌ Erreur réseau critique lors du chargement last_bump: {e}")
                    break
            except Exception as e:
                # Vérifier si c'est une erreur SSL dans l'exception générale
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['ssl', 'decryption', 'bad record mac', 'handshake']):
                    self.logger.warning(f"🔄 Erreur SSL temporaire (tentative {attempt + 1}/3): {e}")
                    if attempt < 2:
                        delay = 2 ** attempt  # Exponential backoff
                        await asyncio.sleep(delay)
                        continue
                else:
                    self.logger.error(f"❌ Erreur inattendue lors du chargement last_bump: {e}")
                    break
                
        # Si toutes les tentatives échouent, retourner valeur par défaut
        self.logger.warning("❌ Impossible de charger last_bump après 3 tentatives, utilisation de datetime.min")
        return datetime.min

    async def save_last_bump(self):
        if not self.sheet:
            self.logger.warning("Sheet non initialisé; report de save_last_bump")
            return
            
        try:
            def _save_bump():
                request = self.sheet.values().update(
                    spreadsheetId=self.GOOGLE_SHEET_ID,
                    range='A2',
                    valueInputOption='RAW',
                    body={'values': [[self.last_bump.isoformat()]]}
                )
                return request.execute()
            
            # Timeout de 10 secondes pour la sauvegarde
            await asyncio.wait_for(
                asyncio.to_thread(_save_bump),
                timeout=10.0
            )
            self.logger.debug(f"✅ Last_bump sauvegardé: {self.last_bump}")
            
        except asyncio.TimeoutError:
            self.logger.error("⏰ Timeout lors de la sauvegarde last_bump (10s)")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la sauvegarde last_bump: {e}")

    async def load_last_reminder(self):
        """Charger la dernière date de reminder avec gestion d'erreurs robuste et timeout."""
        if not self.sheet:
            self.logger.warning("Sheet non initialisé, utilisation de la valeur par défaut")
            return datetime.min
            
        for attempt in range(3):  # Retry up to 3 times
            try:
                self.logger.debug(f"📊 Tentative {attempt + 1}/3 de chargement last_reminder...")
                
                def _load_reminder():
                    request = self.sheet.values().get(
                        spreadsheetId=self.GOOGLE_SHEET_ID,
                        range='B2'
                    )
                    return request.execute()
                
                # Timeout de 5 secondes par tentative
                result = await asyncio.wait_for(
                    asyncio.to_thread(_load_reminder),
                    timeout=5.0
                )
                
                values = result.get('values', [[datetime.min.isoformat()]])
                
                if values and values[0]:
                    reminder_date = datetime.fromisoformat(values[0][0])
                    self.logger.debug(f"✅ Last_reminder chargé: {reminder_date}")
                    return reminder_date
                else:
                    self.logger.debug("ℹ️ Aucune donnée last_reminder, utilisation de datetime.min")
                    return datetime.min
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"⏰ Timeout lors du chargement last_reminder (tentative {attempt + 1}/3)")
                if attempt < 2:
                    await asyncio.sleep(1)
            except HttpError as e:
                if e.resp.status == 503:  # Service unavailable
                    self.logger.warning(f"🔄 Google Sheets API indisponible (tentative {attempt + 1}/3). Retry...")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"❌ Erreur HTTP Google Sheets lors du chargement last_reminder: {str(e)}")
                    break
            except (ConnectionError, OSError) as e:
                # Erreurs réseau/SSL temporaires
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['ssl', 'connection', 'network', 'timeout', 'decryption']):
                    self.logger.warning(f"🔄 Erreur réseau/SSL temporaire (tentative {attempt + 1}/3): {e}")
                    if attempt < 2:
                        delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        await asyncio.sleep(delay)
                        continue
                else:
                    self.logger.error(f"❌ Erreur réseau critique lors du chargement last_reminder: {e}")
                    break
            except Exception as e:
                # Vérifier si c'est une erreur SSL dans l'exception générale
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['ssl', 'decryption', 'bad record mac', 'handshake']):
                    self.logger.warning(f"🔄 Erreur SSL temporaire (tentative {attempt + 1}/3): {e}")
                    if attempt < 2:
                        delay = 2 ** attempt  # Exponential backoff
                        await asyncio.sleep(delay)
                        continue
                else:
                    self.logger.error(f"❌ Erreur inattendue lors du chargement last_reminder: {e}")
                    break
                
        # Si toutes les tentatives échouent, retourner valeur par défaut
        self.logger.warning("❌ Impossible de charger last_reminder après 3 tentatives, utilisation de datetime.min")
        return datetime.min

    async def save_last_reminder(self):
        if not self.sheet:
            self.logger.warning("Sheet non initialisé; report de save_last_reminder")
            return
            
        try:
            def _save_reminder():
                request = self.sheet.values().update(
                    spreadsheetId=self.GOOGLE_SHEET_ID,
                    range='B2',
                    valueInputOption='RAW',
                    body={'values': [[self.last_reminder.isoformat()]]}
                )
                return request.execute()
            
            # Timeout de 10 secondes pour la sauvegarde
            await asyncio.wait_for(
                asyncio.to_thread(_save_reminder),
                timeout=10.0
            )
            self.logger.debug(f"✅ Last_reminder sauvegardé: {self.last_reminder}")
            
        except asyncio.TimeoutError:
            self.logger.error("⏰ Timeout lors de la sauvegarde last_reminder (10s)")
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la sauvegarde last_reminder: {e}")

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
            # Attendre que le bot soit prêt seulement au premier run
            if not self.bot_ready_waited:
                self.logger.info("🔄 Attente que le bot soit prêt (premier run)...")
                try:
                    await asyncio.wait_for(self.bot.wait_until_ready(), timeout=60.0)
                    self.logger.info("✅ Bot prêt !")
                except asyncio.TimeoutError:
                    self.logger.warning("⚠️ Timeout d'attente bot ready (60s), continuation forcée")
                finally:
                    self.bot_ready_waited = True
                    
                # Vérifier que l'initialisation est terminée
                if not self.initialization_complete:
                    self.logger.warning("⚠️ Initialisation non terminée, attente...")
                    for i in range(12):  # 60 secondes max (12 * 5s)
                        if self.initialization_complete:
                            break
                        await asyncio.sleep(5)
                        if i % 2 == 0:  # Log toutes les 10 secondes
                            self.logger.info(f"🕰️ Attente initialisation... ({(i+1)*5}s)")
                    
                    if not self.initialization_complete:
                        self.logger.error("❌ Initialisation non terminée après 60s, continuation forcée")
                
                self.logger.info("🏁 Check bump opérationnel !")
            
            now = datetime.now()
            time_since_last_bump = now - self.last_bump
            time_since_last_reminder = now - self.last_reminder
            
            self.logger.info(f"Checking bump - Last bump: {time_since_last_bump}, Last reminder: {time_since_last_reminder}")
            
            # Vérification pour 24 heures
            if time_since_last_bump >= timedelta(hours=24):
                if self.last_reminder < self.last_bump:
                    channel = self.bot.get_channel(self.channel_id)
                    if channel:
                        await channel.send("⚠️ Ça fait 24h ! N'oubliez pas de bump le serveur")
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
        """Préparation avant démarrage de la task - pas de blocage pour éviter les deadlocks."""
        self.logger.info("🏁 Préparation de la tâche check_bump (pas de blocage)")

async def setup(bot):
    """Setup du cog avec initialisation sécurisée et timeout."""
    import logging
    logger = logging.getLogger('bump_cog')
    
    logger.info("🔄 Début du setup du cog Bump...")
    
    try:
        cog = Bump(bot)
        await bot.add_cog(cog)
        logger.info("✅ Cog Bump ajouté au bot")
        
        # Démarrer l'initialisation asynchrone avec timeout
        init_task = asyncio.create_task(cog._async_setup())
        
        # Ne pas attendre l'initialisation, laisser le bot continuer
        logger.info("✅ Tâche d'initialisation asynchrone démarrée")
        
        # Optionnel: surveiller l'initialisation en arrière-plan
        async def _monitor_init():
            try:
                await asyncio.wait_for(init_task, timeout=60.0)
                logger.info("✅ Initialisation du cog Bump terminée avec succès")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Timeout d'initialisation du cog Bump (60s), mais le bot continue")
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'initialisation du cog Bump: {e}")
                
        asyncio.create_task(_monitor_init())
        
        logger.info("✅ Cog bump chargé avec succès")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du setup du cog Bump: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
