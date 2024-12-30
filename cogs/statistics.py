import discord
from discord.ext import commands
import asyncio

class Statistics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.categories_to_analyze = [1093159899749417010, 1018543594518347939, 1018441801847287810]

    @commands.hybrid_command(name="stats")
    @commands.has_permissions(administrator=True)
    async def stats(self, ctx):
        await ctx.defer()
        
        total_chars = 0
        
        for category_id in self.categories_to_analyze:
            category = ctx.guild.get_channel(category_id)
            if not category:
                continue

            for channel in category.channels:
                if isinstance(channel, discord.TextChannel):
                    # Compte les messages du canal principal
                    async for message in channel.history(limit=None):
                        total_chars += len(message.content)
                    
                    # Compte les messages des threads
                    for thread in channel.threads:
                        async for message in thread.history(limit=None):
                            total_chars += len(message.content)

        # Crée un embed avec le résultat total
        embed = discord.Embed(title="Statistiques du serveur", color=discord.Color.blue())
        embed.add_field(
            name="Total des caractères",
            value=f"{total_chars:,}",
            inline=False
        )

        await ctx.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Statistics(bot))