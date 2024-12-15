import os
import discord
from discord.ext import commands

class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # Load cogs
        await self.load_extension('inventaire_cog')
        
        # Sync commands
        await self.tree.sync()

def main():
    # Bot configuration
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    # Create bot instance
    bot = CustomBot(
        command_prefix='!', 
        intents=intents
    )

    # Bot events
    @bot.event
    async def on_ready():
        print(f'Logged in as {bot.user.name}')
        print(f'Bot ID: {bot.user.id}')

    # Custom role check method
    def check_role(interaction):
        # Implement your role checking logic
        # This is a placeholder - replace with your actual role check
        return True
    
    bot.check_role = check_role

    # Run the bot
    bot.run(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    main()