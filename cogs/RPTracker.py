import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pytz
import os
import asyncio
import gspread
from google.oauth2 import service_account

class RPTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone('Europe/Paris')
        self.channel_id = 1214092904595980299
        self.message_id = 1266749233155936348
        self.categories = ["[RP] La Citadelle Extérieure", "[RP] L'Académie", "[RP] Chronologie Temporelle"]
        
        # Configuration Google Sheets
        self.credentials = service_account.Credentials.from_service_account_info(
            eval(os.getenv('SERVICE_ACCOUNT_JSON')),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.gc = gspread.authorize(self.credentials)
        self.sheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_ACTIVITE')).sheet1
        
        self.update_loop.start()

    @tasks.loop(hours=1)
    async def update_loop(self):
        print("Exécution de la boucle de mise à jour")
        try:
            await self.check_and_update()
            print("Mise à jour terminée avec succès")
        except Exception as e:
            print(f"Erreur dans la boucle de mise à jour: {e}")
            # Attendre avant de continuer pour éviter les boucles d'erreurs
            await asyncio.sleep(300)  # 5 minutes

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)

    @update_loop.error
    async def update_loop_error(self, error):
        """Gère les erreurs de la tâche update_loop."""
        logging.error(f"❌ Erreur critique dans update_loop: {error}")
        # Notifier un canal Discord spécifique
        channel = self.bot.get_channel(1230946716849799381)
        if channel:
            try:
                await channel.send(f"❌ **Erreur critique dans la tâche RPTracker** :\n```{error}```")
            except Exception as notify_error:
                logging.error(f"Erreur lors de la notification Discord : {notify_error}")
        # Redémarrer la tâche après une erreur
        await asyncio.sleep(600)  # Attendre 10 minutes avant de redémarrer
        try:
            if not self.update_loop.is_running():
                self.update_loop.restart()
                logging.info("✅ Tâche update_loop redémarrée après erreur critique")
        except Exception as restart_error:
            logging.error(f"❌ Erreur lors du redémarrage de update_loop: {restart_error}")

    async def cog_unload(self):
        """Nettoie les ressources lors du déchargement du cog."""
        try:
            if self.update_loop.is_running():
                self.update_loop.cancel()
            print("🧹 Tâche du cog RPTracker arrêtée")
        except Exception as e:
            print(f"❌ Erreur lors de l'arrêt de la tâche RPTracker: {e}")

    async def cog_load(self):
        print("Cog RPTracker en cours de chargement")
        await self.initial_setup()

    async def initial_setup(self):
        print("Début du setup initial")
        await self.check_and_update()
        print("Setup initial terminé")

    async def check_and_update(self):
        print("Début de check_and_update")
        await self.perform_update()
        print("Fin de check_and_update")

    async def update_sheet_timestamp(self):
        try:
            now = datetime.now(self.paris_tz)
            print(f"Tentative de mise à jour du sheet avec timestamp: {now.isoformat()}")
            self.sheet.update('A1', [['last_update', now.isoformat()]])
            print("Mise à jour du sheet réussie")
        except Exception as e:
            print(f"Erreur lors de la mise à jour du sheet: {e}")

    async def perform_update(self):
        print("Début de perform_update")
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            print("Canal non trouvé")
            return

        try:
            message = await channel.fetch_message(self.message_id)
            print("Message trouvé")
        except discord.NotFound:
            print("Message non trouvé")
            return

        recent_channels, old_channels = await self.get_active_channels()

        embed = discord.Embed(title="Salons RP actifs ces 7 derniers jours", color=0x6d5380)
    
        if recent_channels:
            recent_content = "\n".join([f"• {channel.mention} - {self.format_time_ago(last_activity)}" for channel, last_activity in recent_channels])
            embed.add_field(name="Récents", value=recent_content, inline=False)
        else:
            embed.add_field(name="Récents", value="Aucun salon récent", inline=False)

        if old_channels:
            old_content = "\n".join([f"• {channel.mention} - {self.format_time_ago(last_activity)}" for channel, last_activity in old_channels])
            embed.add_field(name="Anciens", value=old_content, inline=False)
        else:
            embed.add_field(name="Anciens", value="Aucun salon ancien", inline=False)

        now = datetime.now(self.paris_tz)
        embed.set_footer(text=f"Dernière mise à jour : {now.strftime('%d/%m/%Y à %H:%M')}")

        await message.edit(content=None, embed=embed)
        await self.update_sheet_timestamp()

    async def get_active_channels(self):
        recent_channels = []
        old_channels = []
        now = datetime.now(self.paris_tz)

        for guild in self.bot.guilds:
            for category in guild.categories:
                if category.name in self.categories:
                    for channel in category.channels:
                        try:
                            if isinstance(channel, discord.TextChannel):
                                last_message = await asyncio.wait_for(self.get_last_message(channel), timeout=10.0)
                                if last_message:
                                    self.add_channel_to_list(channel, last_message, now, recent_channels, old_channels)
                            
                                for thread in channel.threads:
                                    thread_last_message = await asyncio.wait_for(self.get_last_message(thread), timeout=10.0)
                                    if thread_last_message:
                                        self.add_channel_to_list(thread, thread_last_message, now, recent_channels, old_channels)
                        
                            elif isinstance(channel, discord.ForumChannel):
                                threads = [thread async for thread in channel.archived_threads()]
                                threads.extend(channel.threads)
                                for thread in threads:
                                    thread_last_message = await asyncio.wait_for(self.get_last_message(thread), timeout=10.0)
                                    if thread_last_message:
                                        self.add_channel_to_list(thread, thread_last_message, now, recent_channels, old_channels)
                    
                        except asyncio.TimeoutError:
                            pass
                        except Exception as e:
                            print(f"Erreur lors de la vérification du canal {channel.name}: {e}")

        recent_channels.sort(key=lambda x: x[1], reverse=True)
        old_channels.sort(key=lambda x: x[1], reverse=True)
        return recent_channels, old_channels

    def add_channel_to_list(self, channel, last_message, now, recent_channels, old_channels):
        time_diff = now - last_message.created_at.astimezone(self.paris_tz)
        if time_diff < timedelta(days=1):
            recent_channels.append((channel, last_message.created_at))
        elif time_diff < timedelta(days=7):
            old_channels.append((channel, last_message.created_at))

    async def get_last_message(self, channel):
        try:
            if isinstance(channel, discord.TextChannel):
                async for message in channel.history(limit=1):
                    return message
            elif isinstance(channel, discord.ForumChannel):
                threads = [thread async for thread in channel.archived_threads()]
                threads.extend(channel.threads)
                if threads:
                    latest_thread = max(threads, key=lambda t: t.last_message_id or 0)
                    return await self.get_last_message(latest_thread)
            elif isinstance(channel, discord.Thread):
                async for message in channel.history(limit=1):
                    return message
        except discord.errors.Forbidden:
            pass
        except Exception:
            pass
        return None

    def format_time_ago(self, timestamp):
        now = datetime.now(self.paris_tz)
        diff = now - timestamp.astimezone(self.paris_tz)

        if diff < timedelta(hours=1):
            return f"il y a {diff.seconds // 60} minutes"
        elif diff < timedelta(days=1):
            return f"il y a {diff.seconds // 3600} heures"
        else:
            return f"il y a {diff.days} jours"

async def setup(bot):
    await bot.add_cog(RPTracker(bot))
    print("Cog RPTracker chargé avec succès")