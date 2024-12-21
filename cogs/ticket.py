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
            async for message in channel.history(limit=10):
                # Vérifie les embeds du message
                for embed in message.embeds:
                    if embed.footer and "TicketTool.xyz" in embed.footer.text:
                        print(f"Ticket trouvé: {channel.name}")
                        return True
            return False
        except Exception as e:
            print(f"Erreur lors de la vérification du ticket {channel.name}: {str(e)}")
            return False

    async def find_tickettool_answer(self, channel, question_text):
        try:
            async for message in channel.history(limit=20):
                # Vérifie les embeds du message
                for embed in message.embeds:
                    # Vérifie le contenu de l'embed
                    if embed.description:
                        # Divise la description en lignes
                        lines = embed.description.split('\n')
                        for i, line in enumerate(lines):
                            if question_text in line and i + 1 < len(lines):
                                # La réponse est la ligne suivante
                                answer = lines[i + 1].strip()
                                print(f"Réponse trouvée pour {question_text}: {answer}")
                                return answer
            return None
        except Exception as e:
            print(f"Erreur lors de la recherche de réponse: {str(e)}")
            return None

    async def get_first_four_words(self, text):
        words = text.split()[:4]
        return ' '.join(words)

    async def process_ticket(self, channel):
        try:
            print(f"Traitement du salon: {channel.name}")

            # Vérifie d'abord si c'est un ticket
            if not await self.is_ticket_channel(channel):
                print(f"Ce n'est pas un ticket: {channel.name}")
                return

            # Vérifie la catégorie
            target_category = self.bot.get_channel(self.target_category_id)
            if not target_category:
                print("Catégorie cible non trouvée")
                return
            
            if channel.category_id != self.target_category_id:
                print(f"Déplacement du salon {channel.name} vers la catégorie cible")
                await channel.move(category=target_category, sync_permissions=True)

            # Traitement selon le type de ticket
            name_answer = await self.find_tickettool_answer(channel, "Quel est le nom de votre personnage ?")
            if name_answer:
                print(f"Renommage en tant que fiche: {name_answer}")
                await channel.edit(name=name_answer)
                return

            sub_element = await self.find_tickettool_answer(channel, "Quel est le sous-élément ?")
            if sub_element:
                print(f"Renommage en tant que sous-élément: {sub_element}")
                await channel.edit(name=sub_element)
                return

            magic_name = await self.find_tickettool_answer(channel, "Quel est le nom de la magie unique")
            if magic_name:
                print(f"Renommage en tant que magie unique: {magic_name}")
                await channel.edit(name=magic_name)
                return

            request = await self.find_tickettool_answer(channel, "Quelle est votre demande ?")
            if request:
                new_name = await self.get_first_four_words(request)
                print(f"Renommage en tant que demande: {new_name}")
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
                print(f"Ticket traité: {channel.name}")

        await interaction.followup.send(f"Traitement terminé. {processed} tickets ont été traités.")

async def setup(bot):
    await bot.add_cog(Ticket(bot))