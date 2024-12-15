import os
import discord
from discord.ext import commands

class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Charger les cogs
        await self.load_extension('cogs.inventaire')
        
        # Synchroniser les commandes
        await self.tree.sync()

    def check_role(self, interaction):
        # Implémentez votre logique de vérification de rôle ici
        return True

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

    # Événements du bot
    @bot.event
    async def on_ready():
        print(f'Connecté en tant que {bot.user.name}')
        print(f'ID du bot : {bot.user.id}')

    # Exécuter le bot
    bot.run(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    main()