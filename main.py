import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv
import time

# Charger les variables d'environnement
load_dotenv()

# Serveur HTTP minimal pour Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
        print(f"GET request received at {self.path} from {self.client_address}")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Cache-Control', 'no-cache, no-store')
        self.end_headers()
        print(f"HEAD request received at {self.path} from {self.client_address}")

    def log_message(self, format, *args):
        # Surcharger pour éviter les logs excessifs
        if args[0].startswith('HEAD') or args[0].startswith('GET'):
            print(f"{self.client_address[0]} - - [{time.strftime('%d/%b/%Y %H:%M:%S')}] {args[0]}")
        return

def start_http_server():
    try:
        # Render fournit PORT, sinon utiliser 10000 localement
        port = int(os.environ.get("PORT", 10000))
        print(f"Port utilisé: {port}")
        
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"Serveur HTTP démarré avec succès sur le port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"Erreur lors du démarrage du serveur : {e}")
        import traceback
        traceback.print_exc()
        
        # Réessayer après un délai si le serveur échoue
        time.sleep(5)
        print("Tentative de redémarrage du serveur HTTP...")
        start_http_server()

# Classe personnalisée pour le bot
class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_server_thread = None

    async def setup_hook(self):
        # Charger les cogs
        await self.load_extension('cogs.inventaire')
        await self.load_extension('cogs.RPTracker')
        await self.load_extension('cogs.bump')
        await self.load_extension('cogs.vocabulaire')
        await self.load_extension('cogs.souselement')
        await self.load_extension('cogs.ticket')
        await self.load_extension('cogs.validation')
        await self.load_extension('cogs.Espace')
        await self.load_extension('cogs.Inactif')

        # Synchroniser les commandes
        await self.tree.sync()
        print("Commandes synchronisées avec succès")

    def check_role(self, interaction):
        # Implémentez votre logique de vérification de rôle ici
        return True

    def start_http_server_thread(self):
        # Démarrer le serveur HTTP dans un thread séparé
        self.http_server_thread = threading.Thread(target=start_http_server, daemon=True)
        self.http_server_thread.start()
        print("Thread du serveur HTTP démarré")

def main():
    # Configuration du bot
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # Créer une instance du bot
    bot = CustomBot(
        command_prefix='!', 
        intents=intents
    )

    # Démarrer le serveur HTTP avant le bot
    bot.start_http_server_thread()

    # Définir la fonction on_ready et l'ajouter comme listener
    async def on_ready():
        print(f'Connecté en tant que {bot.user.name}')
        print(f'ID du bot : {bot.user.id}')
        
        # Vérifier si le thread du serveur HTTP est toujours en cours d'exécution
        if not bot.http_server_thread or not bot.http_server_thread.is_alive():
            print("Le thread du serveur HTTP n'est pas en cours d'exécution. Redémarrage...")
            bot.start_http_server_thread()
    
    # Ajouter le listener au lieu d'utiliser le décorateur
    bot.add_listener(on_ready, 'on_ready')

    # Exécuter le bot
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        print(f"Erreur lors du démarrage du bot : {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()