import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv
import sys
import traceback
import asyncio
import aiohttp
import signal

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def log_message(self, format, *args):
        logger.info(f"Health check: {format%args}")

def start_http_server():
    try:
        port = int(os.environ.get("PORT", 10000))
        logger.info(f"Starting HTTP server on port {port}")
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")

class CustomBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.initial_extensions = [
            'cogs.inventaire',
            'cogs.RPTracker',
            'cogs.bump',
            'cogs.vocabulaire',
            'cogs.souselement',
            'cogs.ticket',
            'cogs.validation'
        ]

    async def setup_hook(self):
        # Charger les cogs
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}")
                traceback.print_exc()
        
        # Synchroniser les commandes
        await self.tree.sync()

    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def close(self):
        logger.info("Shutting down bot...")
        await super().close()

async def start_bot():
    bot = CustomBot()
    
    # Gérer l'arrêt proprement
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        asyncio.create_task(bot.close())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Démarrer le serveur HTTP
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            async with bot:
                await bot.start(os.getenv('DISCORD_TOKEN'))
                break
        except (discord.errors.HTTPException, aiohttp.ClientConnectorError) as e:
            retry_count += 1
            logger.error(f"Connection error (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                await asyncio.sleep(min(5 * retry_count, 30))  # Backoff exponentiel
            else:
                logger.critical("Max retries reached, shutting down")
                break
        except Exception as e:
            logger.critical(f"Unexpected error: {e}")
            break

def main():
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
