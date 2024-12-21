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
                    # Vérifie que c'est bien un ticket TicketTool
                    if (embed.footer and "TicketTool.xyz" in embed.footer.text 
                        and embed.author  # Vérifie qu'il y a un auteur
                        and " (" in embed.author.name):  # Format typique "@User (Info | Info)"
                        print(f"Ticket trouvé: {channel.name}")
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

            # Obtenir la catégorie cible
            target_category = self.bot.get_channel(self.target_category_id)
            if not target_category:
                print("Catégorie cible non trouvée")
                return

            # Déplacer d'abord le ticket dans la bonne catégorie s'il n'y est pas déjà
            if channel.category_id != self.target_category_id:
                print(f"Déplacement du salon {channel.name} vers la catégorie cible")
                await channel.move(category=target_category, sync_permissions=True)
                # Attendre un court instant pour s'assurer que le déplacement est terminé
                await asyncio.sleep(1)

            # Rechercher et traiter les réponses pour le renommage
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
            # Traiter tous les canaux textuels, qu'ils soient dans une catégorie ou non
            if await self.is_ticket_channel(channel):
                await self.process_ticket(channel)
                processed += 1
                print(f"Ticket traité: {channel.name}")

        await interaction.followup.send(f"Traitement terminé. {processed} tickets ont été traités.")

async def setup(bot):
    await bot.add_cog(Ticket(bot))