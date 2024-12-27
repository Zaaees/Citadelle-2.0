import discord
from discord.ext import commands
import re
import asyncio

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_category_id = 1020827427888435210
        self.CHANNEL_EDIT_DELAY = 2
        self.alphabet_mapping = {
            "A": "𝙰", "B": "𝙱", "C": "𝙲", "D": "𝙳", "E": "𝙴", "F": "𝙵", "G": "𝙶",
            "H": "𝙷", "I": "𝙸", "J": "𝙹", "K": "𝙺", "L": "𝙻", "M": "𝙼", "N": "𝙽",
            "O": "𝙾", "P": "𝙿", "Q": "𝚀", "R": "𝚁", "S": "𝚂", "T": "𝚃", "U": "𝚄",
            "V": "𝚅", "W": "𝚆", "X": "𝚇", "Y": "𝚈", "Z": "𝚉"
        }

    async def is_ticket_channel(self, channel):
        try:
            async for message in channel.history(limit=10):
                if message.embeds:
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
                if message.embeds:
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

    async def get_first_letter(self, text):
        if text:
            first_letter = text[0].upper()
            return self.alphabet_mapping.get(first_letter, None)
        return None

async def process_ticket(self, channel):
    try:
        if not await self.is_ticket_channel(channel):
            return False

        target_category = self.bot.get_channel(self.target_category_id)
        if target_category and channel.category != target_category:
            try:
                await channel.edit(category=target_category)
                await asyncio.sleep(self.CHANNEL_EDIT_DELAY)
            except Exception as e:
                print(f"Erreur lors du déplacement: {str(e)}")

        name_answer = await self.find_tickettool_answer(channel, "Quel est le nom de votre personnage ?")
        if name_answer:
            first_letter = await self.get_first_letter(name_answer)
            if first_letter:
                new_name = f"【🎭 】{first_letter}{name_answer[1:]}"
                await channel.edit(name=new_name)
                return True

        sub_element = await self.find_tickettool_answer(channel, "Quel est le sous-élément ?")
        if sub_element:
            first_letter = await self.get_first_letter(sub_element)
            if first_letter:
                new_name = f"【⭐ 】{first_letter}{sub_element[1:]}"
                await channel.edit(name=new_name)
                return True

        magic_name = await self.find_tickettool_answer(channel, "Quel est le nom de la magie unique")
        if magic_name:
            first_letter = await self.get_first_letter(magic_name)
            if first_letter:
                new_name = f"【🌟 】{first_letter}{magic_name[1:]}"
                await channel.edit(name=new_name)
                return True

        request = await self.find_tickettool_answer(channel, "Quelle est votre demande ?")
        if request:
            first_letter = await self.get_first_letter(request)
            if first_letter:
                new_name = f"【❔ 】{first_letter}{request[1:]}"
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

    @discord.app_commands.command(name="ticket", description="Traite tous les tickets existants")
    @discord.app_commands.default_permissions(administrator=True)
    async def process_tickets(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("Traitement des tickets en cours...", ephemeral=True)

            processed = 0
            total_processed = 0

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
