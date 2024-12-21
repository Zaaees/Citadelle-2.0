import discord
from discord.ext import commands
import re
import asyncio

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_category_id = 1020827427888435210

    async def is_ticket_channel(self, channel):
        try:
            async for message in channel.history(limit=5):
                if "TicketTool.xyz" in message.content:
                    return True
            return False
        except:
            return False

    async def find_tickettool_answer(self, channel, question):
        async for message in channel.history(limit=100):
            content = message.content
            if question in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if question in line and i + 1 < len(lines):
                        return lines[i + 1].strip()
        return None

    async def get_first_four_words(self, text):
        words = text.split()[:4]
        return ' '.join(words)

    async def process_ticket(self, channel):
        try:
            # Vérifie d'abord si c'est un ticket
            if not await self.is_ticket_channel(channel):
                return

            # Vérifie si le salon est déjà dans la bonne catégorie
            target_category = self.bot.get_channel(self.target_category_id)
            if not target_category:
                return
            
            if channel.category_id != self.target_category_id:
                await channel.move(category=target_category, sync_permissions=True)

            # Traitement selon le type de ticket
            
            # Ticket de fiche
            name_answer = await self.find_tickettool_answer(channel, "Quel est le nom de votre personnage ?")
            if name_answer:
                await channel.edit(name=name_answer)
                return

            # Ticket de sous-élément
            sub_element = await self.find_tickettool_answer(channel, "Quel est le sous-élément ?")
            if sub_element:
                await channel.edit(name=sub_element)
                return

            # Ticket de magie unique
            magic_name = await self.find_tickettool_answer(channel, "Quel est le nom de la magie unique")
            if magic_name:
                await channel.edit(name=magic_name)
                return

            # Ticket de demande
            request = await self.find_tickettool_answer(channel, "Quelle est votre demande ?")
            if request:
                new_name = await self.get_first_four_words(request)
                await channel.edit(name=new_name)
                return

        except discord.Forbidden:
            print(f"Permissions insuffisantes pour le salon {channel.name}")
        except Exception as e:
            print(f"Erreur lors du traitement du ticket {channel.name}: {str(e)}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.TextChannel):
            # Attendre que TicketTool finisse d'initialiser le ticket
            await asyncio.sleep(2)
            await self.process_ticket(channel)

    @discord.app_commands.command(name="process_tickets", description="Traite tous les tickets existants")
    @discord.app_commands.default_permissions(administrator=True)
    async def process_tickets(self, interaction: discord.Interaction):
        await interaction.response.defer()

        processed = 0
        for channel in interaction.guild.text_channels:
            if await self.is_ticket_channel(channel):
                await self.process_ticket(channel)
                processed += 1

        await interaction.followup.send(f"Traitement terminé. {processed} tickets ont été traités.")

async def setup(bot):
    await bot.add_cog(Ticket(bot))