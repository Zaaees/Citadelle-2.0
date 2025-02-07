import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import logging

class Bump(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = 1031999400383348757
        self.disboard_bot_id = 302050872383242240
        
        # Configuration Google Sheets
        self.SERVICE_ACCOUNT_JSON = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
        self.GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID_BUMP')
        self.sheet = self.setup_google_sheets()
        
        # Chargement des données initiales
        self.last_bump = self.load_last_bump()
        self.last_reminder = self.load_last_reminder()
        self.check_bump.start()
        self.setup_logging()

    def setup_google_sheets(self):
        credentials = service_account.Credentials.from_service_account_info(
            self.SERVICE_ACCOUNT_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service.spreadsheets()

    def load_last_bump(self):
        result = self.sheet.values().get(
            spreadsheetId=self.GOOGLE_SHEET_ID,
            range='A2'
        ).execute()
        
        values = result.get('values', [[datetime.min.isoformat()]])
        return datetime.fromisoformat(values[0][0])

    def save_last_bump(self):
        self.sheet.values().update(
            spreadsheetId=self.GOOGLE_SHEET_ID,
            range='A2',
            valueInputOption='RAW',
            body={'values': [[self.last_bump.isoformat()]]}
        ).execute()

    def load_last_reminder(self):
        result = self.sheet.values().get(
            spreadsheetId=self.GOOGLE_SHEET_ID,
            range='B2'
        ).execute()
        
        values = result.get('values', [[datetime.min.isoformat()]])
        return datetime.fromisoformat(values[0][0])

    def save_last_reminder(self):
        self.sheet.values().update(
            spreadsheetId=self.GOOGLE_SHEET_ID,
            range='B2',
            valueInputOption='RAW',
            body={'values': [[self.last_reminder.isoformat()]]}
        ).execute()

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
            self.save_last_bump()
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
                channel = self.bot.get_channel(self.channel_id)
                if channel:
                    await channel.send("⚠️ Ça fait 24h ! Bump le serveur enculé")
                    self.last_reminder = now
                    self.save_last_reminder()
                    self.logger.info("24-hour reminder sent successfully")
                    return # Ajout d'un return pour éviter de passer à la vérification normale
            # Vérification normale pour 2 heures
            elif time_since_last_bump >= timedelta(hours=2) and time_since_last_reminder >= timedelta(hours=2):
                channel = self.bot.get_channel(self.channel_id)
                if channel:
                    await channel.send("Bump le serveur")
                    self.last_reminder = now
                    self.save_last_reminder()
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
            self.check_bump.restart()

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
        await self.bot.wait_until_ready()

    def cog_unload(self):
        self.check_bump.cancel()

async def setup(bot):
    await bot.add_cog(Bump(bot))
    print("Cog bump chargé avec succès")