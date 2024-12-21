import discord
from discord.ext import commands
import re
import asyncio

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_category_id = 1020827427888435210
        self.CHANNEL_EDIT_DELAY = 2

    async def is_ticket_channel(self, channel):
        try:
            async for message in channel.history(limit=10):
                # Vérifie si le message contient un embed
                if message.embeds:
                    for embed in message.embeds:
                        # Debug: afficher les informations de l'embed
                        print(f"Vérification du salon {channel.name}")
                        print(f"Embed trouvé: {embed.to_dict()}")
                        if embed.footer and "TicketTool.xyz" in embed.footer.text:
                            print(f"Ticket trouvé dans {channel.name}")
                            return True
            return False
        except Exception as e:
            print(f"Erreur lors de la vérification du ticket {channel.name}: {str(e)}")
            return False

    async def find_tickettool_answer(self, channel, question_text):
        try:
            async for message in channel.history(limit=20):
                if message.embeds:
                    for embed in message.embeds:
                        if embed.description:
                            # Debug: afficher la description de l'embed
                            print(f"Description de l'embed: {embed.description}")
                            if question_text in embed.description:
                                lines = embed.description.split('\n')
                                for i, line in enumerate(lines):
                                    if question_text in line and i + 1 < len(lines):
                                        print(f"Réponse trouvée: {lines[i + 1].strip()}")
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
            print(f"Vérification du salon: {channel.name}")
            if not await self.is_ticket_channel(channel):
                print(f"Ce n'est pas un ticket: {channel.name}")
                return False

            print(f"C'est un ticket: {channel.name}")
            
            # Déplacement du ticket
            target_category = self.bot.get_channel(self.target_category_id)
            if target_category and channel.category != target_category:  # Changement ici
                try:
                    print(f"Déplacement du salon {channel.name} vers {target_category.name}")
                    await channel.edit(category=target_category)  # Utilisation de edit au lieu de move
                    await asyncio.sleep(self.CHANNEL_EDIT_DELAY)
                except Exception as e:
                    print(f"Erreur lors du déplacement: {str(e)}")

            # Chercher la réponse appropriée pour renommer
            print(f"Recherche des réponses pour {channel.name}")
            name_answer = await self.find_tickettool_answer(channel, "Quel est le nom de votre personnage ?")
            if name_answer:
                print(f"Nom trouvé: {name_answer}")
                await channel.edit(name=name_answer)
                return True

            sub_element = await self.find_tickettool_answer(channel, "Quel est le sous-élément ?")
            if sub_element:
                print(f"Sous-élément trouvé: {sub_element}")
                await channel.edit(name=sub_element)
                return True

            magic_name = await self.find_tickettool_answer(channel, "Quel est le nom de la magie unique")
            if magic_name:
                print(f"Magie unique trouvée: {magic_name}")
                await channel.edit(name=magic_name)
                return True

            request = await self.find_tickettool_answer(channel, "Quelle est votre demande ?")
            if request:
                new_name = await self.get_first_four_words(request)
                print(f"Demande trouvée: {new_name}")
                await channel.edit(name=new_name)
                return True

            return False

        except Exception as e:
            print(f"Erreur lors du traitement du ticket {channel.name}: {str(e)}")
            return False

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.TextChannel):
            await asyncio.sleep(2)
            await self.process_ticket(channel)

    @discord.app_commands.command(name="process_tickets", description="Traite tous les tickets existants")
    @discord.app_commands.default_permissions(administrator=True)
    async def process_tickets(self, interaction: discord.Interaction):
        try:
            # Répondre immédiatement pour éviter l'expiration de l'interaction
            await interaction.response.send_message("Traitement des tickets en cours...", ephemeral=True)
            
            processed = 0
            total_processed = 0
            
            # Filtrer uniquement les salons qui n'ont pas de catégorie
            channels_to_check = [
                channel for channel in interaction.guild.text_channels 
                if channel.category is None
            ]
            
            for channel in channels_to_check:
                try:
                    if await self.process_ticket(channel):
                        processed += 1
                    total_processed += 1
                    await asyncio.sleep(self.CHANNEL_EDIT_DELAY)
                except Exception as e:
                    print(f"Erreur lors du traitement du ticket {channel.name}: {e}")

            await interaction.followup.send(
                f"Traitement terminé. {processed} tickets ont été traités sur {total_processed} salons vérifiés.",
                ephemeral=True
            )

        except Exception as e:
            print(f"Erreur lors de l'exécution de la commande: {str(e)}")
            try:
                await interaction.followup.send("Une erreur est survenue lors du traitement.", ephemeral=True)
            except:
                pass

async def setup(bot):
    await bot.add_cog(Ticket(bot))