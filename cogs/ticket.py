import discord
from discord.ext import commands
import re
import asyncio

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_category_id = 1020827427888435210
        self.CHANNEL_EDIT_DELAY = 2  # Délai en secondes entre chaque modification de salon

    async def is_ticket_channel(self, channel):
        try:
            async for message in channel.history(limit=10):
                for embed in message.embeds:
                    if embed.footer and "TicketTool.xyz" in embed.footer.text:
                        return True
            return False
        except Exception as e:
            print(f"Erreur lors de la vérification du ticket {channel.name}: {str(e)}")
            return False

    async def find_tickettool_answer(self, channel, question_text):
        try:
            async for message in channel.history(limit=20):
                for embed in message.embeds:
                    if embed.description:
                        lines = embed.description.split('\n')
                        for i, line in enumerate(lines):
                            if question_text in line and i + 1 < len(lines):
                                return lines[i + 1].strip()
            return None
        except Exception as e:
            print(f"Erreur lors de la recherche de réponse: {str(e)}")
            return None

    async def get_first_four_words(self, text):
        words = text.split()[:4]
        return ' '.join(words)

    async def process_ticket(self, channel):
        try:
            if not await self.is_ticket_channel(channel):
                return

            # Déplacer d'abord le ticket dans la bonne catégorie
            target_category = self.bot.get_channel(self.target_category_id)
            if target_category and channel.category_id != self.target_category_id:
                try:
                    await channel.move(category=target_category, sync_permissions=True)
                    await asyncio.sleep(self.CHANNEL_EDIT_DELAY)
                except discord.errors.HTTPException as e:
                    if e.status == 429:  # Rate limit
                        await asyncio.sleep(e.retry_after)
                        await channel.move(category=target_category, sync_permissions=True)
                    else:
                        print(f"Erreur lors du déplacement du salon {channel.name}: {e}")
                except Exception as e:
                    print(f"Erreur inattendue lors du déplacement du salon {channel.name}: {e}")

            # Rechercher et traiter les réponses pour le renommage
            new_name = None
            
            for question, response in [
                ("Quel est le nom de votre personnage ?", None),
                ("Quel est le sous-élément ?", None),
                ("Quel est le nom de la magie unique", None),
                ("Quelle est votre demande ?", lambda x: self.get_first_four_words(x))
            ]:
                answer = await self.find_tickettool_answer(channel, question)
                if answer:
                    new_name = await response(answer) if response else answer
                    break

            if new_name and new_name != channel.name:
                try:
                    await channel.edit(name=new_name)
                    await asyncio.sleep(self.CHANNEL_EDIT_DELAY)
                except discord.errors.HTTPException as e:
                    if e.status == 429:
                        await asyncio.sleep(e.retry_after)
                        await channel.edit(name=new_name)
                except Exception as e:
                    print(f"Erreur lors du renommage du salon {channel.name}: {e}")

        except Exception as e:
            print(f"Erreur lors du traitement du ticket {channel.name}: {str(e)}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.TextChannel):
            await asyncio.sleep(2)
            await self.process_ticket(channel)

    @discord.app_commands.command(name="process_tickets", description="Traite tous les tickets existants")
    @discord.app_commands.default_permissions(administrator=True)
    async def process_tickets(self, interaction: discord.Interaction):
        await interaction.response.defer()
        processed = 0
        
        for channel in interaction.guild.text_channels:
            try:
                await self.process_ticket(channel)
                processed += 1
                await asyncio.sleep(self.CHANNEL_EDIT_DELAY)
            except Exception as e:
                print(f"Erreur lors du traitement du ticket {channel.name}: {e}")

        await interaction.followup.send(f"Traitement terminé. {processed} tickets ont été traités.")

async def setup(bot):
    await bot.add_cog(Ticket(bot))