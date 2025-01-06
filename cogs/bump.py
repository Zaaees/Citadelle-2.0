import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import time
from googleapiclient.errors import HttpError

class Bump:
    def __init__(self, bot):
        self.bot = bot
        self.last_bump = self.load_last_bump()
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

    def setup_google_sheets(self):
        credentials = service_account.Credentials.from_service_account_info(
            self.SERVICE_ACCOUNT_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service.spreadsheets()

    def load_last_bump(self):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Your existing code to load the last bump
                result = self.service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range="A2"
                ).execute()
                return result.get('values', [])[0][0]
            except HttpError as e:
                if e.resp.status == 503:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise
                else:
                    raise

    async def setup(bot):
       await bot.add_cog(Bump(bot))

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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id == self.channel_id and message.author.id == self.disboard_bot_id:
            self.last_bump = datetime.now()
            self.save_last_bump()
            self.check_bump.restart()

    @tasks.loop(minutes=1)
    async def check_bump(self):
        now = datetime.now()
        time_since_last_bump = now - self.last_bump
        time_since_last_reminder = now - self.last_reminder
        
        if time_since_last_bump >= timedelta(hours=2) and time_since_last_reminder >= timedelta(hours=2):
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                await channel.send("Bump le serveur")
                self.last_reminder = now
                self.save_last_reminder()

        time_to_next_check = min(
            timedelta(hours=2) - time_since_last_bump,
            timedelta(hours=2) - time_since_last_reminder
        )
        self.check_bump.change_interval(minutes=max(1, int(time_to_next_check.total_seconds() / 60)))

    @check_bump.before_loop
    async def before_check_bump(self):
        await self.bot.wait_until_ready()

    def cog_unload(self):
        self.check_bump.cancel()

async def setup(bot):
    await bot.add_cog(Bump(bot))
    print("Cog bump chargé avec succès")