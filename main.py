import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Serveur HTTP minimal pour Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')

def start_http_server():
    port = int(os.environ.get("PORT", 10000))  # Render utilise la variable d'environnement PORT
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Serveur HTTP démarré sur le port {port}")
    server.serve_forever()

# Classe personnalisée pour le bot
class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Charger les cogs
        await self.load_extension('cogs.inventaire')
        await self.load_extension('cogs.RPTracker')
        await self.load_extension('cogs.bump')
        await self.load_extension('cogs.vocabulaire')

        # Synchroniser les commandes
        await self.tree.sync()

    def check_role(self, interaction):
        # Implémentez votre logique de vérification de rôle ici
        return True

def main():
    # Démarrer le serveur HTTP dans un thread séparé
    threading.Thread(target=start_http_server, daemon=True).start()

    # Configuration du bot
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # Créer une instance du bot
    bot = CustomBot(
        command_prefix='!', 
        intents=intents
    )

    # Événements du bot
    @bot.event
    async def on_ready():
        print(f'Connecté en tant que {bot.user.name}')
        print(f'ID du bot : {bot.user.id}')

    # Exécuter le bot
    bot.run(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    main()
