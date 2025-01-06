import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv
import sys
import traceback
import asyncio
import aiohttp

# Charger les variables d'environnement
load_dotenv()

# Serveur HTTP minimal pour Render
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

def start_http_server():
    try:
        # Render fournit PORT, sinon utiliser 10000 localement
        port = int(os.environ.get("PORT", 10000))
        print(f"Port from environment: {os.environ.get('PORT')}")
        print(f"Tentative de démarrage du serveur sur le port {port}...")
        
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"Serveur HTTP démarré avec succès sur le port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"Erreur lors du démarrage du serveur : {e}")

# Classe personnalisée pour le bot
class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            await self.load_extension(extension)
        
        # Synchroniser les commandes
        await self.tree.sync()

    async def reload_extensions(self):
        for extension in self.initial_extensions:
            try:
                await self.reload_extension(extension)
            except Exception as e:
                print(f"Erreur lors du rechargement de {extension}: {e}")
        await self.tree.sync()

    def check_role(self, interaction):
        # Implémentez votre logique de vérification de rôle ici
        return True

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                except Exception as e:
                    print(f'Failed to load extension {filename}', file=sys.stderr)
                    traceback.print_exc()

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

def main():
    # Démarrer le serveur HTTP dans un thread séparé
    threading.Thread(target=start_http_server, daemon=True).start()

    bot = MyBot()
    
    # Ajout d'une meilleure gestion des erreurs de connexion
    async def start_bot():
        try:
            async with bot:
                await bot.start(os.getenv('DISCORD_TOKEN'))
        except discord.errors.HTTPException as e:
            print(f"HTTP Exception: {e}")
            await asyncio.sleep(5)  # Attendre 5 secondes avant de réessayer
            await start_bot()
        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error: {e}")
            await asyncio.sleep(5)
            await start_bot()
        except Exception as e:
            print(f"Unexpected error: {e}")
            await asyncio.sleep(5)
            await start_bot()

    # Utiliser asyncio.run() pour démarrer le bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Bot stopped by user")

if __name__ == "__main__":
    main()
