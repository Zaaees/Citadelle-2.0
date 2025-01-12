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

    async def setup_hook(self):
        # Charger les cogs
        await self.load_extension('cogs.inventaire')
        await self.load_extension('cogs.RPTracker')
        await self.load_extension('cogs.bump')
        await self.load_extension('cogs.vocabulaire')
        await self.load_extension('cogs.Souselement2')
        await self.load_extension('cogs.ticket')
        await self.load_extension('cogs.validation')

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
