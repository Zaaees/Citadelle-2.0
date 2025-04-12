import discord
from discord.ext import commands, tasks
import datetime
import logging
import pytz
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Configuration
CHANNEL_ID = 1038531040852953138
REMINDER_INTERVAL = datetime.timedelta(hours=2)
BUMP_INTERVAL = datetime.timedelta(hours=24)
SERVICE_ACCOUNT_JSON_PATH = os.getenv('SERVICE_ACCOUNT_JSON')
SHEET_ID = os.getenv('BUMP_SHEET_ID')
SHEET_RANGE = 'A1:B1'
TIMEZONE = pytz.timezone('Europe/Paris')

# Initialisation du logger
logger = logging.getLogger('bump')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='bump.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(handler)

class Bump(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet = self.connect_to_sheets()
        self.last_bump, self.last_reminder = self.load_timestamps()
        self.check_bump.start()

    def connect_to_sheets(self):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON_PATH)
        return build('sheets', 'v4', credentials=creds).spreadsheets()

    def load_timestamps(self):
        result = self.sheet.values().get(spreadsheetId=SHEET_ID, range=SHEET_RANGE).execute()
        values = result.get('values', [[None, None]])[0]
        last_bump = datetime.datetime.fromisoformat(values[0]) if values[0] else datetime.datetime.now(TIMEZONE)
        last_reminder = datetime.datetime.fromisoformat(values[1]) if values[1] else datetime.datetime.now(TIMEZONE)
        return last_bump, last_reminder

    def save_timestamps(self):
        values = [[self.last_bump.isoformat(), self.last_reminder.isoformat()]]
        self.sheet.values().update(
            spreadsheetId=SHEET_ID, range=SHEET_RANGE,
            valueInputOption='RAW', body={'values': values}
        ).execute()

    @tasks.loop(minutes=1)
    async def check_bump(self):
        now = datetime.datetime.now(TIMEZONE)
        channel = self.bot.get_channel(CHANNEL_ID)

        if now >= self.last_bump + REMINDER_INTERVAL and now >= self.last_reminder + REMINDER_INTERVAL:
            await channel.send("🔔 **N'oubliez pas de bump le serveur !** 🔔")
            self.last_reminder = now
            self.save_timestamps()
            logger.info('Rappel bump envoyé après 2h.')

        if now >= self.last_bump + BUMP_INTERVAL:
            await channel.send("⚠️ **Ça fait 24h que personne n'a bump, pensez à bump rapidement !**")
            self.last_reminder = now
            self.save_timestamps()
            logger.info('Rappel bump envoyé après 24h.')

    @check_bump.before_loop
    async def before_check_bump(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != CHANNEL_ID or message.author.bot:
            return

        if 'bump effectué' in message.content.lower() or 'bump done' in message.content.lower():
            self.last_bump = datetime.datetime.now(TIMEZONE)
            self.last_reminder = self.last_bump
            self.save_timestamps()
            logger.info('Bump détecté et enregistré.')

    @commands.command()
    async def bumpstatus(self, ctx):
        now = datetime.datetime.now(TIMEZONE)
        elapsed = now - self.last_bump

        days, remainder = divmod(elapsed.total_seconds(), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60

        status_message = "Dernier bump effectué il y a "
        if days > 0:
            status_message += f"{int(days)}j "
        if hours > 0 or days > 0:
            status_message += f"{int(hours)}h "
        status_message += f"{int(minutes)}m."

        await ctx.send(status_message)

    def cog_unload(self):
        self.check_bump.cancel()

async def setup(bot):
    await bot.add_cog(Bump(bot))
    logger.info("Cog bump chargé avec succès.")
